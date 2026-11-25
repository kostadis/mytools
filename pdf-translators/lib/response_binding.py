"""Versioned, prompt-bound Rust response namespaces; historical files stay put."""
import hashlib
import json
import os
from pathlib import Path
import tempfile


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.' + path.name + '.', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def response_directory(base, requests, *, system, model, backend, create, settings=None):
    """Bind an ordered request set without keeping another document of prompts.

    Namespacing the whole set deliberately favors conservative reuse: changing
    a chunk or settings selects a new directory; identical partial runs resume.
    Each request has its own digest in the manifest, including its exact prompt.
    """
    manifest = {'version': 1, 'backend': backend, 'system': system, 'model': model,
                'settings': settings or {}, 'requests': []}
    for cid, prompt in requests:
        digest = hashlib.sha256(prompt.encode('utf-8')).hexdigest()
        manifest['requests'].append([cid, digest])
    encoded = json.dumps(manifest, sort_keys=True, ensure_ascii=False,
                         separators=(',', ':')).encode('utf-8')
    digest = hashlib.sha256(encoded).hexdigest()
    base = Path(base)
    marker = 'rust-requests.json'
    directory = base if (base / marker).is_file() else base / 'rust-pdf-v1' / digest
    binding = directory / marker
    if binding.exists():
        try:
            saved = json.loads(binding.read_text(encoding='utf-8'))
        except (ValueError, OSError) as error:
            raise RuntimeError('Rust response binding is unreadable') from error
        if saved != manifest:
            raise RuntimeError('Rust response binding mismatch; use the matching extraction/settings')
    elif create:
        if directory.exists() and any(directory.iterdir()):
            raise RuntimeError('Cannot bind pre-existing unbound response files')
        atomic_json(binding, manifest)
    else:
        raise RuntimeError('No matching bound response set; legacy responses require their original extraction')
    return directory


def batch_record_path(directory, batch_id):
    import re
    if not isinstance(batch_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,256}', batch_id):
        raise RuntimeError('Invalid batch identifier')
    return Path(directory) / 'batches' / f'{batch_id}.json'


def save_batch_record(directory, batch_id, cids):
    path = batch_record_path(directory, batch_id)
    value = {'id': batch_id, 'cids': list(cids)}
    if path.exists():
        if json.loads(path.read_text()) != value:
            raise RuntimeError('Conflicting immutable batch request binding')
        return
    atomic_json(path, value)
