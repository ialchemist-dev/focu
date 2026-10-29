import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from focu.reader import ReaderStore, StateConflict
from focu.reader_server import handler
from focu.intents import IntentStore
from focu.evidence import EvidenceStore
from focu.delivery import DeliveryArchive
from focu.data_sync import DataSync, ArtifactCache, restore
from focu.git_journal import GitJournal
from focu.drive_storage import DriveStorage


class MemoryDrive:
    def __init__(self):self.objects={};self.uploads=0;self.downloads=0;self.fail=False
    def verify_folder(self):return True
    def upload(self,path,artifact_id,mime):
        if self.fail:raise RuntimeError('offline')
        data=Path(path).read_bytes();sha=hashlib.sha256(data).hexdigest()
        key=hashlib.sha256((artifact_id+sha).encode()).hexdigest()
        if key not in self.objects:self.objects[key]=data;self.uploads+=1
        return {'file_id':key,'sha256':sha,'size':len(data),'mime':mime}
    def download(self,record,path):
        if self.fail:raise RuntimeError('offline')
        data=self.objects[record['file_id']]
        if hashlib.sha256(data).hexdigest()!=record['sha256']:raise RuntimeError('corrupt')
        self.downloads+=1;Path(path).parent.mkdir(parents=True,exist_ok=True);Path(path).write_bytes(data)
        return Path(path)


