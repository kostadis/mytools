#!/usr/bin/env python3
"""Deterministic half of the batched spell pass: Phase 0, Phase 1, and the
sibling lookups for Phase 2.5.

One directory per invocation. Emits ``scan.json`` containing every candidate
with its contexts and the sibling transcription's text at each span. It makes
no judgments: ``sibling_evidence.kind`` is left null for the agent to fill.

Why this is a script and not agent tool-calls
---------------------------------------------
Fourteen agents improvising this pipeline produce fourteen slightly different
residuals, and a residual computed differently is not comparable at the merge.
Pinning it here means the only thing that varies between agents is the judgment
the agent is actually for.

Isolation: every intermediate goes under --scratch/<dir>/. SKILL.md's documented
commands hardcode /tmp paths, which five concurrent agents would overwrite for
each other -- silently, between one agent's apply and its re-scan.

Usage:
    batch_scan.py --campaign-dir <campaign> --dir 20250812-chapter-08 \
        --scratch /path/to/scratch [--npcs-dir <campaign>/notes/npcs]

Run data (manifest.json, known_flat.txt, one directory per chapter) lives in
the campaign under --batch-dir (default <campaign>/notes/spell_pass_batch);
this script lives with the vtt-spell-pass skill, whose scripts it calls.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# The vtt-spell-pass skill directory: this file lives in its batch/ subdir.
SP = Path(__file__).resolve().parent.parent

PY = sys.executable


def run(cmd: list[str], stdin_data: str | None = None) -> str:
    """Run a skill script with a PINNED hash seed.

    cluster_unknowns.py builds its known-name list by iterating a set
    (cluster_unknowns.py:296-298), so under Python's default per-process hash
    randomisation the list order -- and therefore which canonical a token binds
    to -- changes between runs. Measured: three identical invocations produced
    three different cluster sets. Serially that is merely surprising; across 14
    agents it means no two residuals are comparable and the merge is garbage.
    """
    env = {**os.environ, "PYTHONHASHSEED": "0"}
    r = subprocess.run(cmd, capture_output=True, text=True, input=stdin_data, env=env)
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:3])}... failed:\n{r.stderr[-2000:]}")
    return r.stdout


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--campaign-dir", required=True, type=Path)
    ap.add_argument("--batch-dir", type=Path,
                    help="run data (default: <campaign>/notes/spell_pass_batch)")
    ap.add_argument("--npcs-dir", type=Path,
                    help="NPC dossier dir; omit if the campaign has none")
    ap.add_argument("--dir", required=True)
    ap.add_argument("--scratch", required=True, type=Path)
    args = ap.parse_args()

    CAMP = args.campaign_dir.expanduser().resolve()
    BATCH = (args.batch_dir or CAMP / "notes" / "spell_pass_batch").expanduser().resolve()
    GLOSSARY = CAMP / "notes" / "vtt_transcription_corrections.md"
    STATE = CAMP / "notes" / ".vtt_spell_pass_state.json"
    KNOWN_FLAT = BATCH / "known_flat.txt"
    for need in (BATCH / "manifest.json", GLOSSARY, STATE, KNOWN_FLAT):
        if not need.is_file():
            print(f"error: missing {need}", file=sys.stderr)
            return 2

    manifest = json.loads((BATCH / "manifest.json").read_text())
    if args.dir not in manifest["dirs"]:
        print(f"unknown dir {args.dir!r}", file=sys.stderr)
        return 2
    m = manifest["dirs"][args.dir]
    target = CAMP / m["target_file"]
    sibling = CAMP / m["sibling_file"]

    work = args.scratch / args.dir
    work.mkdir(parents=True, exist_ok=True)

    # --- Phase 0 -----------------------------------------------------------
    phase0 = json.loads(run([
        PY, str(SP / "prepare_input.py"), "--input", str(target),
        "--scan-copy", str(work / "scan.txt"), "--json",
    ]))
    if phase0["duplication"]["duplicated"]:
        # Every occurrence count downstream would be doubled. Refuse rather
        # than hand the GM inflated evidence.
        print(json.dumps({"error": "duplication_detected", "phase0": phase0}, indent=2))
        return 3

    scan = work / "scan.txt"
    known = ["--glossary", str(GLOSSARY), "--extra-known", str(KNOWN_FLAT)]
    if args.npcs_dir:
        known += ["--npcs-dir", str(args.npcs_dir)]

    # --- Phase 1: collapse the set first, then re-scan ----------------------
    preview = work / "preview.txt"
    run([PY, str(SP / "apply_replacements.py"), "--vtt", str(scan),
         "--glossary", str(GLOSSARY), "--output", str(preview)])

    n_scan, n_prev = len(scan.read_text().splitlines()), len(preview.read_text().splitlines())
    if n_scan != n_prev:
        raise RuntimeError(f"preview line count {n_prev} != scan {n_scan} — "
                           f"scratch collision or a rule that eats lines")

    raw = json.loads(run([
        PY, str(SP / "find_unknowns.py"), "--vtt", str(preview),
        *known, "--min-count", "1",
    ]))
    clusters = json.loads(run(
        [PY, str(SP / "cluster_unknowns.py"), *known],
        stdin_data=json.dumps(raw),
    ))["clusters"]

    known_count = raw["known_names_count"]
    if known_count < 50:
        raise RuntimeError(f"known_names_count={known_count} — known-name inputs not read")

    # --- state filter: tokens the GM already dismissed ----------------------
    ignored = {t.lower() for t in json.loads(STATE.read_text())["ignored_tokens"]}

    # --- Phase 2.5 inputs: one sibling lookup per member --------------------
    # Import sibling_context rather than shelling out per member: the script
    # re-parses the whole sibling file on every invocation, which for ~150
    # members is minutes of redundant parsing. Same functions, parsed once.
    sys.path.insert(0, str(SP))
    import sibling_context  # noqa: E402
    sib_utts = sibling_context.utterances(sibling)

    # Case-SENSITIVE search of the ORIGINAL text for the lowercased token. The
    # question is "does this wrong-form ever occur lowercase?", because
    # apply_replacements.py matches with re.IGNORECASE and would rewrite ordinary
    # prose. Lowercasing the haystack first (an earlier bug here) makes the test
    # match in any case, so it fired for 147/153 members and would have
    # suppressed every genuine correction.
    target_text = target.read_text(encoding="utf-8", errors="replace")
    out_clusters = []
    for c in clusters:
        members = []
        for mem in c.get("members", []):
            if mem["token"].lower() in ignored:
                continue
            ctx = mem.get("context") or ""
            ev = {"kind": None, "score": None, "sibling_verbatim": None}
            if ctx:
                hits = sibling_context.best_matches(sib_utts, ctx, 1)
                if hits:
                    ev["score"] = hits[0]["score"]
                    ev["sibling_verbatim"] = hits[0]["text"]
            # lowercase-in-this-target gate (corpus-wide gate runs at merge)
            low = re.search(rf"\b{re.escape(mem['token'].lower())}\b", target_text)
            members.append({
                "token": mem["token"],
                "count": mem["count"],
                "verbatim": ctx,
                "sibling_evidence": ev,
                "lowercase_in_target": bool(low),
                "kind": None,             # agent fills
                "recommendation": None,   # agent fills
            })
        if members:
            out_clusters.append({
                "id": c["id"],
                "proposed_canonical": c.get("proposed_canonical"),
                "confidence": c.get("confidence"),
                "reason": c.get("reason"),
                "members": members,
            })

    scan_out = {
        "schema_version": 1,
        "dir": args.dir,
        "target_file": m["target_file"],
        "target_sha256": sha256(target),
        "target_format": phase0["format"],
        "speakers": phase0["speakers"],
        "duplication_detected": False,
        "sibling": {
            "path": m["sibling_file"],
            "transcriber_kind": m["sibling_kind"],
            "name_evidence_admissible": False,
        },
        "glossary_sha256_at_scan": sha256(GLOSSARY),
        "known_names_count": known_count,
        "raw_unknown_count": len(raw["unknown_propers"]),
        "clusters_after_ignore_filter": len(out_clusters),
        "clusters": out_clusters,
    }
    (BATCH / args.dir).mkdir(parents=True, exist_ok=True)
    (BATCH / args.dir / "scan.json").write_text(
        json.dumps(scan_out, indent=2) + "\n", encoding="utf-8")

    print(f"{args.dir}: format={phase0['format']} known={known_count} "
          f"raw_unknowns={len(raw['unknown_propers'])} "
          f"clusters={len(out_clusters)} "
          f"members={sum(len(c['members']) for c in out_clusters)}")
    print(f"  -> {BATCH / args.dir / 'scan.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
