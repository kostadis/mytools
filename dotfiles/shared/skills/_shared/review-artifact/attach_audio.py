#!/usr/bin/env python3
"""Attach an original-recording WAV clip to one shared review card.

This renders evidence only: no extraction, ASR, transcript edits, or rulings.
"""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import html
import json
import math
from pathlib import Path
import wave


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def timestamp(seconds: float) -> str:
    millis = round(seconds * 1000)
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    whole, fraction = divmod(millis, 1000)
    return f'{hours:02}:{minutes:02}:{whole:02}.{fraction:03}'


def attach(spec: dict, card_id: str, clip: Path, source: Path,
           start: float, end: float) -> dict:
    if not all(math.isfinite(n) for n in (start, end)) or start < 0 or end <= start:
        raise ValueError('Use finite recording-relative times with 0 <= start < end.')
    result = copy.deepcopy(spec)
    items = result.get('items', [])
    ids = [item.get('id') for item in items]
    if ids.count(card_id) != 1 or len(ids) != len(set(ids)):
        raise ValueError('The card id must occur exactly once; all item ids must be unique.')
    card = next(item for item in items if item['id'] == card_id)
    if card.get('audio_evidence') or '<audio' in card.get('ev', '').lower():
        raise ValueError('Card already has audio. Start from its unaugmented items file.')
    if not source.is_file():
        raise ValueError(f'Source recording is missing: {source}')
    with wave.open(str(clip), 'rb') as recording:
        frames, rate = recording.getnframes(), recording.getframerate()
        if frames <= 0 or rate <= 0:
            raise ValueError('The WAV clip must contain audio.')
        duration = frames / rate
        if abs(duration - (end - start)) > max(.001, 1 / rate):
            raise ValueError('Clip duration does not match the declared recording time range.')
    data = clip.read_bytes()
    card['audio_evidence'] = {
        'source_recording': str(source.resolve()),
        'source_sha256': sha256_file(source),
        'clip': str(clip.resolve()),
        'clip_sha256': hashlib.sha256(data).hexdigest(),
        'start_s': start, 'end_s': end, 'duration_s': duration,
        'mime_type': 'audio/wav',
    }
    encoded = base64.b64encode(data).decode('ascii')
    player = (
        f'<div data-review-audio="{html.escape(card_id, quote=True)}">'
        f'<b>Original recording · {timestamp(start)}–{timestamp(end)}</b><br>'
        '<audio controls preload="none" style="width:100%;max-width:640px" '
        f'src="data:audio/wav;base64,{encoded}"></audio></div>'
    )
    card['ev'] = player + card.get('ev', '')
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--items', required=True, type=Path)
    parser.add_argument('--id', required=True, dest='card_id')
    parser.add_argument('--clip', required=True, type=Path)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--start', required=True, type=float)
    parser.add_argument('--end', required=True, type=float)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    if args.out.resolve() == args.items.resolve() or args.out.exists():
        parser.error('--out must be a new file; the input items are preserved.')
    try:
        spec = json.loads(args.items.read_text(encoding='utf-8'))
        result = attach(spec, args.card_id, args.clip, args.source, args.start, args.end)
    except (OSError, ValueError, KeyError, TypeError, wave.Error) as error:
        parser.error(str(error))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Attached original audio to {args.card_id}; no decisions or transcript text changed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
