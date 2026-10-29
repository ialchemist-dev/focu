import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from focu.reader import ReaderStore
from focu.reader_server import handler
from focu.intents import IntentStore
from focu.evidence import EvidenceStore
from focu.delivery import DeliveryArchive


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.path=self.root/'focu.sqlite3'
        self.store=ReaderStore(self.path)
        self.add_report('ev_a');self.add_report('ev_b')

    def add_report(self,eid):
        intents=IntentStore(self.path);intent=intents.capture('Question '+eid)
        pack={'schema_version':'0.2','id':eid,'intent_id':intent['id'],'summary':'A summary',
              'findings':[{'claim':'Fact','source_ids':['s']}],
              'sources':[{'id':'s','title':'Original','url':'https://example.org/post'}],
              'created_at':'2026-10-28T00:00:00Z'}
        EvidenceStore(self.path).save(pack)
        intents.transition(intent['id'],'queued','researching')
        intents.transition(intent['id'],'researching','completed',evidence_pack_id=eid)
        DeliveryArchive(self.path).archive_report(eid)

    def test_finite_batch_and_state_survive_restart_and_formats(self):
        args=('batch','Reading',['ev_a'])
        media={'ev_a':{'audio':'episodes/a.mp3'}}
        self.store.publish(*args,media=media)
        self.assertEqual(self.store.publish(*args,media=media)['remaining'],1)
        self.store.state('ev_a',{'completed':True,'saved':True})
        reopened=ReaderStore(self.path)
        self.assertEqual(reopened.batch('batch')['remaining'],0)
        self.assertEqual(len(reopened.library()),1)
        reopened.publish('batch2','Another',['ev_a'],media=media)
        self.assertEqual(reopened.batch('batch2')['remaining'],0)
        reopened.state('ev_a',{'completed':False})
        self.assertEqual(reopened.batch('batch')['remaining'],1)
        self.assertTrue(reopened.item('ev_a')['saved'])

    def test_conflicts_rollback_all_items(self):
        self.store.publish('batch','Reading',['ev_a'])
        with self.assertRaises(ValueError):self.store.publish('batch','Changed',['ev_a','ev_b'])
        with self.assertRaises(ValueError):self.store.item('ev_b')
        self.assertEqual(len(self.store.batches()),1)
        with self.assertRaises(ValueError):self.store.publish('x','Too many',['ev_a','ev_b'],limit=1)
        self.assertEqual(len(self.store.batches()),1)

    def test_rejects_invalid_media_unknown_and_unfinished_research(self):
        with self.assertRaises(ValueError):self.store.publish('x','X',['ev_a'],media={'ev_a':{'audio':'../secret.mp3'}})
        with self.assertRaises(ValueError):self.store.state('unknown',{'saved':True})
        with self.assertRaises(ValueError):self.store.state('ev_a',{'saved':'true'})
        with self.store.db() as db:db.execute("UPDATE intents SET status='researching'")
        with self.assertRaises(ValueError):self.store.publish('x','X',['ev_a'])

    def test_overlapping_packs_pin_membership_and_unsubscribe(self):
        packs=self.root/'packs';packs.mkdir()
        def write(pid,version,urls):
            (packs/(pid+'.json')).write_text(json.dumps({'id':pid,'version':version,'sources':[
                {'name':'Author','site_url':url,'feed_url':url+'/feed','channel':'research','type':'rss'} for url in urls]}))
        write('a','1',['https://example.org']);write('b','1',['https://example.org','https://other.org'])
        with patch('focu.reader.PACKS',packs):
            self.store.subscribe('a',True,'1');self.store.subscribe('a',True,'1');self.store.subscribe('b',True,'1')
            self.assertEqual(len(self.store.sources()),2)
            write('a','2',['https://new.org'])
            self.assertEqual(len(self.store.sources()),2)
            with self.assertRaises(ValueError):self.store.subscribe('a',True,'1')
            self.store.subscribe('b',False)
            self.assertEqual(self.store.sources()[0]['site_url'],'https://example.org')
            self.store.subscribe('a',True,'2')
            self.assertEqual(self.store.sources()[0]['site_url'],'https://new.org')

    def test_http_state_origin_range_and_media_traversal(self):
        (self.root/'a.mp3').write_bytes(b'0123456789')
        self.store.publish('batch','Reading',['ev_a'],media={'ev_a':{'audio':'a.mp3'}})
        server=ThreadingHTTPServer(('127.0.0.1',0),handler(self.store,self.root))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        def request(method,path,body=None,headers=None):
            conn=HTTPConnection('127.0.0.1',server.server_port)
            conn.request(method,path,json.dumps(body) if body else None,headers or {})
            r=conn.getresponse();result=(r.status,r.read(),dict(r.getheaders()));conn.close();return result
        self.assertEqual(request('GET','/api/batches')[0],200)
        for _ in range(2):self.assertEqual(request('GET','/api/batch?id=batch')[0],200)
        self.assertEqual(len(self.store.batches()),1)
        payload={'id':'ev_a','changes':{'completed':True}}
        self.assertEqual(request('POST','/api/state',payload)[0],403)
        hdr={'Content-Type':'application/json','X-Focu-Reader':'1','Origin':'https://evil.example'}
        self.assertEqual(request('POST','/api/state',payload,hdr)[0],403)
        del hdr['Origin']
        self.assertEqual(request('POST','/api/state',payload,hdr)[0],200)
        self.assertEqual(request('GET','/media?id=ev_a&kind=audio',headers={'Range':'bytes=2-5'})[:2],(206,b'2345'))
        self.assertEqual(request('GET','/media?id=ev_a&kind=audio',headers={'Range':'bytes=99-'})[0],416)
        self.assertEqual(request('GET','/../reader.py')[0],404)
        self.assertEqual(request('GET','/api/batches',headers={'Host':'evil.example'})[0],403)
        external=self.root.parent/(self.root.name+'-secret.mp3');external.write_bytes(b'secret');self.addCleanup(external.unlink)
        (self.root/'a.mp3').unlink();(self.root/'a.mp3').symlink_to(external)
        self.assertEqual(request('GET','/media?id=ev_a&kind=audio')[0],404)


if __name__=='__main__':unittest.main()