def git(path,*args):
    return subprocess.run(['git','-C',str(path),*args],capture_output=True,text=True,check=True).stdout.strip()


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.media=self.root/'media';self.media.mkdir();(self.media/'episode.mp3').write_bytes(b'0123456789')
        self.store=ReaderStore(self.root/'focu.sqlite3')
        intents=IntentStore(self.store.path);intent=intents.capture('Original question')
        pack={'schema_version':'0.2','id':'ev_sync','intent_id':intent['id'],'summary':'Summary',
              'findings':[{'claim':'Fact','source_ids':['s']}],
              'sources':[{'id':'s','title':'Original','url':'https://example.org/post','extracted_text':'Fact'}],
              'created_at':'2026-10-28T00:00:00Z'}
        EvidenceStore(self.store.path).save(pack);intents.transition(intent['id'],'queued','researching')
        intents.transition(intent['id'],'researching','completed',evidence_pack_id=pack['id'])
        DeliveryArchive(self.store.path).archive_report(pack['id'])
        self.store.publish('batch','Edition',[pack['id']],media={pack['id']:{'audio':'episode.mp3'}})
        bare=self.root/'remote.git';bare.mkdir();git(bare,'init','--bare','--initial-branch=main')
        self.repo=self.root/'metadata';subprocess.run(['git','clone',str(bare),str(self.repo)],capture_output=True,check=True)
        (self.repo/'README.md').write_text('Private metadata fixture')
        git(self.repo,'add','README.md');git(self.repo,'-c','user.name=Test','-c','user.email=test@localhost','commit','-m','Initialize')
        git(self.repo,'push','origin','main')
        self.journal=GitJournal(self.repo,verify_private=False);self.drive=MemoryDrive()
        self.sync=DataSync(self.store,self.media,self.drive,self.journal)

    def test_atomic_state_retries_revisions_and_archive_timestamps(self):
        revision=self.store.item('ev_sync')['revision']
        first=self.store.state('ev_sync',{'completed':True,'archived':True,'position_seconds':12},event_id='event1',expected_revision=revision)
        self.assertIsNotNone(first['read_at']);self.assertIsNotNone(first['archived_at'])
        self.assertEqual(self.store.state('ev_sync',{'completed':True,'archived':True,'position_seconds':12},event_id='event1',expected_revision=revision)['revision'],first['revision'])
        with self.assertRaises(StateConflict):self.store.state('ev_sync',{'saved':True},expected_revision=revision)
        with self.assertRaises(ValueError):self.store.state('ev_sync',{'saved':True},event_id='event1')
        self.assertFalse(self.store.item('ev_sync')['saved'])
        self.assertEqual(self.store.batch('batch')['remaining'],0)
        self.store.state('ev_sync',{'completed':False,'archived':False})
        self.assertEqual(self.store.batch('batch')['remaining'],1)
        with patch('focu.reader.sync_events.append',side_effect=RuntimeError('disk full')):
            with self.assertRaises(RuntimeError):self.store.state('ev_sync',{'saved':True})
        self.assertFalse(self.store.item('ev_sync')['saved'])

    def test_end_to_end_recovery_cache_and_state_only_checkpoint_reuse(self):
        self.sync.run();uploaded=self.drive.uploads
        baseline=json.loads((self.repo/'focu/catalog.json').read_text())['checkpoint']
        self.store.state('ev_sync',{'saved':True,'completed':True,'position_seconds':42},event_id='read1')
        result=self.sync.run();self.assertEqual(self.drive.uploads,uploaded)
        self.assertEqual(result['checkpoint'],baseline)
        self.assertEqual(self.store.sync_status()['pending_events'],0)
        catalog=json.loads((self.repo/'focu/catalog.json').read_text())
        self.assertNotIn('markdown',catalog['items'][0]);self.assertNotIn('extracted_text',catalog['items'][0]['sources'][0])
        self.assertFalse(any(p.suffix in ('.mp3','.sqlite3','.gz') for p in (self.repo/'focu').rglob('*')))
        destination=self.root/'recovered/state.sqlite3';new_media=self.root/'recovered/media'
        restore(self.journal,self.drive,destination,new_media)
        restored=ReaderStore(destination);item=restored.item('ev_sync')
        self.assertTrue(item['completed']);self.assertTrue(item['saved']);self.assertEqual(item['position_seconds'],42)
        self.assertIn('Fact',item['markdown']);self.assertEqual(restored.sync_status()['pending_events'],0)
        path=ArtifactCache(restored,new_media,self.drive).ensure('episode.mp3')
        self.assertEqual(path.read_bytes(),b'0123456789')
        with self.assertRaises(ValueError):restore(self.journal,self.drive,destination,new_media)

    def test_archived_cover_is_recoverable_without_original_publisher(self):
        cover=self.media/'cover.jpg';cover.write_bytes(b'original cover fixture')
        self.store.set_cover('ev_sync','https://example.org/cover.jpg','https://example.org/post')
        with patch('focu.data_sync.mirror',return_value=cover):self.sync.run()
        item=self.store.item('ev_sync');self.assertTrue(item['cover']['cache_url'].startswith('/cover?id='))
        cover.unlink()
        with patch('focu.data_sync.mirror',side_effect=AssertionError('Publisher should not be needed again')):
            self.sync.run()
        self.assertEqual(cover.read_bytes(),b'original cover fixture')
        destination=self.root/'cover-recovery/state.sqlite3';media=self.root/'cover-recovery/media'
        restore(self.journal,self.drive,destination,media,download_media=True)
        self.assertEqual((media/'cover.jpg').read_bytes(),b'original cover fixture')
        self.assertEqual((media/'episode.mp3').read_bytes(),b'0123456789')

    def test_wal_database_and_new_content_create_a_new_restorable_baseline(self):
        with self.store.db() as db:db.execute('PRAGMA journal_mode=WAL')
        self.sync.run();first=json.loads((self.repo/'focu/catalog.json').read_text())['checkpoint']
        intents=IntentStore(self.store.path);intent=intents.capture('New research')
        pack={'schema_version':'0.2','id':'ev_new','intent_id':intent['id'],'summary':'New summary','findings':[{'claim':'New fact','source_ids':['s']}],'sources':[{'id':'s','title':'New','url':'https://example.org/new'}],'created_at':'2026-10-29T00:00:00Z'}
        EvidenceStore(self.store.path).save(pack);intents.transition(intent['id'],'queued','researching');intents.transition(intent['id'],'researching','completed',evidence_pack_id='ev_new');DeliveryArchive(self.store.path).archive_report('ev_new')
        self.store.publish('batch2','New edition',['ev_new'])
        self.sync.run();second=json.loads((self.repo/'focu/catalog.json').read_text())['checkpoint']
        self.assertNotEqual(first['content_digest'],second['content_digest'])
        target=self.root/'wal-recovery.sqlite3';restore(self.journal,self.drive,target,self.root/'wal-media')
        self.assertEqual(len(ReaderStore(target).batches()),2)
        self.assertIn('New fact',ReaderStore(target).item('ev_new')['markdown'])

    def test_network_failure_and_new_events_during_push_remain_pending(self):
        self.drive.fail=True
        with self.assertRaises(RuntimeError):self.sync.run()
        self.assertGreater(self.store.sync_status()['pending_events'],0)
        self.assertIsNotNone(self.store.sync_status()['last_error'])
        self.drive.fail=False
        original=self.journal.publish
        def publish(catalog,events):
            self.store.state('ev_sync',{'saved':True},event_id='during-sync')
            return original(catalog,events)
        with patch.object(self.journal,'publish',side_effect=publish):self.sync.run()
        self.assertEqual(self.store.sync_status()['pending_events'],1)
        self.sync.run();self.assertEqual(self.store.sync_status()['pending_events'],0)

    def test_push_failure_retry_and_remote_divergence_preserve_data(self):
        original=self.journal.git
        def failing(*args):
            if args[0]=='push':raise RuntimeError('offline')
            return original(*args)
        with patch.object(self.journal,'git',side_effect=failing):
            with self.assertRaises(RuntimeError):self.sync.run()
        self.assertGreater(self.store.sync_status()['pending_events'],0)
        uploads=self.drive.uploads
        self.sync.run();self.assertEqual(self.store.sync_status()['pending_events'],0)
        self.assertEqual(self.drive.uploads,uploads)
        clone=self.root/'other';subprocess.run(['git','clone',str(self.root/'remote.git'),str(clone)],capture_output=True,check=True)
        (clone/'other.txt').write_text('other writer');git(clone,'add','.');git(clone,'-c','user.name=Test','-c','user.email=test@localhost','commit','-m','Other writer');git(clone,'push','origin','main')
        self.store.state('ev_sync',{'saved':True})
        with self.assertRaises(RuntimeError):self.sync.run()
        self.assertGreater(self.store.sync_status()['pending_events'],0)

    def test_https_origin_and_lazy_media_range(self):
        self.sync.run();(self.media/'episode.mp3').unlink()
        server=ThreadingHTTPServer(('127.0.0.1',0),handler(self.store,self.media,public_origin='https://reader.example.ts.net',drive=self.drive))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        def request(method,path,payload=None,origin='https://reader.example.ts.net'):
            conn=HTTPConnection('127.0.0.1',server.server_port)
            headers={'Host':'reader.example.ts.net','Origin':origin,'Content-Type':'application/json','X-Focu-Reader':'1','Range':'bytes=2-5'}
            conn.request(method,path,json.dumps(payload) if payload else None,headers)
            response=conn.getresponse();result=(response.status,response.read());conn.close();return result
        self.assertEqual(request('GET','/media?id=ev_sync&kind=audio'),(206,b'2345'))
        revision=self.store.item('ev_sync')['revision']
        payload={'id':'ev_sync','changes':{'saved':True},'event_id':'https1','expected_revision':revision}
        self.assertEqual(request('POST','/api/state',payload)[0],200)
        self.assertEqual(request('POST','/api/state',{**payload,'event_id':'https2'})[0],409)
        self.assertEqual(request('POST','/api/state',payload,origin='https://evil.example')[0],403)
        self.assertEqual(request('GET','/api/sync-status')[0],200)


