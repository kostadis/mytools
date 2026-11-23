"""Shared decision server plus a fixed allowlist of review WAVs, under the same capability."""
import argparse,hashlib,ipaddress,json,re,secrets,sys
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote,urlparse
sys.path.insert(0,str(Path(__file__).resolve().parent))
import serve_review as shared
class Handler(shared.Handler):
 def do_GET(self):
  path=unquote(urlparse(self.path).path);prefix=self.config.base_path+'audio/'
  if not path.startswith(prefix):return super().do_GET()
  key=path[len(prefix):];file=self.server.review_audio.get(key)
  if file is None:return self._json(404,{'error':'not found'})
  size=file.stat().st_size;first,last=0,size-1;status=200
  if self.headers.get('Range'):
   match=re.fullmatch(r'bytes=(\d+)-(\d*)',self.headers['Range'])
   if not match:return self._json(416,{'error':'invalid range'})
   first=int(match[1]);last=min(int(match[2]),last) if match[2] else last
   if first>last:return self._json(416,{'error':'invalid range'})
   status=206
  self.send_response(status);self.send_header('Content-Type','audio/wav');self.send_header('Content-Length',str(last-first+1));self.send_header('Accept-Ranges','bytes');self.send_header('Cache-Control','private, max-age=3600');self.send_header('X-Content-Type-Options','nosniff')
  if status==206:self.send_header('Content-Range',f'bytes {first}-{last}/{size}')
  self.end_headers()
  with file.open('rb') as stream:
   stream.seek(first);remaining=last-first+1
   while remaining:
    data=stream.read(min(65536,remaining))
    if not data:break
    self.wfile.write(data);remaining-=len(data)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--review',required=True,type=Path);ap.add_argument('--host',required=True);ap.add_argument('--port',type=int,default=8878);args=ap.parse_args();address=ipaddress.ip_address(args.host)
 if not address.is_loopback and args.host != shared.tailscale_ip():ap.error('Bind to the current Tailscale IPv4 address (or loopback for local verification).')
 p=args.review.resolve();spec=json.loads((p/'review_items.json').read_text());manifest=json.loads((p/'audio_manifest.json').read_text());audio={}
 for key,value in manifest.items():
  assert re.fullmatch(r'[0-9a-f]{64}\.wav',key),key
  file=Path(value['file']).resolve(strict=True);assert file.is_file() and file.suffix=='.wav'
  assert hashlib.sha256(file.read_bytes()).hexdigest()==key[:-4],f'Audio hash mismatch: {key}'
  audio[key]=file
 cfg=shared.ReviewConfig(p/'review.html',p/'review_items.json',p/'decisions.json',secrets.token_urlsafe(18),spec);server=ThreadingHTTPServer((args.host,args.port),partial(Handler));server.review_config=cfg;server.review_audio=audio
 print(f'Review URL: http://{args.host}:{server.server_address[1]}{cfg.base_path}',flush=True);print(f'Saves to: {cfg.output}',flush=True);print(f'Allowlisted audio: {len(audio)} clips; no directory or arbitrary-file access.',flush=True)
 try:server.serve_forever()
 except KeyboardInterrupt:print('stopped',flush=True)
 finally:server.server_close()
if __name__=='__main__':main()
