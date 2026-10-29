"""Transactional, idempotent state events and durable sync status."""
import json
import uuid
from focu.intents import utcnow


def initialize(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS sync_events (
            seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT UNIQUE NOT NULL,
            target TEXT NOT NULL, operation TEXT NOT NULL, changes TEXT NOT NULL,
            created_at TEXT NOT NULL, synced INTEGER NOT NULL DEFAULT 0);
        CREATE INDEX IF NOT EXISTS idx_sync_target ON sync_events(target,seq);
        CREATE INDEX IF NOT EXISTS idx_sync_pending ON sync_events(synced,seq);
        CREATE TABLE IF NOT EXISTS sync_meta (key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sync_artifacts (
            artifact_id TEXT PRIMARY KEY, item_id TEXT NOT NULL, kind TEXT NOT NULL,
            relative_path TEXT, record TEXT NOT NULL);
    ''')


def append(db,target,operation,changes,event_id=None):
    event_id=event_id or str(uuid.uuid4())
    if not isinstance(event_id,str) or not 1<=len(event_id)<=128:
        raise ValueError('Invalid event ID')
    data=json.dumps(changes,sort_keys=True,separators=(',',':'))
    row=db.execute('SELECT * FROM sync_events WHERE event_id=?',(event_id,)).fetchone()
    if row:
        if (row['target'],row['operation'],row['changes'])!=(target,operation,data):
            raise ValueError('Event ID reused with different content')
        return row['seq']
    cur=db.execute('INSERT INTO sync_events(event_id,target,operation,changes,created_at) VALUES (?,?,?,?,?)',
                   (event_id,target,operation,data,utcnow()))
    return cur.lastrowid


def status(db):
    rows={r['key']:json.loads(r['value']) for r in db.execute('SELECT * FROM sync_meta')}
    pending=db.execute('SELECT count(*) FROM sync_events WHERE synced=0').fetchone()[0]
    revision=db.execute('SELECT coalesce(max(seq),0) FROM sync_events').fetchone()[0]
    return {'pending_events':pending,'revision':revision,'configured':bool(rows.get('configured')),
            'last_success_at':rows.get('last_success_at'),'last_error':rows.get('last_error'),
            'syncing':bool(rows.get('syncing')),'warnings':rows.get('warnings',[])}


def meta(db,key,value):
    db.execute('INSERT OR REPLACE INTO sync_meta VALUES (?,?)',(key,json.dumps(value)))
