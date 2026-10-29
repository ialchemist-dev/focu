"""Artifact replication, one-writer metadata checkpoints and disaster recovery."""
from __future__ import annotations
import argparse
import contextlib
import gzip
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time
from focu.reader import ReaderStore
from focu.drive_storage import DriveStorage
from focu.git_journal import GitJournal
from focu.intents import utcnow
from focu import sync_events
from focu.covers import source_cover
from focu.cover_archive import mirror


@contextlib.contextmanager
def writer_lock(path):
    import fcntl
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a') as f:
        try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('Another sync writer is active') from None
        try:yield
        finally:fcntl.flock(f,fcntl.LOCK_UN)


def contained(root,relative):
    if not isinstance(relative,str) or Path(relative).is_absolute():raise ValueError('Invalid relative artifact path')
    path=(root/relative).resolve()
    if not path.is_relative_to(root.resolve()):raise ValueError('Artifact escapes configured root')
    return path


def install_snapshot(path,source):
    source_db=sqlite3.connect(source)
    target=sqlite3.connect(path)
    try:source_db.backup(target)
    finally:target.close();source_db.close()


class DataSync:
    def __init__(self,store,media_root,drive,journal):
        self.store=store;self.root=Path(media_root).resolve();self.drive=drive;self.journal=journal
        self.work=store.path.resolve().parent/'focu-sync-work'
        self.work.mkdir(parents=True,exist_ok=True,mode=0o700)
        os.chmod(self.work,0o700)

    def run(self):
        with writer_lock(self.work/'writer.lock'):
            with self.store.db() as db:
                sync_events.meta(db,'configured',True);sync_events.meta(db,'syncing',True)
            try:
                result=self._run()
            except Exception as exc:
                with self.store.db() as db:
                    sync_events.meta(db,'syncing',False)
                    # Never serialize provider responses, tokens or command stderr.
                    sync_events.meta(db,'last_error',type(exc).__name__+': sync incomplete; pending changes retained')
                raise
            with self.store.db() as db:
                db.execute('UPDATE sync_events SET synced=1 WHERE seq<=?',(result['highwater'],))
                sync_events.meta(db,'checkpoint',result['checkpoint'])
                sync_events.meta(db,'last_success_at',utcnow());sync_events.meta(db,'last_error',None)
                sync_events.meta(db,'warnings',result.get('warnings',[]))
                sync_events.meta(db,'syncing',False)
            return result

    def _run(self):
        self.journal.prepare() # Fail before uploading if remote is public/divergent.
        self.drive.verify_folder()
        with tempfile.TemporaryDirectory(prefix='snapshot-',dir=self.work) as d:
            stage=Path(d);snapshot=stage/'state.sqlite3'
            install_snapshot(snapshot,self.store.path)
            snap=ReaderStore(snapshot)
            with snap.db() as db:
                highwater=db.execute('SELECT coalesce(max(seq),0) FROM sync_events').fetchone()[0]
                items=[json.loads(r['payload']) for r in db.execute('SELECT payload FROM reader_items ORDER BY id')]
                batches=[dict(r) for r in db.execute('SELECT * FROM reader_batches ORDER BY id')]
                covers=[dict(r) for r in db.execute('SELECT * FROM reader_covers ORDER BY item_id')]
                subscriptions=[dict(r) for r in db.execute('SELECT * FROM reader_subscriptions ORDER BY pack_id')]
                states=[dict(r) for r in db.execute('SELECT * FROM reader_state ORDER BY item_id')]
                research_fingerprint=[]
                for table in ('intents','evidence_packs','delivery_artifacts','reader_raw_queue'):
                    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone():
                        research_fingerprint.append((table,[tuple(r) for r in db.execute(f'SELECT * FROM {table} ORDER BY rowid')]))
                events=[{k:r[k] for k in ('seq','event_id','target','operation','changes','created_at')}
                        for r in db.execute('SELECT * FROM sync_events WHERE seq<=? ORDER BY seq',(highwater,))]
            records=[];warnings=[]
            cover_map={row['item_id']:json.loads(row['payload']) for row in covers}
            def upload(artifact_id,item_id,kind,path,relative=None):
                mime=mimetypes.guess_type(str(path))[0] or 'application/octet-stream'
                record=self.drive.upload(path,artifact_id,mime)
                row={'artifact_id':artifact_id,'item_id':item_id,'kind':kind,
                     'relative_path':relative,'record':json.dumps(record,sort_keys=True)}
                records.append(row)
                return record
            for item in items:
                identity=hashlib.sha256(item['id'].encode()).hexdigest()
                report=stage/(identity+'.md');report.write_text(item['markdown'])
                upload(item['id']+':report',item['id'],'report',report)
                cover=cover_map.get(item['id']) or source_cover(item['sources'])
                if cover:
                    try:
                        with self.store.db() as db:
                            previous_cover=db.execute("SELECT * FROM sync_artifacts WHERE item_id=? AND kind='cover'",(item['id'],)).fetchone()
                        if previous_cover and json.loads(previous_cover['record']).get('source_image_url')==cover['url']:
                            cover_path=ArtifactCache(self.store,self.root,self.drive).ensure(previous_cover['relative_path'])
                        else:
                            cover_path=mirror(cover['url'],self.root)
                        upload(item['id']+':cover',item['id'],'cover',cover_path,str(cover_path.relative_to(self.root)))
                        record=json.loads(records[-1]['record']);record['source_image_url']=cover['url']
                        records[-1]['record']=json.dumps(record,sort_keys=True)
                    except Exception:
                        warnings.append({'item_id':item['id'],'kind':'cover','status':'original_image_unavailable'})
                for kind,relative in item['media'].items():
                    path=contained(self.root,relative)
                    if not path.is_file():
                        ArtifactCache(self.store,self.root,self.drive).ensure(relative)
                    upload(item['id']+':'+kind,item['id'],kind,path,relative)
                with snap.db() as db:
                    derivatives=db.execute('SELECT id,kind,content FROM delivery_artifacts WHERE evidence_id=? AND kind!=?',
                                           (item['id'],'research_markdown')).fetchall()
                    evidence=db.execute('SELECT payload FROM evidence_packs WHERE id=?',(item['id'],)).fetchone() if db.execute("SELECT 1 FROM sqlite_master WHERE name='evidence_packs'").fetchone() else None
                for derivative in derivatives:
                    path=stage/(hashlib.sha256(derivative['id'].encode()).hexdigest()+'.json')
                    path.write_text(derivative['content'])
                    upload(derivative['id'],item['id'],derivative['kind'],path)
                if evidence:
                    path=stage/(identity+'-evidence.json');path.write_text(evidence['payload'])
                    upload(item['id']+':evidence',item['id'],'evidence_pack',path)
            # A database baseline only changes when content changes. Reading-only
            # commits reuse it; current state/covers/subscriptions live in Git metadata.
            content_digest=hashlib.sha256(json.dumps({'items':items,'batches':batches,
                'artifacts':records,'research':research_fingerprint},sort_keys=True).encode()).hexdigest()
            with self.store.db() as db:
                row=db.execute("SELECT value FROM sync_meta WHERE key='checkpoint'").fetchone()
                previous=json.loads(row['value']) if row else None
            catalog_path=self.journal.path/'focu/catalog.json'
            if catalog_path.is_file():
                prior_catalog=json.loads(catalog_path.read_text())
                if prior_catalog.get('checkpoint',{}).get('content_digest')==content_digest:
                    previous=prior_catalog['checkpoint']
            if previous and previous['content_digest']==content_digest:
                checkpoint=previous
            else:
                with snap.db() as db:
                    for row in records:db.execute('INSERT OR REPLACE INTO sync_artifacts VALUES (?,?,?,?,?)',tuple(row.values()))
                # Gzip immutable baseline. It never goes into Git.
                standalone=stage/'baseline-clean.sqlite3'
                install_snapshot(standalone,snapshot)
                packed=stage/'baseline.sqlite3.gz'
                with standalone.open('rb') as source,gzip.GzipFile(filename=str(packed),mode='wb',mtime=0) as out:
                    shutil.copyfileobj(source,out)
                checkpoint={'content_digest':content_digest,'database':self.drive.upload(packed,'baseline:'+content_digest,'application/gzip')}
            catalog={'schema_version':1,'highwater':highwater,'checkpoint':checkpoint,
                     'items':[{k:v for k,v in item.items() if k!='markdown'} for item in items],
                     'batches':batches,'states':states,'covers':covers,'subscriptions':subscriptions,'artifacts':records,'warnings':warnings}
            for item in catalog['items']:
                item['generated_at']=item['created_at']
                dates=[batch['created_at'] for batch in batches if item['id'] in json.loads(batch['members'])]
                item['published_at']=min(dates) if dates else None
            # Strip large captured source text; the canonical source packs and reports
            # are recoverable from the Drive database baseline.
            for item in catalog['items']:
                item['sources']=[{k:v for k,v in source.items() if k not in {'extracted_text','html','body'}} for source in item['sources']]
            commit=self.journal.publish(catalog,events)
            # No network call after acknowledgement: status tracks the exact captured prefix.
            with self.store.db() as db:
                for row in records:db.execute('INSERT OR REPLACE INTO sync_artifacts VALUES (?,?,?,?,?)',tuple(row.values()))
            return {'status':'synced','warnings':warnings,'highwater':highwater,'commit':commit,'artifacts':len(records),'checkpoint':checkpoint}


