"""One Git writer, no force pushes, private GitHub remote required by default."""
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.request


class GitJournal:
    def __init__(self,path,*,verify_private=True):
        self.path=Path(path).resolve();self.verify_private=verify_private

    def git(self,*args):
        try:
            return subprocess.run(['git','-C',str(self.path),*args],capture_output=True,text=True,
                                  check=True,timeout=90,env={**os.environ,'GIT_TERMINAL_PROMPT':'0'}).stdout.strip()
        except (subprocess.SubprocessError,OSError):
            raise RuntimeError('Metadata Git operation failed; check repository access and branch divergence') from None

    def prepare(self):
        if self.git('status','--porcelain'):
            raise RuntimeError('Metadata checkout has uncommitted changes; preserve them before sync')
        branch=self.git('branch','--show-current')
        if not branch:raise RuntimeError('Metadata checkout must use a named branch')
        remote=self.git('remote','get-url','origin')
        if self.verify_private:
            match=re.fullmatch(r'(?:git@github\.com:|https://github\.com/)([\w.-]+/[\w.-]+?)(?:\.git)?',remote)
            if not match:raise ValueError('Expected a credential-free private GitHub origin')
            token=os.environ.get('FOCU_GITHUB_TOKEN') or os.environ.get('GH_TOKEN')
            if not token:raise ValueError('Private-repository visibility check requires FOCU_GITHUB_TOKEN or GH_TOKEN')
            req=urllib.request.Request('https://api.github.com/repos/'+match[1],headers={
                'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','User-Agent':'Focu'})
            try:
                with urllib.request.urlopen(req,timeout=30) as response:info=json.load(response)
            except Exception:raise RuntimeError('Cannot verify metadata repository privacy') from None
            if info.get('private') is not True:raise ValueError('Metadata repository must be private')
        self.git('fetch','origin',branch)
        remote_head=self.git('rev-parse','origin/'+branch)
        self.git('merge-base','--is-ancestor',remote_head,'HEAD')
        # Reject unseen upstream edits even when the local checkout is behind.
        if self.git('rev-parse','HEAD')==remote_head:return branch
        # Local-ahead commits from an interrupted previous push are safe to retry;
        # a remote-ahead or divergent history failed the ancestry check above.
        return branch

    def publish(self,catalog,events):
        branch=self.prepare()
        root=self.path/'focu';(root/'events').mkdir(parents=True,exist_ok=True)
        (root/'catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
        import hashlib
        for event in events:
            name=hashlib.sha256(event['event_id'].encode()).hexdigest()+'.json'
            path=root/'events'/name
            body=json.dumps(event,ensure_ascii=False,sort_keys=True,indent=2)+'\n'
            if path.exists() and path.read_text()!=body:raise ValueError('Immutable event conflicts with metadata history')
            path.write_text(body)
        self.git('add','--','focu/catalog.json','focu/events')
        if self.git('diff','--cached','--name-only'):
            self.git('-c','user.name=Focu','-c','user.email=focu@localhost','commit','-m','Sync Focu catalog and reading state')
        self.git('push','origin','HEAD:refs/heads/'+branch)
        return self.git('rev-parse','HEAD')

    def read(self):
        self.prepare()
        return json.loads((self.path/'focu/catalog.json').read_text())
