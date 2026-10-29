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
            db.executescript('''
                CREATE TABLE IF NOT EXISTS reader_items (
                    id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS reader_batches (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, members TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));
                CREATE TABLE IF NOT EXISTS reader_state (
                    item_id TEXT PRIMARY KEY REFERENCES reader_items(id),
                    completed INTEGER NOT NULL DEFAULT 0, saved INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS reader_subscriptions (
                    pack_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            ''')

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
        return self.batch(batch_id)

    def item(self, item_id):
        with self.db() as db:
            row = db.execute('SELECT payload FROM reader_items WHERE id=?', (item_id,)).fetchone()
            if not row:
                raise ValueError('Unknown reader item')
            state = db.execute('SELECT completed,saved FROM reader_state WHERE item_id=?', (item_id,)).fetchone()
        return {**json.loads(row['payload']), 'completed': bool(state['completed']) if state else False,
                'saved': bool(state['saved']) if state else False}

    def state(self, item_id, changes):
        if not isinstance(changes, dict) or not changes or set(changes) - {'completed','saved'} or any(type(v) is not bool for v in changes.values()):
            raise ValueError('Expected explicit completed/saved booleans')
        with self.db() as db:
            if not db.execute('SELECT 1 FROM reader_items WHERE id=?',(item_id,)).fetchone():
                raise ValueError('Unknown reader item')
            db.execute('INSERT OR IGNORE INTO reader_state(item_id) VALUES (?)',(item_id,))
            for key, value in changes.items():
                db.execute(f'UPDATE reader_state SET {key}=? WHERE item_id=?',(int(value),item_id))
        return self.item(item_id)

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
                'remaining':sum(not i['completed'] for i in items)}

    def library(self):
        with self.db() as db:
            ids = [r['item_id'] for r in db.execute('SELECT item_id FROM reader_state WHERE saved=1 OR completed=1 ORDER BY rowid DESC')]
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
            return {'id':pack_id,'subscribed':False}
        pack = next((p for p in self.packs() if p['id']==pack_id),None)
        if not pack or version != pack['version']:
            raise ValueError('Inspect and select a known pack version before subscribing')
        pack.pop('subscribed_version',None)
        with self.db() as db:
            db.execute('INSERT OR REPLACE INTO reader_subscriptions VALUES (?,?)',
                       (pack_id,json.dumps(pack,ensure_ascii=False,sort_keys=True)))
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
    publish = sub.add_parser('publish')
    publish.add_argument('--batch-id',required=True)
    publish.add_argument('--title',required=True)
    publish.add_argument('--evidence-id',action='append',required=True)
    publish.add_argument('--media-json',help='JSON mapping evidence ID to audio/video paths relative to media root')
    publish.add_argument('--limit',type=int,default=20)
    sub.add_parser('sources')
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
        run(store,args.port,Path(args.media_root))
        return 0
    if args.action=='collect':
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
