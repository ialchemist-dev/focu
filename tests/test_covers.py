import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from focu.covers import image_url, source_cover
from focu.source_collection import parse_feed, collect, acknowledge
from focu.reader import ReaderStore
from focu.evidence import EvidenceStore
from focu.intents import IntentStore
from focu.delivery import DeliveryArchive
from focu.web import _TextParser
from io import BytesIO

class CoverTests(unittest.TestCase):
    def test_feed_images_preserve_original_attribution(self):
        rss=b'<rss xmlns:media="http://search.yahoo.com/mrss/"><channel><item><title>A</title><link>https://example.org/post</link><media:content url="https://cdn.example.org/photo.jpg" medium="image"/><description>Text</description></item></channel></rss>'
        record=parse_feed(rss,'https://example.org/feed')[0]
        self.assertEqual(record['image_url'],'https://cdn.example.org/photo.jpg')
        self.assertEqual(record['url'],'https://example.org/post')
        html=b'<rss><channel><item><title>A</title><link>https://example.org/post</link><description>&lt;p&gt;Text&lt;/p&gt;&lt;img src="/photo.jpg" alt="Original"/&gt;</description></item></channel></rss>'
        self.assertEqual(parse_feed(html,'https://example.org/feed')[0]['image_url'],'https://example.org/photo.jpg')
        self.assertEqual(parse_feed(html,'https://example.org/feed')[0]['text'],'Text')

    def test_invalid_image_schemes_and_page_metadata(self):
        for url in ('javascript:alert(1)','data:image/png,x','http://example.org/a','https://user:secret@example.org/a'):
            self.assertIsNone(image_url(url))
        p=_TextParser();p.feed('<meta property="og:image" content="/photo.jpg"><title>Title</title>Text')
        self.assertEqual(image_url(p.images['og:image'],'https://example.org/post'),'https://example.org/photo.jpg')
        self.assertIsNone(source_cover([{'url':'https://example.org/post','title':'Title'}]))

    def test_existing_card_can_get_cover_without_changing_evidence_or_state(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'focu.sqlite3';intents=IntentStore(path);intent=intents.capture('Original title')
            pack={'schema_version':'0.2','id':'ev_cover','intent_id':intent['id'],'summary':'Summary','findings':[{'claim':'Fact','source_ids':['s']}],'sources':[{'id':'s','title':'Original','url':'https://example.org/post'}],'created_at':'2026-10-28T00:00:00Z'}
            EvidenceStore(path).save(pack);intents.transition(intent['id'],'queued','researching');intents.transition(intent['id'],'researching','completed',evidence_pack_id=pack['id']);DeliveryArchive(path).archive_report(pack['id'])
            store=ReaderStore(path);store.publish('batch','Title',[pack['id']]);store.state(pack['id'],{'completed':True,'saved':True})
            with store.db() as db:before=db.execute('SELECT payload FROM reader_items').fetchone()[0]
            self.assertIsNone(store.item(pack['id'])['cover'])
            store.set_cover(pack['id'],'https://cdn.example.org/photo.jpg','https://example.org/post','Original photo')
            self.assertTrue(ReaderStore(path).item(pack['id'])['completed']);self.assertTrue(store.item(pack['id'])['saved'])
            self.assertEqual(store.publish('batch','Title',[pack['id']])['remaining'],0)
            with store.db() as db:self.assertEqual(db.execute('SELECT payload FROM reader_items').fetchone()[0],before)
            with self.assertRaises(ValueError):store.set_cover(pack['id'],'https://cdn.example.org/photo.jpg','https://unrelated.example/post')
            with self.assertRaises(ValueError):store.set_cover(pack['id'],'javascript:alert(1)','https://example.org/post')

    def test_repeated_collection_enriches_images_without_requeue(self):
        class Response(BytesIO):
            def geturl(self):return 'https://example.org/feed'
        with tempfile.TemporaryDirectory() as d:
            store=ReaderStore(Path(d)/'focu.sqlite3');output=Path(d)/'queue.json'
            base='<rss><channel><item><title>A</title><link>https://example.org/a</link><description>Text{}</description></item></channel></rss>'
            old=base.format('').encode();new=base.format('&lt;img src="/a.jpg"/&gt;').encode()
            with patch.object(store,'sources',return_value=[{'name':'A','feed_url':'https://example.org/feed'}]),patch('focu.source_collection.urlopen',side_effect=[Response(old),Response(new)]):
                self.assertEqual(collect(store,output)['pending'],1)
                record=json.loads(output.read_text())['pending'][0];acknowledge(store,[record['id']])
                self.assertEqual(collect(store,output)['pending'],0)
            with store.db() as db:
                row=db.execute('SELECT payload,acknowledged FROM reader_raw_queue').fetchone()
            self.assertEqual(json.loads(row['payload'])['image_url'],'https://example.org/a.jpg')
            self.assertEqual(row['acknowledged'],1)
