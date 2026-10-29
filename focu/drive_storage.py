"""Private Google Drive artifact storage. Credentials never enter manifests."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import tempfile
import urllib.error
import urllib.parse
import urllib.request

API='https://www.googleapis.com/drive/v3'
UPLOAD='https://www.googleapis.com/upload/drive/v3'


class DriveStorage:
    def __init__(self,config_path=None):
        path=Path(config_path or os.environ.get('FOCU_DRIVE_CONFIG','data/drive-private.json'))
        if path.stat().st_mode & 0o077:
            raise ValueError('Drive credential file must have owner-only permissions')
        self.config=json.loads(path.read_text())
        if not all(self.config.get(k) for k in ('client_id','client_secret','refresh_token','folder_id')):
            raise ValueError('Drive requires client_id, client_secret, refresh_token and folder_id')
        self.access_token=None
        self.session_dir=path.parent/'focu-drive-sessions'
        self.session_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
        os.chmod(self.session_dir,0o700)

    def _token(self):
        data=urllib.parse.urlencode({k:self.config[k] for k in ('client_id','client_secret','refresh_token')}
                                   | {'grant_type':'refresh_token'}).encode()
        req=urllib.request.Request('https://oauth2.googleapis.com/token',data=data)
        try:
            with urllib.request.urlopen(req,timeout=30) as response:
                self.access_token=json.load(response)['access_token']
        except Exception:
            raise RuntimeError('Drive authorization failed; check private OAuth configuration') from None

    def request(self,method,url,*,data=None,headers=None,retry=True):
        if not self.access_token:self._token()
        req=urllib.request.Request(url,data=data,method=method,
                                  headers={**(headers or {}),'Authorization':'Bearer '+self.access_token})
        try:return urllib.request.urlopen(req,timeout=60)
        except urllib.error.HTTPError as exc:
            if exc.code==401 and retry:
                self._token();return self.request(method,url,data=data,headers=headers,retry=False)
            if exc.code==308:return exc
            raise RuntimeError(f'Drive request failed (HTTP {exc.code})') from None
        except OSError:
            raise RuntimeError('Drive connection unavailable; retry is safe') from None

    def json(self,method,path,body=None):
        data=json.dumps(body).encode() if body is not None else None
        with self.request(method,API+path,data=data,headers={'Content-Type':'application/json'}) as response:
            return json.load(response)

    def verify_folder(self):
        folder=urllib.parse.quote(self.config['folder_id'],safe='')
        info=self.json('GET','/files/'+folder+'?fields=id,mimeType,trashed,capabilities(canAddChildren)')
        if info.get('mimeType')!='application/vnd.google-apps.folder' or info.get('trashed') or not info.get('capabilities',{}).get('canAddChildren'):
            raise ValueError('Drive destination must be an accessible writable folder')
        permissions=self.json('GET','/files/'+folder+'/permissions?fields=permissions(id,type,role)')
        approved=set(self.config.get('allowed_permission_ids',[]))
        for permission in permissions.get('permissions',[]):
            if permission.get('type') in {'anyone','domain'} or (permission.get('role')!='owner' and permission.get('id') not in approved):
                raise ValueError('Drive folder has sharing outside the explicitly approved private permissions')
        return True

    @staticmethod
    def hashes(path):
        sha=hashlib.sha256();md5=hashlib.md5()
        with Path(path).open('rb') as f:
            for block in iter(lambda:f.read(1024*1024),b''):
                sha.update(block);md5.update(block)
        return sha.hexdigest(),md5.hexdigest(),Path(path).stat().st_size

    def upload(self,path,artifact_id,mime='application/octet-stream'):
        path=Path(path);sha,md5,size=self.hashes(path)
        # Content addressing makes retries and simultaneous identical uploads discoverable.
        key=hashlib.sha256((artifact_id+'\n'+sha).encode()).hexdigest()
        state_path=getattr(self,'session_dir',None)
        state_path=state_path/(key+'.json') if state_path else None
        folder=self.config['folder_id']
        if any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in folder):
            raise ValueError('Invalid Drive folder ID')
        q=f"trashed = false and '{folder}' in parents and appProperties has {{ key='focu_key' and value='{key}' }}"
        fields='id,size,md5Checksum,sha256Checksum,appProperties'
        found=self.json('GET','/files?'+urllib.parse.urlencode({'q':q,'fields':'files('+fields+')','pageSize':100}))
        def verified(info):
            return int(info.get('size',-1))==size and (info.get('sha256Checksum')==sha or info.get('md5Checksum')==md5)
        for info in found.get('files',[]):
            if verified(info):
                if state_path:state_path.unlink(missing_ok=True)
                return {'file_id':info['id'],'sha256':sha,'size':size,'mime':mime}
        session=None;offset=0;info=None
        if state_path and state_path.exists():
            saved=json.loads(state_path.read_text())
            candidate=saved.get('session')
            if candidate and urllib.parse.urlsplit(candidate).scheme=='https' and urllib.parse.urlsplit(candidate).hostname=='www.googleapis.com' and not urllib.parse.urlsplit(candidate).username:
                try:
                    with self.request('PUT',candidate,data=b'',headers={'Content-Range':f'bytes */{size}'}) as response:
                        if response.status==308:
                            value=response.headers.get('Range','').rsplit('-',1)[-1]
                            offset=int(value)+1 if value.isdigit() else 0
                            session=candidate
                        else:
                            info=json.load(response)
                            if verified(info):
                                state_path.unlink(missing_ok=True)
                                return {'file_id':info['id'],'sha256':sha,'size':size,'mime':mime}
                except RuntimeError as exc:
                    if not any(code in str(exc) for code in ('HTTP 404','HTTP 410')):raise
                    state_path.unlink(missing_ok=True)
        if session is None:
            metadata={'name':sha+path.suffix,'parents':[folder],
                      'appProperties':{'focu_key':key,'focu_sha256':sha}}
            url=UPLOAD+'/files?uploadType=resumable&fields='+urllib.parse.quote(fields,safe='')
            with self.request('POST',url,data=json.dumps(metadata).encode(),headers={
                'Content-Type':'application/json','X-Upload-Content-Type':mime,'X-Upload-Content-Length':str(size)}) as response:
                session=response.headers.get('Location')
            if not session or urllib.parse.urlsplit(session).scheme!='https' or urllib.parse.urlsplit(session).hostname!='www.googleapis.com' or urllib.parse.urlsplit(session).username:
                raise RuntimeError('Drive returned an invalid resumable upload session')
            if state_path:
                fd,temp=tempfile.mkstemp(prefix='.session-',dir=state_path.parent)
                try:
                    with os.fdopen(fd,'w') as out:json.dump({'session':session},out)
                    os.replace(temp,state_path)
                finally:Path(temp).unlink(missing_ok=True)
        # Resume from the server-confirmed byte offset after a transient interruption.
        with path.open('rb') as f:
            while offset<size or (size==0 and info is None):
                f.seek(offset);chunk=f.read(8*1024*1024)
                content_range=f'bytes {offset}-{offset+len(chunk)-1}/{size}' if size else 'bytes */0'
                with self.request('PUT',session,data=chunk,headers={'Content-Type':mime,'Content-Range':content_range}) as response:
                    if response.status==308:
                        end=response.headers.get('Range','bytes=0--1').rsplit('-',1)[-1]
                        next_offset=int(end)+1 if end.isdigit() else 0
                        if next_offset<=offset:raise RuntimeError('Drive upload made no progress; retry is safe')
                        offset=next_offset
                    else:
                        info=json.load(response);break
        if not info or not verified(info):raise RuntimeError('Drive upload checksum/size verification failed')
        if state_path:state_path.unlink(missing_ok=True)
        return {'file_id':info['id'],'sha256':sha,'size':size,'mime':mime}

    def download(self,record,destination):
        target=Path(destination);target.parent.mkdir(parents=True,exist_ok=True)
        fd,temp=tempfile.mkstemp(prefix='.focu-download-',dir=target.parent)
        try:
            digest=hashlib.sha256();size=0
            file_id=urllib.parse.quote(record['file_id'],safe='')
            with os.fdopen(fd,'wb') as out,self.request('GET',API+'/files/'+file_id+'?alt=media') as response:
                for block in iter(lambda:response.read(1024*1024),b''):
                    digest.update(block);size+=len(block);out.write(block)
            if digest.hexdigest()!=record['sha256'] or size!=record['size']:
                raise RuntimeError('Downloaded artifact checksum/size mismatch')
            os.replace(temp,target)
        finally:Path(temp).unlink(missing_ok=True)
        return target
