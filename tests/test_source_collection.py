import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from focu.reader import ReaderStore
from focu.source_collection import collect,acknowledge,parse_feed

RSS=b'<rss><channel><item><title>A</title><link>https://example.org/a</link><description>&lt;p&gt;Fact&lt;/p&gt;</description></item></channel></rss>'
ATOM=b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>B</title><link href="/b"/><summary>Text</summary></entry></feed>'
class Response(BytesIO):
    def geturl(self):return 'https://example.org/feed'
class CollectionTests(unittest.TestCase):
    def test_feeds_and_html_failure(self):
        self.assertEqual(parse_feed(RSS,'https://example.org/feed')[0]['text'],'Fact')
        self.assertEqual(parse_feed(ATOM,'https://example.org/feed')[0]['url'],'https://example.org/b')
        with self.assertRaises(ValueError):parse_feed(b'<html/>','https://example.org/feed')
    def test_pending_queue_retries_partial_failures_and_explicit_ack(self):
        with tempfile.TemporaryDirectory() as d:
            store=ReaderStore(Path(d)/'focu.sqlite3');output=Path(d)/'out.json'
            sources=[{'name':'One','feed_url':'https://example.org/feed'}, {'name':'Broken','feed_url':'https://bad.example/feed'}, {'name':'Disabled','enabled':False}]
            def fetch(req,**kw):
                if 'bad.example' in req.full_url:raise OSError('unavailable')
                return Response(RSS)
            with patch.object(store,'sources',return_value=sources),patch('focu.source_collection.urlopen',side_effect=fetch):
                self.assertEqual(collect(store,output)['pending'],1)
                result=collect(store,output)
                self.assertEqual(result['pending'],1)
                self.assertEqual([s['status'] for s in result['sources']],['collected','failed','disabled_or_no_feed'])
                record=json.loads(output.read_text())['pending'][0]
                with self.assertRaises(ValueError):acknowledge(store,[record['id'],'unknown'])
                self.assertEqual(collect(store,output)['pending'],1)
                acknowledge(store,[record['id']])
                self.assertEqual(collect(store,output)['pending'],0)
                self.assertEqual(store.batches(),[])
