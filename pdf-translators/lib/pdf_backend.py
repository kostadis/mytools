"""Validated JSONL boundary to the standalone Rust PDF reader.

No PDF engine is imported here. Document pages are committed only after a
complete, successful worker response. Each extraction requests missing pages
as a batch and shares them with profiling/ToC/chunking callers.
"""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import selectors
import shutil
import signal
import subprocess
import time


class PdfBackendError(RuntimeError):
    pass


def executable():
    configured = os.environ.get('RPG_PDF_READER')
    path = (shutil.which(configured) if configured else
            str(Path(__file__).resolve().parents[1] / 'pdf-reader/target/release/rpg-pdf-reader'))
    if not path or not os.path.isfile(path) or not os.access(path, os.X_OK):
        raise PdfBackendError('Rust PDF worker unavailable. Build with: cargo build --release '
                              '--manifest-path pdf-translators/pdf-reader/Cargo.toml; '
                              'or set RPG_PDF_READER to its executable.')
    return path


def check_worker():
    """Validate setup once before a batch can classify any source as skipped."""
    path = executable()
    try:
        result = subprocess.run([path, '--version'], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise PdfBackendError(f'Cannot start Rust PDF reader: {error}. Rebuild with cargo build '
                              '--release --manifest-path pdf-translators/pdf-reader/Cargo.toml') from error
    if result.returncode or not result.stdout.startswith('rpg-pdf-reader '):
        raise PdfBackendError('Invalid Rust PDF reader build. Run cargo build --release '
                              '--manifest-path pdf-translators/pdf-reader/Cargo.toml')
    return path


def _integer(value, minimum=0):
    return type(value) is int and value >= minimum


def _request(path, pages, timeout):
    command = [executable(), 'inspect' if pages is None else 'extract', str(path)]
    if pages is not None:
        command += ['--pages', ','.join(map(str, pages))]
    expected = [] if pages is None else pages
    deadline = time.monotonic() + timeout
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=True)
    selector = selectors.DefaultSelector()
    buffer = bytearray()
    stderr = bytearray()
    document = end = None
    staged = {}
    completed = False

    def record(line):
        nonlocal document, end
        try:
            item = json.loads(line)
        except (ValueError, UnicodeError) as error:
            raise PdfBackendError('Invalid JSON from Rust PDF worker') from error
        if not isinstance(item, dict) or end is not None:
            raise PdfBackendError('Unexpected PDF protocol record')
        kind = item.get('type')
        if kind == 'error':
            page = f" (page {item['page']})" if 'page' in item else ''
            raise PdfBackendError(f"Rust PDF reader {item.get('code', 'error')}{page}: {item.get('message', '')}")
        if kind == 'document':
            if document is not None or item.get('protocol') != 1 or type(item.get('protocol')) is not int:
                raise PdfBackendError('Unsupported or duplicate PDF protocol document')
            n = item.get('page_count')
            if (not _integer(n, 1) or item.get('requested') != expected
                    or not isinstance(item.get('backend'), str) or not item['backend']
                    or not isinstance(item.get('build'), str) or not item['build']):
                raise PdfBackendError('Invalid PDF document metadata')
            outline = item.get('outline')
            if not isinstance(outline, list):
                raise PdfBackendError('Invalid PDF outline')
            for entry in outline:
                if (not isinstance(entry, dict) or not _integer(entry.get('level'), 1)
                    or not isinstance(entry.get('title'), str)
                    or (entry.get('page') is not None and
                        (not _integer(entry['page'], 1) or entry['page'] > n))):
                    raise PdfBackendError('Invalid PDF outline entry')
            document = item
        elif kind == 'page':
            page = item.get('page')
            if (document is None or not _integer(page, 1) or page not in expected
                    or page in staged or not isinstance(item.get('text'), str)
                    or page != expected[len(staged)]):
                raise PdfBackendError('Unexpected, duplicate or invalid PDF page')
            staged[page] = item['text']
        elif kind == 'end':
            if (document is None or item.get('complete') is not True
                    or not all(_integer(item.get(k)) for k in ['requested', 'emitted', 'failed'])
                    or item['requested'] != len(expected) or item['emitted'] != len(staged)
                    or item['failed'] != 0 or list(staged) != expected):
                raise PdfBackendError('Incomplete PDF extraction')
            end = item
        else:
            raise PdfBackendError('Unknown PDF protocol record')

    try:
        for stream in (process.stdout, process.stderr):
            selector.register(stream, selectors.EVENT_READ)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise PdfBackendError('Rust PDF worker timed out')
            for key, _ in selector.select(min(remaining, 0.2)):
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                if key.fileobj is process.stderr:
                    stderr.extend(chunk)
                    del stderr[:-4096]
                    continue
                buffer.extend(chunk)
                while b'\n' in buffer:
                    line, _, rest = buffer.partition(b'\n')
                    if len(line) > 32 * 1024 * 1024:
                        raise PdfBackendError('PDF protocol record exceeds size limit')
                    record(line)
                    buffer[:] = rest
                if len(buffer) > 32 * 1024 * 1024:
                    raise PdfBackendError('PDF protocol record exceeds size limit')
        try:
            code = process.wait(timeout=max(0.001, deadline - time.monotonic()))
        except subprocess.TimeoutExpired as error:
            raise PdfBackendError('Rust PDF worker timed out') from error
        if buffer or document is None or end is None or code != 0:
            diagnostic = stderr.decode('utf-8', errors='replace')[-1000:]
            raise PdfBackendError(f'Rust PDF worker failed or returned a truncated stream: {diagnostic}')
        completed = True
        return document, staged
    finally:
        selector.close()
        # A wrapper can exit while a descendant still owns its pipes. On any
        # failed request kill the group even if the original leader exited.
        if not completed or process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.wait()
        process.stdout.close()
        process.stderr.close()