class ArtifactCache:
    def __init__(self,store,root,drive):self.store=store;self.root=Path(root).resolve();self.drive=drive
    def ensure(self,relative):
        target=contained(self.root,relative)
        if target.is_file():return target
        with self.store.db() as db:
            row=db.execute('SELECT record FROM sync_artifacts WHERE relative_path=?',(relative,)).fetchone()
        if not row:raise FileNotFoundError('Artifact has no verified Drive copy')
        return self.drive.download(json.loads(row['record']),target)


def restore(journal,drive,destination,media_root,*,download_media=False):
    destination=Path(destination).resolve();root=Path(media_root).resolve()
    if destination.exists():raise ValueError('Restore requires a new database path; existing data is never overwritten')
    catalog=journal.read()
    drive.verify_folder()
    if catalog.get('schema_version')!=1:raise ValueError('Unsupported metadata schema')
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='focu-restore-',dir=destination.parent) as d:
        stage=Path(d);packed=stage/'baseline.gz';database=stage/'restored.sqlite3'
        drive.download(catalog['checkpoint']['database'],packed)
        with gzip.open(packed,'rb') as source,database.open('wb') as out:shutil.copyfileobj(source,out)
        store=ReaderStore(database)
        with store.db() as db:
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('Restored database integrity check failed')
            # Current state is Git's checkpoint, not the older Drive baseline state.
            for table,key in [('reader_state','states'),('reader_covers','covers'),('reader_subscriptions','subscriptions')]:
                db.execute('DELETE FROM '+table)
                for row in catalog[key]:
                    columns=list(row)
                    expected={'reader_state':{'item_id','completed','saved','archived','position_seconds','read_at','saved_at','archived_at'},'reader_covers':{'item_id','payload'},'reader_subscriptions':{'pack_id','payload'}}[table]
                    if set(columns)!=expected:raise ValueError('Invalid restored metadata columns')
                    db.execute(f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",tuple(row.values()))
            for row in catalog['artifacts']:
                db.execute('INSERT OR REPLACE INTO sync_artifacts VALUES (?,?,?,?,?)',tuple(row[k] for k in ('artifact_id','item_id','kind','relative_path','record')))
            db.execute('DELETE FROM sync_events')
            for path in sorted((journal.path/'focu/events').glob('*.json')):
                event=json.loads(path.read_text())
                if event['seq']<=catalog['highwater']:
                    db.execute('INSERT INTO sync_events(seq,event_id,target,operation,changes,created_at,synced) VALUES (?,?,?,?,?,?,1)',
                               tuple(event[k] for k in ('seq','event_id','target','operation','changes','created_at')))
            sync_events.meta(db,'checkpoint',catalog['checkpoint']);sync_events.meta(db,'last_success_at',utcnow())
            sync_events.meta(db,'syncing',False);sync_events.meta(db,'last_error',None);sync_events.meta(db,'configured',True)
        # SQLite backup closes WAL safely and creates a standalone installable database.
        standalone=stage/'standalone.sqlite3';install_snapshot(standalone,database)
        if download_media:
            cache=ArtifactCache(store,root,drive)
            for row in catalog['artifacts']:
                if row['relative_path']:cache.ensure(row['relative_path'])
        # Exclusive creation prevents a race from overwriting another database.
        with destination.open('xb') as out,standalone.open('rb') as source:shutil.copyfileobj(source,out)
        os.chmod(destination,0o600)
    return {'status':'restored','db':str(destination),'highwater':catalog['highwater'],'media_downloaded':download_media}


def main(argv=None,*,db_path='data/focu.sqlite3'):
    p=argparse.ArgumentParser(prog='focu sync');sub=p.add_subparsers(dest='action',required=True)
    for action in ('run','watch','restore'):
        parser=sub.add_parser(action);parser.add_argument('--repo',required=True);parser.add_argument('--media-root',required=True)
        parser.add_argument('--drive-config')
        if action=='watch':parser.add_argument('--interval',type=int,default=60)
        if action=='restore':parser.add_argument('--download-media',action='store_true')
    sub.add_parser('status')
    args=p.parse_args(argv)
    if args.action=='status':result=ReaderStore(db_path).sync_status()
    else:
        journal=GitJournal(args.repo);drive=DriveStorage(args.drive_config)
        if args.action=='restore':result=restore(journal,drive,db_path,args.media_root,download_media=args.download_media)
        else:
            service=DataSync(ReaderStore(db_path),args.media_root,drive,journal)
            if args.action=='watch':
                if args.interval<15:raise ValueError('Sync interval must be at least 15 seconds')
                while True:
                    try:service.run()
                    except Exception:print('Focu sync pending; check private configuration and connectivity',flush=True)
                    time.sleep(args.interval)
            result=service.run()
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0
