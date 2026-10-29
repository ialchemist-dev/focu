"""Loopback-only reader API. Put a production adapter behind authenticated HTTPS."""
from __future__ import annotations
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit
from focu.reader import ASSETS


def handler(store, media_root):
    root=Path(media_root).resolve()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def headers_for(self, status, mime, size=None):
            self.send_response(status)
            self.send_header('Content-Type',mime)
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' https:; media-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            if size is not None:
                self.send_header('Content-Length',str(size))
            self.end_headers()

        def reply(self,data,status=200):
            body=json.dumps(data,ensure_ascii=False).encode()
            self.headers_for(status,'application/json; charset=utf-8',len(body))
            self.wfile.write(body)

        def valid_host(self):
            return self.headers.get('Host') in {f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}',f'[::1]:{self.server.server_port}'}

        def do_GET(self):
            if not self.valid_host():
                self.reply({'error':'Unrecognized host'},403)
                return
            try:
                parts=urlsplit(self.path)
                path=unquote(parts.path)
                query=parse_qs(parts.query)
                if path=='/api/batches':
                    return self.reply(store.batches())
                if path=='/api/batch':
                    return self.reply(store.batch(query.get('id',[''])[0]))
                if path=='/api/library':
                    return self.reply(store.library())
                if path=='/api/packs':
                    return self.reply(store.packs())
                if path=='/api/sources':
                    return self.reply(store.sources())
                if path=='/media':
                    item=store.item(query.get('id',[''])[0])
                    kind=query.get('kind',[''])[0]
                    relative=item['media'].get(kind)
                    if kind not in {'audio','video'} or not relative:
                        raise ValueError('Unavailable media')
                    target=(root/relative).resolve()
                    if not target.is_relative_to(root) or target.suffix.lower() not in {'.mp3','.m4a','.wav','.ogg','.mp4','.webm'}:
                        raise ValueError('Invalid media path')
                    return self.file(target,allow_range=True)
                names={'/':'index.html','/index.html':'index.html','/app.js':'app.js',
                       '/style.css':'style.css','/manifest.webmanifest':'manifest.webmanifest',
                       '/sw.js':'sw.js','/icon.svg':'icon.svg','/icon-192.png':'icon-192.png',
                       '/icon-512.png':'icon-512.png'}
                if path not in names:
                    return self.reply({'error':'Not found'},404)
                return self.file(ASSETS/names[path])
            except (ValueError,KeyError,FileNotFoundError) as exc:
                self.reply({'error':str(exc)},404)

        def file(self,path,allow_range=False):
            size=path.stat().st_size
            start,end=0,size-1
            status=200
            value=self.headers.get('Range') if allow_range else None
            if value:
                import re
                match=re.fullmatch(r'bytes=(\d*)-(\d*)',value)
                if not match or not any(match.groups()):
                    return self.reply({'error':'Invalid range'},416)
                a,b=match.groups()
                if a:
                    start=int(a); end=min(int(b),end) if b else end
                else:
                    start=max(0,size-int(b))
                if start>end or start>=size:
                    self.send_response(416);self.send_header('Content-Range',f'bytes */{size}');self.end_headers();return
                status=206
            self.send_response(status)
            self.send_header('Content-Type',mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
            self.send_header('Content-Length',str(end-start+1))
            self.send_header('Cache-Control','no-store' if allow_range else 'no-cache')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' https:; media-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            if allow_range:
                self.send_header('Accept-Ranges','bytes')
                if status==206:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
            self.end_headers()
            with path.open('rb') as f:
                f.seek(start);remaining=end-start+1
                while remaining:
                    chunk=f.read(min(65536,remaining))
                    if not chunk:break
                    self.wfile.write(chunk);remaining-=len(chunk)

        def do_POST(self):
            if not self.valid_host() or self.headers.get('X-Focu-Reader')!='1':
                return self.reply({'error':'Same-origin reader request required'},403)
            origin=self.headers.get('Origin')
            if origin and origin != 'http://'+self.headers['Host']:
                return self.reply({'error':'Cross-origin mutation rejected'},403)
            if self.headers.get('Content-Type')!='application/json':
                return self.reply({'error':'Expected application/json'},415)
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=16384:
                    raise ValueError('Invalid body size')
                payload=json.loads(self.rfile.read(length))
                if not isinstance(payload,dict):raise ValueError('Expected JSON object')
                if self.path=='/api/state':
                    result=store.state(payload['id'],payload['changes'])
                elif self.path=='/api/subscribe':
                    result=store.subscribe(payload['id'],payload['enabled'],payload.get('version'))
                else:
                    return self.reply({'error':'Not found'},404)
                self.reply(result)
            except (ValueError,KeyError,TypeError) as exc:
                self.reply({'error':str(exc)},400)
    return Handler


def serve(store,port,media_root):
    server=ThreadingHTTPServer(('127.0.0.1',port),handler(store,media_root))
    print(f'Focu reader: http://127.0.0.1:{server.server_port}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
