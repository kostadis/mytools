import json
from pathlib import Path
from unittest.mock import patch
import pytest

from lib.response_binding import response_directory, atomic_json
from lib import chunk_cache as cache

BACKEND={'name':'rust-pdf-reader/1','version':'0.1.0','protocol':1}

def bound(path, prompt='text',model='model',system='system',create=True):
    return response_directory(path,[('001-room',prompt)],system=system,model=model,backend=BACKEND,create=create)

def test_unchanged_requests_resume_and_legacy_is_preserved(tmp_path):
    legacy=tmp_path/'001-room-response.txt';legacy.write_text('historical')
    directory=bound(tmp_path);(directory/'001-room-response.txt').write_text('["new"]')
    assert bound(tmp_path,create=False)==directory
    assert legacy.read_text()=='historical'
    assert directory!=tmp_path

@pytest.mark.parametrize('changed',[{'prompt':'different'},{'model':'new-model'},{'system':'new-system'}])
def test_changed_inputs_have_separate_bindings(tmp_path,changed):
    first=bound(tmp_path);second=bound(tmp_path,**changed)
    assert first!=second
    assert not (second/'001-room-response.txt').exists()


def test_rust_replay_cannot_use_unbound_historical_files(tmp_path):
    (tmp_path/'001-room-response.txt').write_text('["historical"]')
    with pytest.raises(RuntimeError,match='bound response'):bound(tmp_path,create=False)


def test_explicit_binding_mismatch_is_rejected(tmp_path):
    directory=bound(tmp_path)
    with pytest.raises(RuntimeError,match='binding mismatch'):bound(directory,model='different',create=False)


def test_atomic_failure_preserves_previous_json(tmp_path):
    path=tmp_path/'cache.json';path.write_text('{"old": true}')
    with pytest.raises(TypeError):atomic_json(path,{'bad':object()})
    assert json.loads(path.read_text())=={'old':True}
    assert list(tmp_path.iterdir())==[path]


def test_rust_extract_path_prefers_new_and_retains_old(tmp_path):
    pdf=tmp_path/'book.pdf'
    legacy=tmp_path/'book-extract.json';legacy.write_text('historical')
    assert cache.extract_path(pdf)==legacy
    fresh=cache.extract_path(pdf,write=True);assert fresh!=legacy
    fresh.write_text('new');assert cache.extract_path(pdf)==fresh
    assert legacy.read_text()=='historical'


def encode_fixture(tmp_path,monkeypatch,*,body='original',model='model',replay=None,batch=False,resume=None):
    import converters.pdf_to_5etools_v2 as v2
    from lib.pdf_utils import TocNode
    from types import SimpleNamespace
    node=TocNode(1,'Room',1,1)
    chunk=v2.ChunkSpec(node,node,False,body)
    meta={'short_id':'TEST','name':'Fixture','output_type':'adventure','source_kind':'fast','pdf_backend':BACKEND}
    return v2.encode_chunks([node],[chunk],meta,pdf_path=tmp_path/'book.pdf',
        backend=SimpleNamespace(kind='test'),model=model,author='test',out_path=tmp_path/'book.json',
        output_dir=None,use_batch=batch,debug_dir=tmp_path/'responses',dry_run_only=False,
        verbose=False,reuse_responses=True,replay_responses=replay,resume_batch=resume)


def test_converter_reuses_only_matching_rust_prompts(tmp_path,monkeypatch):
    import converters.pdf_to_5etools_v2 as v2
    root=tmp_path/'responses';root.mkdir()
    legacy=root/'001-room-response.txt';legacy.write_text('["historical"]')
    calls=[]
    def call(backend,prompt,model,verbose,debug_dir,cid):
        calls.append(prompt)
        (debug_dir/f'{cid}-response.txt').write_text('["converted"]')
        return ['converted']
    monkeypatch.setattr(v2,'call_claude_for_chunk',call)
    encode_fixture(tmp_path,monkeypatch)
    assert len(calls)==1  # Must not consume the unbound legacy response.
    encode_fixture(tmp_path,monkeypatch);assert len(calls)==1
    encode_fixture(tmp_path,monkeypatch,body='changed');assert len(calls)==2
    encode_fixture(tmp_path,monkeypatch,body='changed',model='other');assert len(calls)==3
    assert legacy.read_text()=='["historical"]'


