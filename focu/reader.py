"""Finite, explicitly published research batches and pinned source subscriptions."""
from __future__ import annotations
import argparse
import json
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from focu.delivery import DeliveryArchive
from focu.evidence import EvidenceStore
from focu.intents import IntentStore
from focu.covers import source_cover, image_url
from focu import sync_events

class StateConflict(ValueError):
    pass


ASSETS = Path(__file__).with_name('reader_assets')
PACKS = Path(__file__).with_name('source_packs')


def canonical_url(value):
    p = urlsplit(value)
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password:
        raise ValueError('Expected a public HTTP(S) source URL')
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip('/') or '/', p.query, ''))


class ReaderStore:
    def __init__(self, db_path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        DeliveryArchive(self.path)
        with self.db() as db:
            sync_events.initialize(db)
            db.executescript('''
                CREATE TABLE IF NOT EXISTS reader_items (
                    id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS reader_batches (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, members TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));
                CREATE TABLE IF NOT EXISTS reader_state (
                    item_id TEXT PRIMARY KEY REFERENCES reader_items(id),
                    completed INTEGER NOT NULL DEFAULT 0, saved INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS reader_covers (
                    item_id TEXT PRIMARY KEY REFERENCES reader_items(id), payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS reader_subscriptions (
                    pack_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            ''')

        with self.db() as db:
            columns={r['name'] for r in db.execute('PRAGMA table_info(reader_state)')}
            for name,definition in [('archived','INTEGER NOT NULL DEFAULT 0'),('position_seconds','REAL NOT NULL DEFAULT 0'),('read_at','TEXT'),('saved_at','TEXT'),('archived_at','TEXT')]:
                if name not in columns:db.execute(f'ALTER TABLE reader_state ADD COLUMN {name} {definition}')

    def db(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        return db

    def publish(self, batch_id, title, evidence_ids, *, media=None, limit=20):
        if not isinstance(batch_id, str) or not batch_id.strip() or not isinstance(title, str) or not title.strip():
            raise ValueError('Batch ID and title required')
        if not isinstance(evidence_ids, list) or not evidence_ids or len(set(evidence_ids)) != len(evidence_ids):
            raise ValueError('Expected unique evidence IDs')
        if not 1 <= limit <= 100 or len(evidence_ids) > limit:
            raise ValueError('Batch exceeds explicit item budget (1–100)')
        items = []
        for eid in evidence_ids:
            pack = EvidenceStore(self.path).get(eid)
            if pack is None:
                raise ValueError('Unknown evidence pack: ' + eid)
            intent = IntentStore(self.path).get(pack['intent_id'])
            if not intent or intent['status'] != 'completed' or intent['evidence_pack_id'] != eid:
                raise ValueError('Publish requires completed research linked to its evidence pack')
            report = DeliveryArchive(self.path).get('research:' + eid)
            item = dict(id=eid, title=intent['question'], summary=pack['summary'],
                        markdown=report['content'], sources=pack['sources'],
                        created_at=pack['created_at'], media=(media or {}).get(eid, {}))
            if set(item['media']) - {'audio', 'video'}:
                raise ValueError('Unsupported presentation format')
            for filename in item['media'].values():
                if not isinstance(filename, str) or not filename.strip():
                    raise ValueError('Media path must be nonempty text')
                p = Path(filename)
                if p.is_absolute() or '..' in p.parts:
                    raise ValueError('Media must be relative to the configured media root')
            items.append(item)
        members = json.dumps(evidence_ids)
        # Validate every immutable conflict before committing any new item or batch.
        with self.db() as db:
            for item in items:
                payload = json.dumps(item, ensure_ascii=False, sort_keys=True)
                old = db.execute('SELECT payload FROM reader_items WHERE id=?', (item['id'],)).fetchone()
                if old and old['payload'] != payload:
                    raise ValueError('Published item is immutable: ' + item['id'])
                db.execute('INSERT OR IGNORE INTO reader_items VALUES (?, ?)', (item['id'], payload))
            old = db.execute('SELECT title,members FROM reader_batches WHERE id=?', (batch_id,)).fetchone()
            if old and (old['title'], old['members']) != (title, members):
                raise ValueError('Batch ID reused with different selection')
            db.execute('INSERT OR IGNORE INTO reader_batches(id,title,members) VALUES (?,?,?)', (batch_id,title,members))
            if old is None:sync_events.append(db,batch_id,'publish',{'members':evidence_ids})
        return self.batch(batch_id)

    def item(self, item_id):
        with self.db() as db:
            row = db.execute('SELECT payload FROM reader_items WHERE id=?', (item_id,)).fetchone()
            if not row:
                raise ValueError('Unknown reader item')
            state = db.execute('SELECT * FROM reader_state WHERE item_id=?', (item_id,)).fetchone()
            cover = db.execute('SELECT payload FROM reader_covers WHERE item_id=?',(item_id,)).fetchone()
            revision=db.execute("SELECT coalesce(max(seq),0) FROM sync_events WHERE target=?",(item_id,)).fetchone()[0]
        payload=json.loads(row['payload'])
        cover_value=json.loads(cover['payload']) if cover else source_cover(payload['sources'])
        if cover_value:
            with self.db() as db:
                archived=db.execute("SELECT record FROM sync_artifacts WHERE item_id=? AND kind='cover'",(item_id,)).fetchone()
            if archived and json.loads(archived['record']).get('source_image_url')==cover_value['url']:
                from urllib.parse import quote
                cover_value={**cover_value,'cache_url':'/cover?id='+quote(item_id,safe='')}
        return {**payload, 'cover':cover_value, 'completed': bool(state['completed']) if state else False,
                'saved': bool(state['saved']) if state else False,
                'archived':bool(state['archived']) if state else False,
                'position_seconds':state['position_seconds'] if state else 0,
                'read_at':state['read_at'] if state else None,'saved_at':state['saved_at'] if state else None,
                'archived_at':state['archived_at'] if state else None,'revision':revision}

    def set_cover(self, item_id, url, source_url, alt=''):
        item=self.item(item_id)
        if canonical_url(source_url) not in {canonical_url(s['url']) for s in item['sources']}:
            raise ValueError('Cover must be attributed to a cited source')
        safe=image_url(url,source_url)
        if safe is None:
            raise ValueError('Cover requires a credential-free HTTPS image URL')
        if not isinstance(alt,str) or len(alt)>1000:
            raise ValueError('Invalid cover description')
        cover={'url':safe,'source_url':source_url,'alt':alt or item['title']}
        with self.db() as db:
            db.execute('INSERT OR REPLACE INTO reader_covers VALUES (?,?)',
                       (item_id,json.dumps(cover,ensure_ascii=False)))
            sync_events.append(db,item_id,'cover',cover)
        return self.item(item_id)

    def state(self, item_id, changes, *, event_id=None, expected_revision=None):
        allowed={'completed','saved','archived','position_seconds'}
        if not isinstance(changes,dict) or not changes or set(changes)-allowed:
            raise ValueError('Expected explicit reading state changes')
        for key,value in changes.items():
            if key=='position_seconds':
                import math
                if type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=604800:
                    raise ValueError('Invalid playback position')
            elif type(value) is not bool:raise ValueError('Expected boolean reading state')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM reader_items WHERE id=?',(item_id,)).fetchone():
                raise ValueError('Unknown reader item')
            prior=db.execute('SELECT * FROM sync_events WHERE event_id=?',(event_id,)).fetchone() if event_id else None
            if prior:
                sync_events.append(db,item_id,'state',changes,event_id)
            else:
                revision=db.execute('SELECT coalesce(max(seq),0) FROM sync_events WHERE target=?',(item_id,)).fetchone()[0]
                if expected_revision is not None and (type(expected_revision) is not int or expected_revision!=revision):
                    raise StateConflict('Reading state changed on another client; reload before retrying')
                db.execute('INSERT OR IGNORE INTO reader_state(item_id) VALUES (?)',(item_id,))
                from focu.intents import utcnow
                for key,value in changes.items():
                    db.execute(f'UPDATE reader_state SET {key}=? WHERE item_id=?',(value,item_id))
                    timestamp={'completed':'read_at','saved':'saved_at','archived':'archived_at'}.get(key)
                    if timestamp:db.execute(f'UPDATE reader_state SET {timestamp}=? WHERE item_id=?',(utcnow() if value else None,item_id))
                sync_events.append(db,item_id,'state',changes,event_id)
        return self.item(item_id)

    def sync_status(self):
        with self.db() as db:return sync_events.status(db)

    def batches(self):
        with self.db() as db:
            return [dict(r) for r in db.execute('SELECT id,title,created_at FROM reader_batches ORDER BY created_at DESC,rowid DESC')]

    def batch(self, batch_id):
        with self.db() as db:
            row = db.execute('SELECT * FROM reader_batches WHERE id=?',(batch_id,)).fetchone()
        if not row:
            raise ValueError('Unknown batch')
        items = [self.item(i) for i in json.loads(row['members'])]
        return {'id':batch_id,'title':row['title'],'created_at':row['created_at'], 'items':items,
                'remaining':sum(not i['completed'] and not i['archived'] for i in items)}

    def library(self):
        with self.db() as db:
            ids = [r['item_id'] for r in db.execute('SELECT item_id FROM reader_state WHERE saved=1 OR completed=1 OR archived=1 ORDER BY rowid DESC')]
        return [self.item(i) for i in ids]

    def packs(self):
        packs = [json.loads(p.read_text()) for p in sorted(PACKS.glob('*.json'))]
        with self.db() as db:
            subscriptions = {r['pack_id']:json.loads(r['payload']) for r in db.execute('SELECT * FROM reader_subscriptions')}
        return [{**p, 'subscribed_version': subscriptions.get(p['id'],{}).get('version')} for p in packs]

    def subscribe(self, pack_id, enabled, version=None):
        if type(enabled) is not bool:
            raise ValueError('Expected enabled boolean')
        if not enabled:
            with self.db() as db:
                db.execute('DELETE FROM reader_subscriptions WHERE pack_id=?',(pack_id,))
                sync_events.append(db,pack_id,'unsubscribe',{})
            return {'id':pack_id,'subscribed':False}
        pack = next((p for p in self.packs() if p['id']==pack_id),None)
        if not pack or version != pack['version']:
            raise ValueError('Inspect and select a known pack version before subscribing')
        pack.pop('subscribed_version',None)
        with self.db() as db:
            db.execute('INSERT OR REPLACE INTO reader_subscriptions VALUES (?,?)',
                       (pack_id,json.dumps(pack,ensure_ascii=False,sort_keys=True)))
            sync_events.append(db,pack_id,'subscribe',{'version':version})
        return {'id':pack_id,'subscribed':True,'version':version}

    def sources(self):
        with self.db() as db:
            packs = [json.loads(r['payload']) for r in db.execute('SELECT payload FROM reader_subscriptions ORDER BY pack_id')]
        result = {}
        for pack in packs:
            for source in pack['sources']:
                locator = canonical_url(source.get('feed_url') or source['site_url'])
                if locator not in result:
                    result[locator] = {**source,'groups':[]}
                result[locator]['groups'].append(pack['id'])
        return list(result.values())


def main(argv=None, *, db_path='data/focu.sqlite3'):
    p = argparse.ArgumentParser(prog='focu reader')
    sub = p.add_subparsers(dest='action', required=True)
    serve = sub.add_parser('serve')
    serve.add_argument('--port',type=int,default=8765)
    serve.add_argument('--media-root',default='data')
    serve.add_argument('--public-origin',help='Exact trusted HTTPS origin, e.g. Tailscale Serve URL')
    serve.add_argument('--drive-config',help='Private Drive config for lazy media-cache recovery')
    publish = sub.add_parser('publish')
    publish.add_argument('--batch-id',required=True)
    publish.add_argument('--title',required=True)
    publish.add_argument('--evidence-id',action='append',required=True)
    publish.add_argument('--media-json',help='JSON mapping evidence ID to audio/video paths relative to media root')
    publish.add_argument('--limit',type=int,default=20)
    sub.add_parser('sources')
    cover=sub.add_parser('cover',help='Attach an original source image to an existing card')
    cover.add_argument('--evidence-id',required=True)
    cover.add_argument('--image-url',required=True)
    cover.add_argument('--source-url',required=True)
    cover.add_argument('--alt',default='')
    collection=sub.add_parser('collect')
    collection.add_argument('--output',required=True)
    ack=sub.add_parser('acknowledge')
    ack.add_argument('--record-id',action='append',required=True)
    subscribe = sub.add_parser('subscribe')
    subscribe.add_argument('pack_id')
    subscribe.add_argument('--version',required=True)
    unsubscribe = sub.add_parser('unsubscribe')
    unsubscribe.add_argument('pack_id')
    args=p.parse_args(argv)
    store=ReaderStore(db_path)
    if args.action=='serve':
        from focu.reader_server import serve as run
        run(store,args.port,Path(args.media_root),public_origin=args.public_origin,drive_config=args.drive_config)
        return 0
    if args.action=='cover':
        result=store.set_cover(args.evidence_id,args.image_url,args.source_url,args.alt)
    elif args.action=='collect':
        from focu.source_collection import collect
        result=collect(store,Path(args.output))
    elif args.action=='acknowledge':
        from focu.source_collection import acknowledge
        result=acknowledge(store,args.record_id)
    elif args.action=='publish':
        result=store.publish(args.batch_id,args.title,args.evidence_id,
                             media=json.loads(Path(args.media_json).read_text()) if args.media_json else None,limit=args.limit)
    elif args.action=='sources':
        result={'sources':store.sources()}
    else:
        result=store.subscribe(args.pack_id,args.action=='subscribe',getattr(args,'version',None))
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0
