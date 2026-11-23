#!/usr/bin/env python3
"""Serve one exact review bundle and validated saves behind a private capability URL."""
import argparse,html,json,secrets,threading,hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote,urlsplit
from common import read,put,atomic_put,digest,load_bundle,load_page,normalize_page,safe_json

MAX_BODY=4*1024*1024

def make_server(bundle,host,port,token):
    root,manifest=load_bundle(bundle);pages={p['name']:p for p in manifest['pages']};base='/r/'+token+'/';lock=threading.Lock()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def send(self,status,body,kind='application/json'):
            data=body.encode() if isinstance(body,str) else body;self.send_response(status);self.send_header('Content-Type',kind+'; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(data)
        def error(self,status,message):self.send(status,json.dumps({'error':message}))
        def route(self):
            path=unquote(urlsplit(self.path).path)
            if not path.startswith(base):return None
            return path[len(base):].split('/')
        def do_GET(self):
            parts=self.route()
            if parts is None:return self.error(404,'Not found')
            try:
                if parts in ([''],['index.html']):
                    rows=[]
                    for p in pages.values():
                        folder,spec,_=load_page(root,p);saved=normalize_page(read(folder/'decisions.json'),spec) if (folder/'decisions.json').exists() else None;status=f'{saved["decided"]}/{len(p["items"])} saved' if saved else 'Not saved'
                        rows.append(f'<li><a href="{p["name"]}/review.html">{html.escape(p["name"])} · {len(p["items"])} items</a> — {html.escape(status)}</li>')
                    return self.send(200,'<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(manifest['title'])+'</title><body style="font:18px/1.6 system-ui;max-width:900px;margin:30px auto;padding:16px"><h1>'+html.escape(manifest['title'])+'</h1><p>Save each page before navigating.</p><ol>'+''.join(rows)+'</ol></body>','text/html')
                if len(parts)==2 and parts[0] in pages and parts[1] in ('','review.html'):
                    folder,spec,_=load_page(root,pages[parts[0]]);page=(folder/'review.html').read_text().replace('</head>','<meta name="codex-review-save" content="enabled"></head>',1)
                    if (folder/'decisions.json').exists():
                        saved=normalize_page(read(folder/'decisions.json'),spec);page=page.replace('</body>','<script type="application/json" id="review-saved">'+safe_json(saved)+'</script><script>restoreReview(JSON.parse(document.getElementById("review-saved").textContent));</script></body>',1)
                    return self.send(200,page,'text/html')
                return self.error(404,'Not found')
            except (ValueError,OSError,KeyError) as e:self.error(409,str(e))
        def do_PUT(self):
            parts=self.route()
            if not parts or len(parts)!=2 or parts[0] not in pages or parts[1]!='decisions':return self.error(404,'Not found')
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=MAX_BODY:return self.error(413,'Invalid decision payload length')
                raw_export=self.rfile.read(length);payload=json.loads(raw_export)
                with lock:
                    folder,spec,_=load_page(root,pages[parts[0]]);out=normalize_page(payload,spec);destination=folder/'decisions.json'
                    if destination.exists():
                        previous=normalize_page(read(destination),spec);history=folder/'saved_exports';history.mkdir(exist_ok=True);archive=history/(digest(previous)+'.json')
                        if not archive.exists():put(archive,previous)
                    history=folder/'saved_exports';history.mkdir(exist_ok=True);raw_hash=hashlib.sha256(raw_export).hexdigest();raw_path=history/(raw_hash+'.json')
                    if not raw_path.exists():raw_path.write_bytes(raw_export)
                    atomic_put(destination,out);atomic_put(folder/'saved_receipt.json',{'raw_export_sha256':raw_hash,'raw_export_file':str(raw_path.relative_to(folder)),'normalized_sha256':hashlib.sha256(destination.read_bytes()).hexdigest()})
                self.send(200,json.dumps({'saved':True,'decided':out['decided']}))
            except (ValueError,UnicodeError,KeyError,OSError) as e:self.error(422,str(e))
    return ThreadingHTTPServer((host,port),Handler)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bundle',type=Path,required=True);p.add_argument('--host',required=True);p.add_argument('--port',type=int,default=8765);p.add_argument('--state',type=Path);a=p.parse_args()
    if a.host in ('0.0.0.0','::',''):p.error('Bind to the exact private Tailscale address or loopback for tests.')
    root,manifest=load_bundle(a.bundle);state=a.state or Path.home()/'.local/state/review-pages'/(digest(str(root))[:16]+'.json')
    state=state.expanduser().resolve()
    if state==root or root in state.parents:p.error('Keep capability state outside the review bundle.')
    state.parent.mkdir(parents=True,exist_ok=True)
    if state.exists():
        config=read(state)
        if config['bundle']!=str(root):p.error('Capability state belongs to another bundle.')
        token=config['token']
    else:token=secrets.token_urlsafe(24);atomic_put(state,{'bundle':str(root),'token':token});state.chmod(0o600)
    server=make_server(root,a.host,a.port,token);print(f'http://{a.host}:{server.server_port}/r/{token}/',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
