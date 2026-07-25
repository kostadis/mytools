#!/usr/bin/env python3
"""Re-transcribe a D&D session's Zoom .m4a recording into a more accurate
WebVTT, reusing the existing Zoom .vtt's cue boundaries/speaker labels and
biasing faster-whisper (run on the DGX Spark) with campaign-specific
vocabulary. See CLAUDE.md for the full design and why each piece exists.

Usage:
  retranscribe.py <audio.m4a> <zoom.vtt> [options]

Happy path (audio + Zoom VTT already sitting together in a session dir):
  cd ~/campaigns/obelisk/summaries/007
  python ~/src/mytools/audio-to-vtt/retranscribe.py \\
    GMT20260718-212700_Recording.m4a \\
    GMT20260718-212700_Recording.transcript.vtt
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import proper_noun_review  # noqa: E402
import spark_runner  # noqa: E402
import vocab  # noqa: E402
import vtt_scaffold  # noqa: E402

_VTT_SPELL_PASS_APPLY = (
    Path(__file__).resolve().parents[1]
    / "dotfiles" / "claude" / "skills" / "vtt-spell-pass" / "apply_replacements.py"
)


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("audio", type=Path, help="Path to the session's .m4a recording")
    ap.add_argument("vtt", type=Path, help="Path to the matching Zoom .vtt transcript")
    ap.add_argument("--campaign-root", type=Path, default=None,
                    help="Campaign root (default: auto-detected by walking up from <vtt>)")
    ap.add_argument("--model-size", default="large-v3")
    ap.add_argument("--compute-type", default="int8_float16")
    ap.add_argument("--spark-host", choices=["auto", "spark", "spark2"], default="auto")
    ap.add_argument("--min-free-gb", type=float, default=4.0)
    ap.add_argument("--max-group-seconds", type=float, default=25.0)
    ap.add_argument("--token-budget", type=int, default=200)
    ap.add_argument("--output", type=Path, default=None,
                    help="Raw output path (default: '<vtt-stem>.retranscribed.vtt' alongside <vtt>)")
    ap.add_argument("--skip-glossary-pass", action="store_true")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print the cue-group plan + hotwords preview; no Spark contact")
    ap.add_argument("--smoke-test", type=float, nargs="?", const=300.0, default=None,
                    help="Transcribe only the first N seconds (default 300) on the real "
                         "target box and report a measured RTF before running the full job")
    return ap


def main(argv=None) -> int:
    args = build_arg_parser().parse_args(argv)

    if not args.audio.exists():
        print(f"ERROR: audio file not found: {args.audio}", file=sys.stderr)
        return 1
    if not args.vtt.exists():
        print(f"ERROR: VTT file not found: {args.vtt}", file=sys.stderr)
        return 1

    campaign_root = args.campaign_root or vocab.find_campaign_root(args.vtt.resolve().parent)
    if campaign_root:
        print(f"Campaign root: {campaign_root}")
        vocabulary = vocab.gather_vocabulary(campaign_root)
    else:
        print("WARNING: no campaign root found/given -- proceeding with no vocabulary bias.")
        vocabulary = []
    print(f"Vocabulary candidates: {len(vocabulary)}")

    vtt_text = args.vtt.read_text(encoding="utf-8", errors="replace")
    cues = vtt_scaffold.parse_zoom_vtt(vtt_text)
    if not cues:
        print("ERROR: no cues parsed from the VTT -- is this a Zoom WebVTT export?", file=sys.stderr)
        return 1
    groups = vtt_scaffold.group_cues(cues, max_group_seconds=args.max_group_seconds)
    skip_mask = [vtt_scaffold.is_system_caption_speaker(g.speaker) for g in groups]
    transcribable = [g for g, skip in zip(groups, skip_mask) if not skip]
    total_speech = sum(g.end - g.start for g in groups)
    print(f"Parsed {len(cues)} cues -> {len(groups)} cue groups "
          f"({total_speech / 60:.1f} min of speech spanning {groups[-1].end / 60:.1f} min)")
    if len(transcribable) < len(groups):
        print(f"Skipping re-transcription for {len(groups) - len(transcribable)} Zoom "
              f"system-caption cue group(s) (e.g. \"Audio shared by X\") -- faster-whisper "
              f"reliably hallucinates on these; keeping Zoom's original text for them.")

    if args.dry_run:
        print("\n--dry-run: no Spark contact. Sample cue groups:")
        for g, skip in list(zip(groups, skip_mask))[:10]:
            marker = " [skip: system caption]" if skip else ""
            print(f"  [{vtt_scaffold.seconds_to_timestamp(g.start)} -> "
                  f"{vtt_scaffold.seconds_to_timestamp(g.end)}] {g.speaker}: "
                  f"{g.original_text[:70]!r}{marker}")
        if len(groups) > 10:
            print(f"  ... and {len(groups) - 10} more")
        preview = ", ".join(vocabulary[:40])
        print(f"\nVocabulary (first 40 of {len(vocabulary)}): {preview}")
        return 0

    session_id = args.audio.stem
    manifest = {
        "model_size": args.model_size,
        "compute_type": args.compute_type,
        "language": "en",
        "token_budget": args.token_budget,
        "vocabulary": vocabulary,
        "cue_groups": [{"start": g.start, "end": g.end, "speaker": g.speaker} for g in transcribable],
    }

    host = spark_runner.pick_host(args.spark_host, args.min_free_gb)
    print(f"Target Spark host: {host}")

    if args.smoke_test is not None:
        print(f"\n--smoke-test: transcribing first {args.smoke_test:.0f}s only...")
        smoke_manifest = dict(manifest)
        smoke_manifest["smoke_test_seconds"] = args.smoke_test
        t0 = time.monotonic()
        result = spark_runner.run_remote_transcription(
            args.audio, smoke_manifest, host=host, session_id=f"{session_id}-smoke")
        wall = time.monotonic() - t0
        rtf = result.get("real_time_factor")
        print(f"\nSmoke test done in {wall:.1f}s wall-clock. "
              f"device_used={result.get('device_used')} RTF={rtf}")
        if rtf:
            est_minutes = rtf * (groups[-1].end / 60.0)
            print(f"Extrapolated full-session estimate: ~{est_minutes:.1f} min")
        try:
            answer = input("Continue with the full session? [y/N] ").strip().lower()
        except EOFError:
            answer = "n"
        if answer != "y":
            print("Stopped after smoke test.")
            return 0

    print(f"\nRunning full transcription ({len(transcribable)} cue groups) on {host}...")
    result = spark_runner.run_remote_transcription(
        args.audio, manifest, host=host, session_id=session_id)
    print(f"Done in {result.get('elapsed_seconds', 0):.1f}s "
          f"(device_used={result.get('device_used')}, RTF={result.get('real_time_factor')})")

    result_texts = iter(r["text"] for r in result["results"])
    texts = [g.original_text if skip else next(result_texts)
             for g, skip in zip(groups, skip_mask)]
    raw_vtt = vtt_scaffold.render_vtt(groups, texts)

    raw_path = args.output or args.vtt.with_name(args.vtt.stem + ".retranscribed.vtt")
    raw_path.write_text(raw_vtt, encoding="utf-8")
    print(f"Wrote {raw_path}")

    cleaned_path = raw_path.with_name(raw_path.stem + ".cleaned.vtt")
    glossary_path = (campaign_root / "notes" / "vtt_transcription_corrections.md") if campaign_root else None
    if not args.skip_glossary_pass and glossary_path and glossary_path.exists():
        proc = subprocess.run(
            [sys.executable, str(_VTT_SPELL_PASS_APPLY),
             "--vtt", str(raw_path), "--glossary", str(glossary_path), "--output", str(cleaned_path)],
            capture_output=True, text=True)
        print(proc.stdout)
        if proc.returncode != 0:
            print(f"WARNING: glossary pass failed: {proc.stderr}", file=sys.stderr)
            cleaned_path = raw_path
    else:
        cleaned_path = raw_path
        print("Skipping glossary post-pass (no glossary found or --skip-glossary-pass set).")

    review_path = None
    if vocabulary:
        retr_cues = vtt_scaffold.parse_zoom_vtt(
            cleaned_path.read_text(encoding="utf-8", errors="replace"))
        try:
            flagged = proper_noun_review.review(groups, retr_cues, vocabulary)
        except ValueError as e:
            print(f"WARNING: proper-noun review skipped: {e}", file=sys.stderr)
        else:
            report = proper_noun_review.render_report(flagged, len(groups), args.vtt, cleaned_path)
            review_path = cleaned_path.with_name(cleaned_path.stem + ".proper_nouns.md")
            review_path.write_text(report, encoding="utf-8")
            print(f"Scanned {len(groups)} cue groups, flagged {len(flagged)} possible "
                  f"proper-noun misses in Zoom's transcript. Wrote {review_path}")

    print(f"\nNext step: run /vtt-spell-pass on {cleaned_path}")
    if review_path:
        print(f"Also check {review_path} for spots the retranscription suggests Zoom's "
              f"transcript missed a name -- Zoom's own wording is left untouched either way.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
