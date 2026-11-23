#!/usr/bin/env python3
"""Read validated saved pages without applying their decisions to target files."""
import argparse,json,sys
from pathlib import Path
from common import load_bundle,load_page,read,sha,normalize_page,put

def collect(bundle):
    root,manifest=load_bundle(bundle);result={'reviewId':manifest['reviewId'],'total':manifest['total'],'decisions':{},'notes':{},'picks':{},'discuss':[],'unmarked':[],'missing_pages':[],'provenance':[],'scope_map':{}}
    for page in manifest['pages']:
        folder,spec,mapping=load_page(root,page);result['scope_map'].update(mapping);path=folder/'decisions.json'
        if not path.exists():result['missing_pages'].append(page['name']);result['unmarked']+=page['items'];continue
        d=normalize_page(read(path),spec)
        for key in ('decisions','notes','picks'):result[key].update(d.get(key,{}))
        result['discuss']+=d['discuss'];result['unmarked']+=d['unmarked'];result['provenance'].append({'page':page['name'],'reviewId':d['reviewId'],'savedAt':d['savedAt'],'decisions_sha256':sha(path),'frozen_files':page['files']})
    assert len(set(result['decisions'])|set(result['unmarked']))==manifest['total']
    result['needs_discussion']=bool(result['discuss']);result['all_marked']=not result['missing_pages'] and not result['unmarked'];result['ready_for_owner_review']=result['all_marked'] and not result['needs_discussion'];result['note_item_ids']=list(result['notes']);return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bundle',type=Path,required=True);p.add_argument('--out',type=Path);a=p.parse_args()
    try:result=collect(a.bundle)
    except (ValueError,OSError,KeyError) as e:p.error(str(e))
    if a.out:put(a.out,result)
    print(json.dumps(result if not a.out else {k:result[k] for k in ('total','all_marked','needs_discussion','missing_pages','unmarked','note_item_ids')},indent=2))
