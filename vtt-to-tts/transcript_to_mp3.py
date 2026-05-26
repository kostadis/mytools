#!/usr/bin/env python3
"""
Convert Zoom closed-caption transcript to MP3 with per-speaker voices.
Uses edge-tts (free, no API key needed). No ffmpeg required.

Install deps:
    pip install edge-tts

Chunks are cached next to the output file (in <output>.chunks/).
Re-running with a changed VOICE_MAP only regenerates affected chunks.
"""

import asyncio
import io
import json
import re
import sys
from pathlib import Path

# --- Voice assignments (edge-tts voice names) ---
VOICE_MAP = {
    "Kostadis Roussos":       "en-US-GuyNeural",
    "Dimos Stathakis":        "en-US-ChristopherNeural",
    "Nicholas Roussos":       "en-US-RogerNeural",
    "Thomas Kolivakis":       "en-US-EricNeural",
    "george":                 "en-US-AndrewNeural",
    "Nikhil Reddy Mettupally": "en-US-BrianNeural",
}
DEFAULT_VOICE = "en-US-GuyNeural"

# Silence between utterances: 16 silent MPEG1 Layer3 frames ≈ 400ms
_SILENT_FRAME = bytes([0xFF, 0xFB, 0x90, 0x00, *([0x00] * 413)])
SILENCE_BYTES = _SILENT_FRAME * 16


_ZOOM_PATTERN = re.compile(
    r"\[([^\]]+)\]\s+\d{2}:\d{2}:\d{2}\s*\n(.*?)(?=\n\[|\Z)", re.DOTALL
)
# Otter markdown export: **Speaker Name**HH:MM:SS\n\n<lines>\n\n**Next Speaker**...
_OTTER_PATTERN = re.compile(
    r"\*\*([^*\n]+?)\*\*\s*\d{2}:\d{2}:\d{2}\s*\n(.*?)(?=\n\*\*[^*\n]+?\*\*\s*\d{2}:\d{2}:\d{2}|\Z)",
    re.DOTALL,
)


def _clean_utterance(text: str) -> str:
    # Collapse internal blank lines and join paragraphs into one TTS-friendly line.
    return " ".join(line.strip() for line in text.strip().splitlines() if line.strip())


def parse_transcript(path: Path) -> list[tuple[str, str]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    # Try Zoom first; fall back to Otter markdown.
    for pattern in (_ZOOM_PATTERN, _OTTER_PATTERN):
        utterances = []
        for m in pattern.finditer(text):
            speaker = m.group(1).strip()
            content = _clean_utterance(m.group(2))
            if content:
                utterances.append((speaker, content))
        if utterances:
            return utterances
    return []


def group_consecutive(utterances: list[tuple[str, str]]) -> list[tuple[str, str]]:
    if not utterances:
        return []
    grouped = [list(utterances[0])]
    for speaker, text in utterances[1:]:
        if speaker == grouped[-1][0]:
            grouped[-1][1] += " " + text
        else:
            grouped.append([speaker, text])
    return [(s, t) for s, t in grouped]


async def tts_to_bytes(speaker: str, text: str, retries: int = 3) -> bytes:
    import edge_tts
    voice = VOICE_MAP.get(speaker, DEFAULT_VOICE)
    last_err = None
    for attempt in range(retries):
        try:
            buf = io.BytesIO()
            communicate = edge_tts.Communicate(text, voice)
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    buf.write(chunk["data"])
            data = buf.getvalue()
            if data:
                return data
            raise ValueError("Empty audio returned")
        except Exception as e:
            last_err = e
            wait = 2 ** attempt
            print(f"    [retry {attempt+1}/{retries} after {wait}s: {e}]")
            await asyncio.sleep(wait)
    print(f"    [SKIPPED: {last_err}]")
    return b""


async def main(transcript_path: str, output_mp3: str) -> None:
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        print("ERROR: edge-tts not installed. Run: pip install edge-tts")
        sys.exit(1)

    path = Path(transcript_path)
    if not path.exists():
        print(f"ERROR: File not found: {transcript_path}")
        sys.exit(1)

    out_path = Path(output_mp3)
    cache_dir = out_path.with_suffix("") .with_name(out_path.stem + ".chunks")
    cache_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = cache_dir / "manifest.json"

    print(f"Parsing transcript: {path.name}")
    utterances = parse_transcript(path)
    utterances = group_consecutive(utterances)
    print(f"  {len(utterances)} utterances after grouping")

    speakers = set(s for s, _ in utterances)
    for sp in sorted(speakers):
        voice = VOICE_MAP.get(sp, DEFAULT_VOICE)
        print(f"  {sp!r} → {voice}")

    # Load existing manifest to detect which chunks need regeneration
    manifest: dict[str, str] = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())

    total = len(utterances)
    skipped = 0

    for i, (speaker, text) in enumerate(utterances):
        chunk_path = cache_dir / f"chunk_{i:05d}.mp3"
        voice = VOICE_MAP.get(speaker, DEFAULT_VOICE)
        cache_key = f"{voice}|{text}"

        # Use cached chunk if voice+text unchanged and file exists
        if chunk_path.exists() and manifest.get(str(i)) == cache_key:
            print(f"  [{i+1}/{total}] {speaker[:20]:<20} [cached]")
            continue

        print(f"  [{i+1}/{total}] {speaker[:20]:<20} {text[:55]!r}...")
        audio = await tts_to_bytes(speaker, text)
        if audio:
            chunk_path.write_bytes(audio)
            manifest[str(i)] = cache_key
            manifest_path.write_text(json.dumps(manifest))
        else:
            # Clear stale cache entry so it retries next run
            manifest.pop(str(i), None)
            if chunk_path.exists():
                chunk_path.unlink()
            skipped += 1

        await asyncio.sleep(0.1)

    # Assemble final MP3 from cached chunks
    print(f"\nAssembling {total - skipped} chunks → {output_mp3}")
    with out_path.open("wb") as out_file:
        for i in range(total):
            chunk_path = cache_dir / f"chunk_{i:05d}.mp3"
            if chunk_path.exists():
                out_file.write(chunk_path.read_bytes())
                if i < total - 1:
                    out_file.write(SILENCE_BYTES)

    size_mb = out_path.stat().st_size / 1_048_576
    print(f"Done! {output_mp3} ({size_mb:.1f} MB)")
    if skipped:
        print(f"  {skipped} utterances skipped (TTS failed). Re-run to retry.")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(f"Usage: python3 {sys.argv[0]} <transcript.txt> <output.mp3>")
        sys.exit(1)

    asyncio.run(main(sys.argv[1], sys.argv[2]))
