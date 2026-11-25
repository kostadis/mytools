"""Strict process boundary for the Rust PDF worker; no PDF library required."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from lib.pdf_backend import RustDocument, PdfBackendError

DOC = {"type":"document", "protocol":1,"backend":"rust-pdf-reader/1","build":"0.1.0","page_count":2,"requested":[],"outline":[{"level":1,"title":"Group","page":None},{"level":2,"title":"Room","page":1},{"level":2,"title":"Room","page":2}]}
END = {"type":"end","complete":True,"requested":0,"emitted":0,"failed":0}


def worker(tmp_path, monkeypatch, records=None, extra="", code=0):
    path=tmp_path/'worker'
    payload='import json,sys,time\n'+extra+'\n'
    if records is not None:
        payload += '\n'.join('print('+repr(json.dumps(r))+', flush=True)' for r in records)+'\n'
    payload += f'sys.exit({code})\n'
    path.write_text('#!'+sys.executable+'\n'+payload);path.chmod(0o755)
    monkeypatch.setenv('RPG_PDF_READER',str(path))
    pdf=tmp_path/'source.pdf';pdf.write_bytes(b'fixture')
    return pdf


def test_inspect_and_group_ranges(tmp_path,monkeypatch):
    pdf=worker(tmp_path,monkeypatch,[DOC,END])
    doc=RustDocument(pdf)
    assert doc.page_count==2
    assert doc.get_toc()==[[1,'Group',1],[2,'Room',1],[2,'Room',2]]
    assert doc.backend['name']=='rust-pdf-reader/1'


@pytest.mark.parametrize('records,code',[
    ([DOC],0), ([DOC,END],1), ([{**DOC,'protocol':2},END],0),
    ([DOC,{**END,'complete':False}],0), ([DOC,DOC,END],0),
    ([DOC,{**END,'emitted':1}],0), ([DOC,END,END],0),
    ([{**DOC,'page_count':True},END],0),
    ([{**DOC,'outline':[{'level':1,'title':'bad','page':3}]},END],0),
    ([{'type':'error','code':'password_required','message':'Password required'}, {**END,'complete':False}],1),
])
def test_incomplete_or_invalid_protocol_rejected(tmp_path,monkeypatch,records,code):
    pdf=worker(tmp_path,monkeypatch,records,code=code)
    with pytest.raises(PdfBackendError):RustDocument(pdf)


def test_invalid_json_is_not_a_success(tmp_path,monkeypatch):
    pdf=worker(tmp_path,monkeypatch,extra="print('not json',flush=True)")
    with pytest.raises(PdfBackendError):RustDocument(pdf)


def test_timeout_reaps_worker(tmp_path,monkeypatch):
    pid=tmp_path/'pid'
    pdf=worker(tmp_path,monkeypatch,extra=f"import os\nopen({str(pid)!r},'w').write(str(os.getpid()))\ntime.sleep(30)")
    started=time.monotonic()
    with pytest.raises(PdfBackendError,match='timed out'):RustDocument(pdf,timeout=0.2)
    assert time.monotonic()-started<3
    with pytest.raises(ProcessLookupError):os.kill(int(pid.read_text()),0)


def test_stderr_flood_does_not_deadlock(tmp_path,monkeypatch):
    pdf=worker(tmp_path,monkeypatch,[DOC,END],extra="sys.stderr.write('x'*200000);sys.stderr.flush()")
    assert RustDocument(pdf,timeout=3).page_count==2


def test_missing_worker_has_build_instructions(tmp_path,monkeypatch):
    monkeypatch.setenv('RPG_PDF_READER',str(tmp_path/'missing'))
    with pytest.raises(PdfBackendError,match='cargo build'):RustDocument(tmp_path/'book.pdf')


def test_reads_selected_pages_once_and_stages_before_commit(tmp_path,monkeypatch):
    calls=tmp_path/'calls'
    extra=f'''open({str(calls)!r},'a').write(' '.join(sys.argv[1:])+'\\n')
requested=[] if sys.argv[1]=='inspect' else [int(x) for x in sys.argv[sys.argv.index('--pages')+1].split(',')]
doc={DOC!r};doc['requested']=requested
print(json.dumps(doc))
for page in requested:print(json.dumps({{'type':'page','page':page,'text':'page '+str(page)}}))
print(json.dumps({{'type':'end','complete':True,'requested':len(requested),'emitted':len(requested),'failed':0}}))'''
    pdf=worker(tmp_path,monkeypatch,extra=extra)
    d=RustDocument(pdf);d.read_pages([1]);d.read_all();d.read_all()
    assert d.load_page(0).get_text('text')=='page 1'
    assert d.load_page(1).get_text('text')=='page 2'
    lines=calls.read_text().splitlines(); assert len(lines)==3
    assert lines[1].endswith('--pages 1') and lines[2].endswith('--pages 2')


def test_markdown_import_chain_does_not_import_fitz():
    project=Path(__file__).resolve().parents[1]
    code='''
import sys, importlib.abc
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self, fullname, path=None, target=None):
  if fullname.split('.')[0] in {'fitz','pymupdf'}: raise AssertionError('PDF engine imported')
sys.meta_path.insert(0,Block())
from converters import pdf_to_5etools_v2 as c
assert c.parse_markdown_headings('# Searchable')[0][0].title=='Searchable'
'''
    subprocess.run([sys.executable,'-c',code],env={**os.environ,'PYTHONPATH':str(project)},capture_output=True,check=True)


def test_batch_classifier_uses_rust_and_batches_sampled_pages(tmp_path,monkeypatch):
    import lib.pdf_backend as backend
    from batch import batch_convert
    calls=[]
    class Document:
        page_count=2
        def __init__(self,path):pass
        def __enter__(self):return self
        def __exit__(self,*args):calls.append('closed')
        def read_pages(self,pages):calls.append(list(pages))
        def load_page(self,index):return self
        def get_text(self,kind):return 'x'*500
    monkeypatch.setattr(backend,'RustDocument',Document)
    pdf=tmp_path/'book.pdf';pdf.write_bytes(b'fixture')
    rel,result=batch_convert.classify_pdf(str(pdf),str(tmp_path))
    assert result['status']=='pending'
    assert calls==[[1,2],'closed']


@pytest.mark.parametrize('bad', ['duplicate','unexpected','missing','error','invalid-text','boolean-page'])
def test_failed_extraction_does_not_commit_partial_pages(tmp_path,monkeypatch,bad):
    extra=f'''
doc={DOC!r}
if sys.argv[1]=='inspect':
 print(json.dumps(doc));print(json.dumps({END!r}))
else:
 doc['requested']=[1,2];print(json.dumps(doc))
 print(json.dumps({{'type':'page','page':1,'text':'partial'}}))
 bad={bad!r}
 if bad=='error':print(json.dumps({{'type':'error','code':'unsupported_content','message':'bad glyph'}}))
 elif bad=='duplicate':print(json.dumps({{'type':'page','page':1,'text':'duplicate'}}))
 elif bad=='unexpected':print(json.dumps({{'type':'page','page':3,'text':'unexpected'}}))
 elif bad=='invalid-text':print(json.dumps({{'type':'page','page':2,'text':None}}))
 elif bad=='boolean-page':print(json.dumps({{'type':'page','page':True,'text':'bad'}}))
 print(json.dumps({{'type':'end','complete':True,'requested':2,'emitted':2,'failed':0}}))
'''
    pdf=worker(tmp_path,monkeypatch,extra=extra)
    doc=RustDocument(pdf)
    with pytest.raises(PdfBackendError):doc.read_all()
    assert doc.pages=={}


def test_real_worker_v2_dry_run_without_python_pdf_engine(tmp_path):
    from lib.pdf_backend import executable
    try:
        binary=executable()
    except PdfBackendError:
        pytest.skip('build Rust reader for end-to-end acceptance')
    text=b'BT /F1 12 Tf 20 700 Td '+b'(Searchable content 17.) Tj 0 -20 Td '*6+b'ET'
    objects=[
        b'<< /Type /Catalog /Pages 2 0 R /Outlines 7 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 6 0 R >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 6 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        b'<< /Length '+str(len(text)).encode()+b' >>\nstream\n'+text+b'\nendstream',
        b'<< /Type /Outlines /First 8 0 R /Last 8 0 R /Count 1 >>',
        b'<< /Title (Chapter) /Parent 7 0 R /Dest [3 0 R /Fit] >>',
    ]
    data=bytearray(b'%PDF-1.4\n');offsets=[0]
    for n,obj in enumerate(objects,1):
        offsets.append(len(data));data.extend(f'{n} 0 obj\n'.encode()+obj+b'\nendobj\n')
    xref=len(data);data.extend(f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode())
    for off in offsets[1:]:data.extend(f'{off:010d} 00000 n \n'.encode())
    data.extend(f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode())
    pdf=tmp_path/'source.pdf';pdf.write_bytes(data)
    project=Path(__file__).resolve().parents[1]
    code='''
import sys,importlib.abc
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname.split('.')[0] in {'fitz','pymupdf'}:raise AssertionError('legacy PDF engine imported')
sys.meta_path.insert(0,Block())
from converters import pdf_to_5etools_v2 as c
roots,units,kind,meta=c.extract_structure(__import__('pathlib').Path(sys.argv[1]),output_type='adventure',allow_marker=False)
assert len(units)==2 and all('Searchable content 17.' in unit for unit in units)
assert meta['pdf_backend']['name']=='rust-pdf-reader/1'
assert c.main([sys.argv[1],'--provider','claude-code','--dry-run'])==0
'''
    subprocess.run([sys.executable,'-c',code,str(pdf)],env={**os.environ,'RPG_PDF_READER':binary,'PYTHONPATH':str(project)},check=True,capture_output=True)


def test_timeout_kills_group_even_if_worker_leader_has_exited(tmp_path,monkeypatch):
    pidfile=tmp_path/'descendant'
    pdf=worker(tmp_path,monkeypatch,extra=f'''import os
pid=os.fork()
if pid==0:
 open({str(pidfile)!r},'w').write(str(os.getpid()))
 time.sleep(30)
else:
 sys.exit(0)
''')
    with pytest.raises(PdfBackendError,match='timed out'):RustDocument(pdf,timeout=0.3)
    pid=int(pidfile.read_text())
    try:
        status=Path(f'/proc/{pid}/stat')
        deadline=time.monotonic()+1
        while status.exists() and status.read_text().split()[2]!='Z' and time.monotonic()<deadline:
            time.sleep(0.01)
        assert not status.exists() or status.read_text().split()[2]=='Z'
    finally:
        try:os.kill(pid,9)
        except ProcessLookupError:pass


def test_missing_worker_stops_batch_scan_before_creating_skip_entries(tmp_path,monkeypatch):
    from batch import batch_convert
    (tmp_path/'book.pdf').write_bytes(b'fixture')
    monkeypatch.setenv('RPG_PDF_READER',str(tmp_path/'missing'))
    with pytest.raises(PdfBackendError,match='cargo build'):
        batch_convert.build_manifest(tmp_path,{},1)


def test_environment_scan_errors_are_retryable_after_install(tmp_path,monkeypatch):
    from batch import batch_convert
    pdf=tmp_path/'book.pdf';pdf.write_bytes(b'fixture')
    stat=pdf.stat()
    previous={'book.pdf':{'size':stat.st_size,'mtime':int(stat.st_mtime),'status':'skipped','reason':'scan_error: PdfBackendError','text_chars':0}}
    # At least preflight must be attempted instead of blindly reusing skips.
    monkeypatch.setenv('RPG_PDF_READER',str(tmp_path/'missing'))
    with pytest.raises(PdfBackendError,match='cargo build'):
        batch_convert.build_manifest(tmp_path,previous,1)
