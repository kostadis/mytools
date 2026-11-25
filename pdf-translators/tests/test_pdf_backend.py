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