class DriveTests(unittest.TestCase):
    def test_verified_upload_retry_and_corrupt_download(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'audio.mp3';path.write_bytes(b'audio');sha,md5,size=DriveStorage.hashes(path)
            client=DriveStorage.__new__(DriveStorage);client.config={'folder_id':'folder'};client.access_token='test'
            info={'id':'file1','size':str(size),'md5Checksum':md5}
            class Response(io.BytesIO):
                status=200
                def __init__(self,data,headers=None):super().__init__(data);self.headers=headers or {}
            replies=[Response(b'',{'Location':'https://www.googleapis.com/upload/session'}),Response(json.dumps(info).encode())]
            with patch.object(client,'json',return_value={'files':[]}),patch.object(client,'request',side_effect=replies):
                record=client.upload(path,'artifact','audio/mpeg')
            self.assertEqual(record['sha256'],sha)
            with patch.object(client,'json',return_value={'files':[info]}),patch.object(client,'request') as request:
                self.assertEqual(client.upload(path,'artifact','audio/mpeg'),record);request.assert_not_called()
            destination=Path(d)/'cached.mp3';destination.write_bytes(b'old')
            with patch.object(client,'request',return_value=Response(b'corrupt')):
                with self.assertRaises(RuntimeError):client.download(record,destination)
            self.assertEqual(destination.read_bytes(),b'old')

    def test_shared_drive_folder_is_not_silently_used(self):
        client=DriveStorage.__new__(DriveStorage);client.config={'folder_id':'folder'}
        folder={'mimeType':'application/vnd.google-apps.folder','capabilities':{'canAddChildren':True}}
        with patch.object(client,'json',side_effect=[folder,{'permissions':[{'id':'public','type':'anyone','role':'reader'}]}]):
            with self.assertRaises(ValueError):client.verify_folder()
        with patch.object(client,'json',side_effect=[folder,{'permissions':[{'id':'owner','type':'user','role':'owner'}]}]):
            self.assertTrue(client.verify_folder())

    def test_public_repository_and_credential_permissions_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'config.json';p.write_text('{}');p.chmod(0o644)
            with self.assertRaises(ValueError):DriveStorage(p)
        journal=GitJournal('/unused')
        def fake(*args):
            return {'status':'','branch':'main','remote':'https://github.com/example/public.git'}[args[0]]
        response=io.BytesIO(b'{"private":false}')
        with patch.object(journal,'git',side_effect=fake),patch.dict(os.environ,{'FOCU_GITHUB_TOKEN':'test'}),patch('focu.git_journal.urllib.request.urlopen',return_value=response):
            with self.assertRaises(ValueError):journal.prepare()

class CoverArchiveTests(unittest.TestCase):
    def test_private_addresses_are_rejected_before_fetch(self):
        from focu.cover_archive import validate_public
        with patch('focu.cover_archive.socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]):
            with self.assertRaises(ValueError):validate_public('https://example.org/cover.jpg')
        for url in ('http://example.org/a','https://user:secret@example.org/a','https://example.org:8443/a'):
            with self.assertRaises(ValueError):validate_public(url)

class HostingTests(unittest.TestCase):
    def test_units_preserve_origin_and_do_not_embed_credentials(self):
        from focu.hosting import units
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            result=units(root/'checkout',root/'state.sqlite3',root/'media',root/'repo',root/'private.json',root/'private.env','https://reader.example.ts.net',root/'units')
            text=(root/'units/focu-reader.service').read_text()
            self.assertIn('--public-origin "https://reader.example.ts.net"',text)
            self.assertIn('--drive-config',text)
            self.assertIn('sync watch',(root/'units/focu-sync.service').read_text())
            self.assertFalse(result['installed'])
            self.assertNotIn('Funnel',result['serve_command'])
            with self.assertRaises(ValueError):units(root,root/'db',root,root,root/'creds',root/'env','https://user:secret@example.org',root/'units')

class ResumableDriveTests(unittest.TestCase):
    def test_multi_chunk_upload_uses_server_offset_and_final_checksum(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'large.mp3';path.write_bytes(b'a'*(8*1024*1024)+b'tail')
            sha,md5,size=DriveStorage.hashes(path)
            client=DriveStorage.__new__(DriveStorage);client.config={'folder_id':'folder'};client.access_token='test'
            class Response(io.BytesIO):
                def __init__(self,data=b'',status=200,headers=None):super().__init__(data);self.status=status;self.headers=headers or {}
            responses=[Response(headers={'Location':'https://www.googleapis.com/upload/session'}),
                       Response(status=308,headers={'Range':'bytes=0-8388607'}),
                       Response(json.dumps({'id':'file','size':str(size),'sha256Checksum':sha}).encode())]
            with patch.object(client,'json',return_value={'files':[]}),patch.object(client,'request',side_effect=responses) as request:
                record=client.upload(path,'large','audio/mpeg')
            self.assertEqual(record['sha256'],sha)
            self.assertEqual(request.call_args_list[-1].kwargs['data'],b'tail')
            self.assertEqual(request.call_args_list[-1].kwargs['headers']['Content-Range'],f'bytes 8388608-{size-1}/{size}')

class UploadResumeTests(unittest.TestCase):
    def test_interrupted_upload_reuses_private_session_and_server_offset(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);path=root/'file.mp3';path.write_bytes(b'abcdefgh')
            sha,md5,size=DriveStorage.hashes(path)
            client=DriveStorage.__new__(DriveStorage);client.config={'folder_id':'folder'};client.access_token='test';client.session_dir=root/'sessions';client.session_dir.mkdir()
            class Response(io.BytesIO):
                def __init__(self,data=b'',status=200,headers=None):super().__init__(data);self.status=status;self.headers=headers or {}
            initial=Response(headers={'Location':'https://www.googleapis.com/upload/session'})
            with patch.object(client,'json',return_value={'files':[]}),patch.object(client,'request',side_effect=[initial,RuntimeError('offline')]):
                with self.assertRaises(RuntimeError):client.upload(path,'artifact','audio/mpeg')
            self.assertEqual(len(list(client.session_dir.glob('*.json'))),1)
            final=Response(json.dumps({'id':'file','size':str(size),'sha256Checksum':sha}).encode())
            with patch.object(client,'json',return_value={'files':[]}),patch.object(client,'request',side_effect=[Response(status=308,headers={'Range':'bytes=0-3'}),final]) as request:
                client.upload(path,'artifact','audio/mpeg')
            self.assertTrue(all(call.args[0]=='PUT' for call in request.call_args_list))
            self.assertEqual(request.call_args_list[-1].kwargs['data'],b'efgh')
            self.assertEqual(list(client.session_dir.glob('*.json')),[])
