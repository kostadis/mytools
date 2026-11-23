"""Shared review contract and immutable bundle helpers."""
import hashlib,json,os,sys
from pathlib import Path


def kit_path():
    candidates=[Path(os.environ['REVIEW_ARTIFACT_KIT'])] if os.environ.get('REVIEW_ARTIFACT_KIT') else []
    candidates += [Path(__file__).resolve().parents[2]/'_shared/review-artifact',Path.home()/'.codex/skills/_shared/review-artifact']
    for p in candidates:
        if (p/'read_decisions.py').is_file():return p
    raise ValueError('Shared review-artifact kit missing; set REVIEW_ARTIFACT_KIT to its directory.')

sys.path.insert(0,str(kit_path()))
from read_decisions import normalize,DecisionError
from review_ids import derive_review_id
import build_review


def read(path):return json.loads(Path(path).read_text())
def put(path,value):Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def safe_json(value):return json.dumps(value,ensure_ascii=True).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')


def atomic_put(path,value):
    path=Path(path);temp=path.with_name(path.name+'.tmp');put(temp,value);temp.replace(path)


def load_bundle(root):
    root=Path(root).resolve();manifest=read(root/'bundle.json')
    if manifest.get('schemaVersion')!=1:raise ValueError('Unsupported review bundle version')
    return root,manifest


def load_page(root,page):
    folder=(root/page['name']).resolve()
    if folder.parent!=root:raise ValueError('Invalid page directory')
    for name,expected in page['files'].items():
        if Path(name).name!=name or sha(folder/name)!=expected:raise ValueError(f'Frozen review artifact changed: {page["name"]}/{name}; create a new bundle version.')
    return folder,read(folder/'review_items.json'),read(folder/'review_map.json')


def normalize_page(payload,spec):
    out=normalize(payload,spec)
    if not all(isinstance(v,str) for v in out['notes'].values()):raise DecisionError('Notes must be strings')
    for card in spec['items']:
        if card.get('choiceOnly') and out['decisions'].get(card['id']) in ('approve','reject'):
            raise DecisionError(f'{card["id"]} needs a named pick or Discuss, not a generic verdict')
    exceptions=payload.get('exceptions',[])
    if not isinstance(exceptions,list) or any(not isinstance(i,str) for i in exceptions) or not set(exceptions)<={i['id'] for i in spec['items']}:raise DecisionError('Invalid exception IDs')
    out['exceptions']=list(dict.fromkeys(exceptions));return out
