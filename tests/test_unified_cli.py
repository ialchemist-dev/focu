"""Integration of the previously independent CLI branches."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from focu.cli import main
from focu.web import FetchError, WebPage, fetch_page
from unittest.mock import patch

class UnifiedCLITests(unittest.TestCase):
    def run_cli(self,*args):
        output=io.StringIO()
        with contextlib.redirect_stdout(output):
            status=main(list(args))
        return status,json.loads(output.getvalue())

    def test_daily_reader_and_research_stores_remain_separate(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);db=root/'research.sqlite3'
            self.assertEqual(self.run_cli('--db',str(db),'init')[0],0)
            status,value=self.run_cli('--db',str(db),'daily','status','--data-dir',str(root/'daily'),'--json')
            self.assertEqual((status,value['status']),(0,'not_initialized'))
            self.assertEqual(self.run_cli('--db',str(db),'reader','sources'),(0,{'sources':[]}))
            (root/'posts.json').write_text('{"posts": []}')
            status,value=self.run_cli('--db',str(db),'collect','linkedin-export','--input',str(root/'posts.json'),'--scope','test','--output',str(root/'collected.json'))
            self.assertEqual((status,value['total']),(0,0))
            self.assertTrue(db.exists());self.assertFalse((root/'daily/few.sqlite3').exists())

    def test_registered_example_sources_remain_loadable(self):
        from focu.daily.config import load_config
        path = Path(__file__).resolve().parents[1] / 'examples/sources.yaml'
        cfg = load_config(path)
        sections = [source for source in cfg['sources'] if source['name'].startswith('Anthropic ')]
        self.assertEqual(len(sections), 3)
        self.assertTrue(all(source['type'] == 'blog' and source['site_url'].startswith('https://www.anthropic.com/') for source in sections))

    def test_fetch_snapshot_cli_and_structured_error(self):
        with tempfile.TemporaryDirectory() as d:
            page=WebPage('https://example.org','Title','captured text',200,'text/html')
            with patch('focu.cli.fetch_page',return_value=page):
                status,value=self.run_cli('fetch',page.url,'--snapshot-dir',d,'--retries','1')
            self.assertEqual(status,0)
            self.assertEqual(self.run_cli('verify-snapshot',value['snapshot']['path'],value['snapshot']['sha256']),(0,{'valid':True}))
            errors=io.StringIO()
            with patch('focu.cli.fetch_page',side_effect=FetchError('limited',category='rate_limit',status=429)),contextlib.redirect_stderr(errors):
                self.assertEqual(main(['fetch',page.url]),1)
            self.assertEqual(json.loads(errors.getvalue())['http_status'],429)

    def test_bounded_transient_retry_and_no_retry_for_forbidden(self):
        page=WebPage('https://example.org','Title','text',200,'text/html')
        with patch('focu.web._retrieve',side_effect=[FetchError('retry',category='server',status=503),page]) as retrieve,patch('focu.web.time.sleep'):
            self.assertEqual(fetch_page(page.url,retries=1),page)
            self.assertEqual(retrieve.call_count,2)
        with patch('focu.web._retrieve',side_effect=FetchError('forbidden',category='http',status=403)) as retrieve,patch('focu.web.time.sleep') as sleep:
            with self.assertRaises(FetchError):fetch_page(page.url,retries=5)
            self.assertEqual(retrieve.call_count,1);sleep.assert_not_called()
