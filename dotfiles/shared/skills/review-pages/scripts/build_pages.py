#!/usr/bin/env python3
"""Build a portable, frozen review bundle; never changes a target document."""
import argparse,html,json,math,re,sys
from html.parser import HTMLParser
from pathlib import Path
from common import build_review,read,put,digest,sha,safe_json,derive_review_id

class Plain(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.parts=[];self.audio=[]
    def handle_starttag(self,tag,attrs):
        if tag in ('p','pre','li','br','blockquote'):self.parts.append('\n')
        if tag=='audio':self.audio.extend(v for k,v in attrs if k=='src')
    def handle_endtag(self,tag):
        if tag in ('p','pre','li','blockquote'):self.parts.append('\n')
    def handle_data(self,data):self.parts.append(data)
def plain(value):
    parser=Plain();parser.feed(str(value));return ''.join(parser.parts).strip()
def audio_sources(card):
    parser=Plain();parser.feed(card.get('ev',''));sources=[card.get('audioData'),*card.get('extraAudio',[]),*parser.audio];out=[]
    for source in sources:
        if not source:continue
        if not isinstance(source,str) or not (source.startswith(('https://','http://')) or re.match(r'^data:audio/[\w.+-]+;base64,',source)):raise ValueError('Audio must be an attached data:audio clip or an authorized HTTP(S) URL, not an arbitrary local path.')
        if source not in out:out.append(source)
    return out

def build(items_path,map_path,output,scores_path=None,page_size=100):
    if not 1<=page_size<=100:raise ValueError('Page size must be 1–100')
    spec=read(items_path);mapping=read(map_path);errors=build_review.validate(spec)
    if errors:raise ValueError(errors)
    review_kinds={'text-edit','interpretation','decision'}
    if spec.get('reviewKind','text-edit') not in review_kinds:raise ValueError('Unsupported reviewKind')
    if any(c.get('reviewKind',spec.get('reviewKind','text-edit')) not in review_kinds for c in spec['items']):raise ValueError('Unsupported item reviewKind')
    if spec.get('extraVerdicts'):raise ValueError('Use named picks for extra outcomes; this layout supports Approve/Reject/Discuss and picks.')
    
    if not spec.get('reviewId'):raise ValueError('Supply an explicit unique reviewId')
    cards=spec['items'];ids=[c['id'] for c in cards]
    if not cards:raise ValueError('No decisions; record the empty stage in its owner ledger instead of publishing an empty review.')
    if not isinstance(mapping,dict) or set(ids)!=set(mapping):raise ValueError('Every item must have exactly one scope-map entry')
    raw_scores=read(scores_path) if scores_path else [];scores={s['id']:s for s in raw_scores}
    if len(scores)!=len(raw_scores) or (scores_path and set(scores)!=set(ids)):raise ValueError('Score IDs must cover every item exactly once, or omit scoring entirely.')
    display=[]
    for card in cards:
        i=card['id'];scope=mapping[i]
        if not isinstance(scope,dict) or not scope.get('scope'):raise ValueError(f'{i}: declare the exact scope in the map')
        picks=card.get('picks',[]);texts=card.get('pickTexts',{})
        if picks and set(picks)!=set(texts):raise ValueError(f'{i}: every named pick needs its exact pickTexts passage/outcome')
        if not all(isinstance(t,str) for t in texts.values()):raise ValueError(f'{i}: pickTexts values must be strings')
        if card.get('choiceOnly') and not picks:raise ValueError(f'{i}: choiceOnly needs explicit picks')
        if card.get('guessPick') and card['guessPick'] not in picks:raise ValueError(f'{i}: invalid recommended pick')
        original='Keep original source passage exactly'
        if original in texts and texts[original]!=card.get('sourcePassage'):raise ValueError(f'{i}: keep-original option does not equal sourcePassage')
        for field in ('sourcePassage','confirmedPassage','fullPassage'):
            if card.get(field) is not None and not isinstance(card[field],str):raise ValueError(f'{i}: {field} must be exact text')
        probability=None
        if i in scores:
            score=scores[i];probability=score['p_approve']
            if isinstance(probability,bool) or not isinstance(probability,(float,int)) or not math.isfinite(probability) or not 0<=probability<=1:raise ValueError(f'{i}: invalid probability')
            if 'request' in score:
                request=score['request'];state=request['state'];state=json.loads(state) if isinstance(state,str) else state
                if score.get('input_sha256')!=digest(request) or state.get('question_as_displayed')!=card or state.get('exact_apply_scope')!=scope:raise ValueError(f'{i}: stale score/request or changed scope')
            elif score.get('item_sha256')!=digest(card) or score.get('scope_sha256')!=digest(scope):raise ValueError(f'{i}: score needs exact item_sha256 and scope_sha256 bindings')
        tier='high' if probability is not None and probability>.9 else 'middle' if probability is not None and probability>=.8 else 'cards'
        if card.get('choiceOnly') or card.get('guess','approve')!='approve' or scope.get('requires') or scope.get('requires_named'):tier='cards'
        audio=audio_sources(card);guess=card.get('guessPick') or card.get('guess','approve')
        display.append({'id':i,'reviewKind':card.get('reviewKind',spec.get('reviewKind','text-edit')),'title':plain(card['t']),'display_pair':plain(card.get('edit') or card['t']),'session':card.get('session',''),'reviewGroup':card.get('reviewGroup',''),'p_yes':probability,'tier':tier,'proposal':plain(card['t'])+'\nApprove: '+plain(card['y'])+'\nReject: '+plain(card['n']),'proposed_text':'Recommended: '+guess+'. '+plain(card.get('guessWhy',''))+'\nApprove: '+plain(card['y'])+'\nReject: '+plain(card['n']),'evidence':plain(card.get('ev',''))+'\n\nExact scope:\n'+json.dumps(scope,indent=2,ensure_ascii=False),'picks':picks,'pickTexts':texts,'guessPick':card.get('guessPick'),'guess':card.get('guess','approve'),'choiceOnly':card.get('choiceOnly',False),'sourcePassage':card.get('sourcePassage'),'confirmedPassage':card.get('confirmedPassage'),'fullPassage':card.get('fullPassage'),'baselineLabel':card.get('baselineLabel'),'deletionOnly':card.get('deletionOnly',False),'uncertainties':card.get('uncertainties',[]),'requires':scope.get('requires',[]),'requiresNamed':scope.get('requires_named',{}),'audioData':audio[0] if audio else None,'extraAudio':audio[1:]})
        if display[-1]['reviewKind']=='interpretation':
            display[-1]['proposal']=plain(card['t'])+'\nYes: '+plain(card['y'])+'\nNo: '+plain(card['n'])
            display[-1]['proposed_text']=plain(card.get('guessWhy','Compare each numbered reading with the passage.'))+'\nYes: '+plain(card['y'])+'\nNo: '+plain(card['n'])
    asset=Path(__file__).resolve().parents[1]/'assets/review.html';template=asset.read_text();fingerprint=digest({'spec':spec,'mapping':mapping,'scores':raw_scores,'page_size':page_size,'template_sha256':sha(asset),'builder_sha256':sha(Path(__file__))})
    output=Path(output)
    if output.exists() and any(output.iterdir()):
        existing=read(output/'bundle.json') if (output/'bundle.json').exists() else {}
        if existing.get('input_sha256')!=fingerprint:raise ValueError('Output already contains another/frozen review; choose a new output directory. Existing decisions are never overwritten.')
        for page in existing['pages']:
            for name,expected in page['files'].items():
                if sha(output/page['name']/name)!=expected:raise ValueError('Existing bundle was edited; create a new version.')
        return existing
    output.mkdir(parents=True,exist_ok=True)
    groups={}
    for card in display:groups.setdefault(card['reviewGroup'],[]).append(card)
    chunks=[]
    for group in groups.values():
        ordered=sorted(group,key=lambda c:({'high':0,'middle':1,'cards':2}[c['tier']],-(c['p_yes'] or 0),ids.index(c['id'])))
        chunks.extend(ordered[n:n+page_size] for n in range(0,len(ordered),page_size))
    by={c['id']:c for c in cards};pages=[];total_pages=len(chunks)
    models={s.get('model','Decision model') for s in raw_scores}
    model=spec.get('decisionModel') or (next(iter(models)) if len(models)==1 else 'Multiple decision models' if models else 'Unscored review')
    for number,shown in enumerate(chunks,1):
        name=f'page-{number:03d}';folder=output/name;folder.mkdir();subset=[by[c['id']] for c in shown];page_spec={**spec,'reviewId':derive_review_id(spec['reviewId']+f'-p{number}'),'items':subset};page_map={c['id']:mapping[c['id']] for c in subset};page_scores=[scores[c['id']] for c in subset if c['id'] in scores]
        put(folder/'review_items.json',page_spec);put(folder/'review_map.json',page_map);put(folder/'scores.json',page_scores)
        live={'title':spec['title'],'reviewKind':spec.get('reviewKind','text-edit'),'reviewId':page_spec['reviewId'],'model':model,'threshold':.9,'middle_threshold':.8,'items':shown}
        page=template.replace('__REVIEW_DATA__',safe_json(live)).replace('__TITLE__',html.escape(spec['title'])).replace('__MODEL__',html.escape(model)).replace('__LEDE__',html.escape(plain(spec.get('lede','Review each exact proposal, then save your decisions.')))).replace('__FOOTER__',html.escape(plain(spec.get('footer',''))))
        nav=f'<nav class="notice" aria-label="Review pages"><a href="../index.html">All review pages</a> · Page {number} of {total_pages} · {len(subset)} items'
        if number>1:nav+=f' · <a href="../page-{number-1:03d}/review.html">Previous</a>'
        if number<total_pages:nav+=f' · <a href="../page-{number+1:03d}/review.html">Next</a>'
        page=page.replace('<body>','<body>'+nav+'</nav>',1);(folder/'review.html').write_text(page)
        pages.append({'name':name,'group':shown[0]['reviewGroup'],'reviewId':page_spec['reviewId'],'items':[c['id'] for c in subset],'files':{f:sha(folder/f) for f in ('review_items.json','review_map.json','scores.json','review.html')}})
    index='<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(spec['title'])+'</title><h1>'+html.escape(spec['title'])+'</h1><p>Save each page before navigating.</p><ol>'+''.join('<li><a href="'+p['name']+'/review.html">'+p['name']+' · '+str(len(p['items']))+' items</a></li>' for p in pages)+'</ol>'
    (output/'index.html').write_text(index)
    put(output/'bundle.json',{'schemaVersion':1,'reviewId':spec['reviewId'],'title':spec['title'],'input_sha256':fingerprint,'total':len(cards),'page_limit':page_size,'pages':pages})
    put(output/'source_items.json',spec);put(output/'source_map.json',mapping);put(output/'source_scores.json',raw_scores)
    return read(output/'bundle.json')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--items',type=Path,required=True);parser.add_argument('--map',type=Path,required=True);parser.add_argument('--out',type=Path,required=True);parser.add_argument('--scores',type=Path);parser.add_argument('--page-size',type=int,default=100);a=parser.parse_args()
    try:result=build(a.items,a.map,a.out,a.scores,a.page_size)
    except (ValueError,KeyError,TypeError) as e:parser.error(str(e))
    print(json.dumps({'items':result['total'],'pages':len(result['pages']),'bundle':str(a.out)}))
