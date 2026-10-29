"""Bounded opt-in RSS/Atom collection into a durable raw-material queue, not evidence."""
import hashlib
import json
import re
from html import unescape
from urllib.request import Request,urlopen
from urllib.parse import urljoin
from xml.etree import ElementTree as ET
from focu.reader import canonical_url
from focu.intents import utcnow


def parse_feed(data,base_url):
    root=ET.fromstring(data)
    atom='{http://www.w3.org/2005/Atom}'
    if root.tag not in {'rss',atom+'feed','{http://www.w3.org/1999/02/22-rdf-syntax-ns#}RDF'}:
        raise ValueError('Response is not RSS or Atom')
    entries=root.findall('.//item') or root.findall(atom+'entry')
    records=[]
    for e in entries:
        title=e.findtext('title') or e.findtext(atom+'title') or 'Untitled'
        url=e.findtext('link')
        if not url:
            url=next((l.get('href') for l in e.findall(atom+'link') if l.get('rel','alternate')=='alternate'),None)
        if not url:continue
        url=canonical_url(urljoin(base_url,url))
        text=e.findtext('{http://purl.org/rss/1.0/modules/content/}encoded') or e.findtext('description') or e.findtext(atom+'content') or e.findtext(atom+'summary') or title
        text=unescape(re.sub('<[^>]+>',' ',text))
        text=re.sub(r'\s+',' ',text).strip()
        published=e.findtext('pubDate') or e.findtext(atom+'published') or e.findtext(atom+'updated')
        records.append({'url':url,'title':title,'text':text,'published_at':published})
    return records


def collect(store,output):
    with store.db() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS reader_raw_queue (
            id TEXT PRIMARY KEY, payload TEXT NOT NULL, acknowledged INTEGER NOT NULL DEFAULT 0)''')
    results=[]
    for source in store.sources():
        if not source.get('enabled',True) or not source.get('feed_url'):
            results.append({'source':source['name'],'status':'disabled_or_no_feed'});continue
        try:
            req=Request(source['feed_url'],headers={'User-Agent':'Focu/0.2 (+explicit source collection)'})
            with urlopen(req,timeout=15) as response:
                data=response.read(2_000_001)
                if len(data)>2_000_000:raise ValueError('Feed exceeds 2 MB')
                records=parse_feed(data,response.geturl())
            for record in records:
                record_id=hashlib.sha256((record['url']+'\n'+record['title']+'\n'+record['text']).encode()).hexdigest()
                payload={**record,'id':record_id,'source':source['name'],'method':'rss_or_atom',
                         'collected_at':utcnow(),'evidence_status':'unverified_raw_material'}
                with store.db() as db:
                    db.execute('INSERT OR IGNORE INTO reader_raw_queue(id,payload) VALUES (?,?)',
                               (record_id,json.dumps(payload,ensure_ascii=False)))
            results.append({'source':source['name'],'status':'collected','items':len(records)})
        except Exception as exc:
            results.append({'source':source['name'],'status':'failed','error':str(exc)})
    with store.db() as db:
        pending=[json.loads(r['payload']) for r in db.execute('SELECT payload FROM reader_raw_queue WHERE acknowledged=0 ORDER BY rowid')]
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps({'collection':results,'pending':pending},ensure_ascii=False,indent=2)+'\n')
    return {'sources':results,'pending':len(pending),'output':str(output)}


def acknowledge(store,ids):
    with store.db() as db:
        for record_id in ids:
            if db.execute('SELECT 1 FROM reader_raw_queue WHERE id=?',(record_id,)).fetchone() is None:
                raise ValueError('Unknown raw record ID')
            db.execute('UPDATE reader_raw_queue SET acknowledged=1 WHERE id=?',(record_id,))
    return {'acknowledged':len(ids)}