def test_converter_rust_replay_rejects_legacy_names(tmp_path,monkeypatch):
    directory=tmp_path/'old';directory.mkdir();(directory/'001-room-response.txt').write_text('["old"]')
    with pytest.raises(RuntimeError,match='bound response'):
        encode_fixture(tmp_path,monkeypatch,replay=directory)


def test_rust_batch_results_can_be_resumed_without_new_submission(tmp_path,monkeypatch):
    import converters.pdf_to_5etools_v2 as v2
    calls=[]
    def call(backend,prompts,model,system,verbose,debug_dir):
        calls.append(prompts);return [['converted']]
    monkeypatch.setattr(v2._api,'call_claude_batch',call)
    encode_fixture(tmp_path,monkeypatch,batch=True)
    encode_fixture(tmp_path,monkeypatch,batch=True)
    assert len(calls)==1


def test_rust_replay_uses_supplied_bound_directory(tmp_path,monkeypatch):
    import converters.pdf_to_5etools_v2 as v2
    def call(backend,prompt,model,verbose,debug_dir,cid):
        (debug_dir/f'{cid}-response.txt').write_text('["converted"]');return ['converted']
    monkeypatch.setattr(v2,'call_claude_for_chunk',call)
    encode_fixture(tmp_path,monkeypatch)
    external=tmp_path/'saved';(tmp_path/'responses').rename(external)
    monkeypatch.setattr(v2,'call_claude_for_chunk',lambda *a,**k:pytest.fail('must replay'))
    encode_fixture(tmp_path,monkeypatch,replay=external)


def test_rust_batch_resume_requires_matching_id_and_cids(tmp_path,monkeypatch):
    import converters.pdf_to_5etools_v2 as v2
    def call(backend,prompt,model,verbose,debug_dir,cid):
        (debug_dir/f'{cid}-response.txt').write_text('["converted"]');return ['converted']
    monkeypatch.setattr(v2,'call_claude_for_chunk',call)
    encode_fixture(tmp_path,monkeypatch)
    directory=next((tmp_path/'responses').glob('rust-pdf-v1/*'))
    atomic_json(directory/'batch-id.json',{'id':'batch-right','cids':['001-room']})
    monkeypatch.setattr(v2._api,'fetch_claude_batch_results',lambda *a,**k:pytest.fail('wrong ID must not fetch'))
    with pytest.raises(RuntimeError,match='batch ID'):encode_fixture(tmp_path,monkeypatch,resume='batch-wrong')
    monkeypatch.setattr(v2._api,'fetch_claude_batch_results',lambda *a,**k:[['batch entry']])
    encode_fixture(tmp_path,monkeypatch,resume='batch-right')
    assert json.loads((directory/'001-room-response.txt').read_text())==['batch entry']


def test_rust_extraction_failure_does_not_replace_legacy_or_new_cache(tmp_path,monkeypatch):
    import converters.pdf_to_5etools_v2 as v2
    from batch import batch_convert
    pdf=tmp_path/'book.pdf';pdf.write_bytes(b'fixture')
    legacy=tmp_path/'book-extract.json';legacy.write_text('historical')
    fresh=cache.extract_path(pdf,write=True);fresh.write_text('previous valid Rust cache')
    def fail(*a,**k):raise RuntimeError('incomplete worker stream')
    monkeypatch.setattr(v2,'extract_structure',fail)
    rel,status=batch_convert._extract_one(str(pdf),str(tmp_path),'adventure',True)
    assert status['extract']=='error'
    assert legacy.read_text()=='historical'
    assert fresh.read_text()=='previous valid Rust cache'


def test_batch_submission_persists_id_with_exact_submitted_cids(tmp_path):
    from types import SimpleNamespace as S
    from lib import claude_api
    client=S(messages=S(batches=S(
        create=lambda **kw:S(id='batch-fixture'),
        retrieve=lambda _:S(processing_status='ended',request_counts=S(processing=0,succeeded=1,errored=0)),
        results=lambda _:iter([S(custom_id='chunk-0000',result=S(type='succeeded',message=S(stop_reason='end_turn',content=[S(type='text',text='["entry"]')])))]),
    )))
    backend=S(kind='claude',anthropic_client=client)
    atomic_json(tmp_path/'batch-cids.json',['001-room'])
    assert claude_api.call_claude_batch(backend,['prompt'],'model','system',False,debug_dir=tmp_path)==[['entry']]
    assert json.loads((tmp_path/'batch-id.json').read_text())=={'id':'batch-fixture','cids':['001-room']}