@dataclass
class _Page:
    text: str

    def get_text(self, kind='text'):
        if kind != 'text':
            raise ValueError('Rust reader supports text extraction only')
        return self.text


class RustDocument:
    def __init__(self, path, *, timeout=None):
        self.path = Path(path)
        self.timeout = timeout if timeout is not None else float(os.environ.get('RPG_PDF_TIMEOUT', '300'))
        if self.timeout <= 0:
            raise ValueError('PDF timeout must be positive')
        self.facts, _ = _request(self.path, None, self.timeout)
        self.page_count = self.facts['page_count']
        self.backend = {'name': self.facts['backend'], 'version': self.facts['build'], 'protocol': 1}
        self.pages = {}
        self.closed = False
        self._stamp = self._source_stamp()

    def _source_stamp(self):
        try:
            stat = self.path.stat()
            return stat.st_size, stat.st_mtime_ns
        except OSError as error:
            raise PdfBackendError(f'PDF source unavailable: {error}') from error

    def read_pages(self, pages):
        if self.closed:
            raise PdfBackendError('PDF document is closed')
        pages = list(pages)
        if any(not _integer(p, 1) or p > self.page_count for p in pages):
            raise ValueError('PDF page selection out of range')
        missing = sorted(set(pages) - self.pages.keys())
        if not missing:
            return
        if self._source_stamp() != self._stamp:
            raise PdfBackendError('PDF changed during extraction')
        facts, staged = _request(self.path, missing, self.timeout)
        if (any(facts[k] != self.facts[k] for k in ['page_count', 'outline', 'backend', 'build'])
                or self._source_stamp() != self._stamp):
            raise PdfBackendError('PDF or backend changed during extraction')
        self.pages.update(staged)

    def read_all(self):
        self.read_pages(range(1, self.page_count + 1))

    def load_page(self, index):
        if not _integer(index) or index >= self.page_count:
            raise ValueError('PDF page index out of range')
        if index + 1 not in self.pages:
            self.read_all()
        return _Page(self.pages[index + 1])

    def get_toc(self, simple=True):
        entries = self.facts['outline']
        out = []
        for index, entry in enumerate(entries):
            page = entry['page']
            if page is None:
                descendants = []
                for child in entries[index + 1:]:
                    if child['level'] <= entry['level']:
                        break
                    if child['page'] is not None:
                        descendants.append(child['page'])
                page = min(descendants) if descendants else None
            if page is not None:
                out.append([entry['level'], entry['title'], page])
        return out

    def close(self):
        self.pages.clear()
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
