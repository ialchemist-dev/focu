"""Bounded original-cover fetch for private archiving (no arbitrary API proxy)."""
import hashlib
import ipaddress
import os
from pathlib import Path
import socket
import tempfile
import urllib.parse
import urllib.request


def validate_public(url):
    p=urllib.parse.urlsplit(url)
    if p.scheme!='https' or not p.hostname or p.username or p.password or p.port not in (None,443):
        raise ValueError('Original cover requires public HTTPS')
    addresses=socket.getaddrinfo(p.hostname,443,type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
        raise ValueError('Private-network cover fetch rejected')


class PublicRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        validate_public(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def mirror(url,root):
    directory=Path(root)/'focu-covers';directory.mkdir(parents=True,exist_ok=True)
    name=hashlib.sha256(url.encode()).hexdigest()
    for suffix in ('.jpg','.png','.webp','.gif'):
        path=directory/(name+suffix)
        if path.is_file():return path
    validate_public(url)
    request=urllib.request.Request(url,headers={'User-Agent':'Focu original-cover archive'})
    with urllib.request.build_opener(PublicRedirect()).open(request,timeout=20) as response:
        mime=response.headers.get_content_type()
        suffix={'image/jpeg':'.jpg','image/png':'.png','image/webp':'.webp','image/gif':'.gif'}.get(mime)
        if not suffix:raise ValueError('Unsupported original cover image type')
        path=directory/(name+suffix);fd,temp=tempfile.mkstemp(prefix='.cover-',dir=directory)
        try:
            total=0
            with os.fdopen(fd,'wb') as out:
                for block in iter(lambda:response.read(65536),b''):
                    total+=len(block)
                    if total>10*1024*1024:raise ValueError('Cover exceeds 10 MB')
                    out.write(block)
            if not total:raise ValueError('Empty cover image')
            os.replace(temp,path)
        finally:Path(temp).unlink(missing_ok=True)
    return path
