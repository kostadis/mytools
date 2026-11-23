import base64,copy,json,sys,tempfile,threading,unittest,urllib.error,urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from build_pages import build
from common import put,read,digest,normalize_page
from read_results import collect
from serve_bundle import make_server

class BundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def make_inputs(self,count=4,grouped=False):
        cards=[];mapping={};scores=[]
        for n in range(count):
            i=f'item-{n}';card={'id':i,'t':'Choose the wording','y':'Use the proposed text in draft only.','n':'Keep the reviewed baseline.','sourcePassage':'Raw source','confirmedPassage':'Reviewed source','fullPassage':'Proposed text','guess':'approve','picks':['Keep original source passage exactly'],'pickTexts':{'Keep original source passage exactly':'Raw source'}}
            if grouped:card['reviewGroup']='first' if n<2 else 'second'
            if n==3:card.update(choiceOnly=True,guess='discuss',guessPick='Use contextual guess shown above',picks=['Use contextual guess shown above','Keep original source passage exactly'],pickTexts={'Use contextual guess shown above':'Proposed text','Keep original source passage exactly':'Raw source'})
            cards.append(card);mapping[i]={'scope':'This exact draft passage only','target':'example.md'};scores.append({'id':i,'p_approve':.99,'model':'clef','item_sha256':digest(card),'scope_sha256':digest(mapping[i])})
        spec={'title':'Fixture review','reviewId':'fixture-v1','items':cards};put(self.root/'items.json',spec);put(self.root/'map.json',mapping);put(self.root/'scores.json',scores);return spec,mapping,scores
    def create(self,count=4,grouped=False,scored=True):
        inputs=self.make_inputs(count,grouped);bundle=self.root/'bundle';manifest=build(self.root/'items.json',self.root/'map.json',bundle,self.root/'scores.json' if scored else None);return bundle,manifest,inputs
    def test_pagination_and_groups(self):
        bundle,m,_=self.create(101);self.assertEqual([len(p['items']) for p in m['pages']],[100,1]);self.assertEqual(len({i for p in m['pages'] for i in p['items']}),101);self.assertNotEqual(m['pages'][0]['reviewId'],m['pages'][1]['reviewId']);self.assertTrue((bundle/'index.html').exists())
        self.tmp.cleanup();self.setUp();_,m,_=self.create(5,True);self.assertEqual([len(p['items']) for p in m['pages']],[2,3])
    def test_stale_scores_and_keep_meaning(self):
        spec,mapping,scores=self.make_inputs();mapping['item-0']['target']='other.md';put(self.root/'map.json',mapping)
        with self.assertRaisesRegex(ValueError,'scope'):build(self.root/'items.json',self.root/'map.json',self.root/'bad',self.root/'scores.json')
        spec['items'][0]['pickTexts']['Keep original source passage exactly']='wrong';put(self.root/'items.json',spec)
        with self.assertRaisesRegex(ValueError,'keep-original'):build(self.root/'items.json',self.root/'map.json',self.root/'bad2')
    def test_frozen_output_and_unscored(self):
        bundle,m,(spec,mapping,_)=self.create(scored=False);page=bundle/m['pages'][0]['name'];self.assertIn('Not scored',(page/'review.html').read_text());put(page/'decisions.json',{'sentinel':True});build(self.root/'items.json',self.root/'map.json',bundle);self.assertEqual(read(page/'decisions.json'),{'sentinel':True})
        mapping['item-0']['scope']='different scope';put(self.root/'map.json',mapping)
        with self.assertRaisesRegex(ValueError,'frozen'):build(self.root/'items.json',self.root/'map.json',bundle)
    def test_interpretation_kind_preserves_source_and_native_scope(self):
        spec,mapping,_=self.make_inputs(count=1)
        spec['reviewKind']='interpretation'
        spec['items'][0].pop('confirmedPassage')
        spec['items'][0]['fullPassage']='The draft says the regiment serves for one day.'
        put(self.root/'items.json',spec)
        bundle=self.root/'meaning-bundle'
        manifest=build(self.root/'items.json',self.root/'map.json',bundle)
        page=bundle/manifest['pages'][0]['name']
        saved=read(page/'review_items.json')
        self.assertEqual(saved['reviewKind'],'interpretation')
        self.assertEqual(saved['items'][0]['sourcePassage'],'Raw source')
        self.assertEqual(read(page/'review_map.json'),mapping)
        self.assertNotIn('confirmedPassage',saved['items'][0])
        payload={'reviewId':saved['reviewId'],'savedAt':'2026-11-21T00:00:00Z','decisions':{'item-0':'approve'}}
        normalized=normalize_page(payload,saved)
        self.assertEqual(normalized['decisions'],{'item-0':'approve'})
        self.assertEqual(saved['items'][0]['sourcePassage'],'Raw source')
    def test_unknown_review_kind_refuses(self):
        spec,_,_=self.make_inputs(count=1)
        spec['reviewKind']='unknown-mode';put(self.root/'items.json',spec)
        with self.assertRaisesRegex(ValueError,'reviewKind'):
            build(self.root/'items.json',self.root/'map.json',self.root/'bad-kind')
    def test_named_only_and_partial_collection(self):
        bundle,m,_=self.create();page=bundle/m['pages'][0]['name'];spec=read(page/'review_items.json');payload={'reviewId':spec['reviewId'],'savedAt':'2026-11-21T00:00:00Z','decisions':{'item-3':'approve'},'unmarked':['item-0','item-1','item-2']}
        with self.assertRaisesRegex(ValueError,'named pick'):normalize_page(payload,spec)
        payload.update(decisions={'item-3':'pick'},picks={'item-3':'Keep original source passage exactly'},notes={'item-1':'Unmarked note'});put(page/'decisions.json',normalize_page(payload,spec));r=collect(bundle);self.assertFalse(r['ready_for_owner_review']);self.assertEqual(r['notes']['item-1'],'Unmarked note');self.assertEqual(len(r['unmarked']),3)
        mapping=read(page/'review_map.json');mapping['item-0']['scope']='changed';put(page/'review_map.json',mapping)
        with self.assertRaisesRegex(ValueError,'Frozen'):collect(bundle)
    def test_server_save_restore_and_foreign_rejection(self):
        bundle,m,_=self.create();server=make_server(bundle,'127.0.0.1',0,'test-capability');thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();base=f'http://127.0.0.1:{server.server_port}/r/test-capability/';name=m['pages'][0]['name'];page=bundle/name;spec=read(page/'review_items.json');payload={'schemaVersion':1,'reviewId':spec['reviewId'],'savedAt':'2026-11-21T00:00:00Z','decisions':{'item-0':'reject','item-3':'pick'},'picks':{'item-3':'Keep original source passage exactly'},'notes':{'item-1':'Remember me'},'unmarked':['item-1','item-2']}
        try:
            def send(value):return urllib.request.urlopen(urllib.request.Request(base+name+'/decisions',data=json.dumps(value).encode(),method='PUT',headers={'Content-Type':'application/json'}))
            bad={**payload,'reviewId':'foreign'}
            with self.assertRaises(urllib.error.HTTPError) as error:send(bad)
            self.assertEqual(error.exception.code,422);error.exception.close();self.assertFalse((page/'decisions.json').exists())
            with send(payload) as response:self.assertEqual(response.status,200)
            with urllib.request.urlopen(base+name+'/review.html') as response:text=response.read().decode();self.assertIn('restoreReview(JSON.parse',text);self.assertIn('Remember me',text)
            self.assertEqual(len(list((page/'saved_exports').glob('*.json'))),1)
            with urllib.request.urlopen(base) as response:self.assertIn('2/4 saved',response.read().decode())
            with self.assertRaises(urllib.error.HTTPError) as missing:urllib.request.urlopen(base+'../outside.txt')
            missing.exception.close()
        finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':unittest.main()
