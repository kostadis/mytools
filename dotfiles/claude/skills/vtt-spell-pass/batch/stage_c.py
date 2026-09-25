#!/usr/bin/env python3
"""Stage C: assemble, dry-run, apply, verify.

Dry-run FIRST and let the GM see the doubling list before a single file is
written. Detecting a doubling rule after the glossary is committed is worthless:
lint_glossary.py provably cannot catch that class (the row is fine in isolation
and only doubles when the transcript supplies the surname), and by then every
cleaned file has to be regenerated.

Usage:
    stage_c.py --campaign-dir <campaign> --scratch <dir> --dry-run [--batch-dir DIR]

It applies the glossary to every manifest target into --scratch, and reports
chained rules, doubling artefacts the apply introduced, and whether a second
apply changes anything (idempotency). Results go to
<batch-dir>/stage_c_dryrun.json. Nothing under summaries/ is written.

NOTE: --apply is not implemented. It currently runs the same analysis as
--dry-run and exits 0 without writing cleaned files, a ledger, or a
verification. Writing the cleaned transcripts is still done per chapter by
vtt-spell-pass Phase 5.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# The vtt-spell-pass skill directory: this file lives in its batch/ subdir.
SP = Path(__file__).resolve().parent.parent
# Set from --campaign-dir / --batch-dir in main(); rows() and apply_to() read them.
CAMP = BATCH = GLOSSARY = STATE = None
PY = sys.executable
ENV = {**os.environ, "PYTHONHASHSEED": "0"}

DOUBLE_RE = re.compile(r"\b(\w+)(\s+\1)\b", re.I)


def rows() -> list[tuple[int, str, str]]:
    out = []
    for i, line in enumerate(GLOSSARY.read_text(encoding="utf-8").splitlines(), 1):
        if not line.startswith("|") or line.startswith("|---") or "Wrong" in line:
            continue
        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) < 2:
            continue
        m = re.search(r"\*\*(.+?)\*\*", cols[1])
        canon = (m.group(1) if m else cols[1]).strip()
        for w in cols[0].split(","):
            w = w.strip()
            if w:
                out.append((i, w, canon))
    return out


def chains(rs):
    """A canonical that is itself another row's wrong-form. Output depends on
    rule order, so the glossary is not idempotent until these are resolved."""
    wrong = {w.lower(): (i, c) for i, w, c in rs}
    out = []
    for i, w, c in rs:
        if c.lower() in wrong:
            j, c2 = wrong[c.lower()]
            if c2.lower() != c.lower():
                out.append((i, w, c, j, c2))
    return out


def apply_to(src: Path, dst: Path) -> str:
    r = subprocess.run(
        [PY, str(SP / "apply_replacements.py"), "--vtt", str(src),
         "--glossary", str(GLOSSARY), "--output", str(dst)],
        capture_output=True, text=True, env=ENV)
    if r.returncode != 0:
        raise RuntimeError(f"{src.name}: {r.stderr[-500:]}")
    return r.stdout


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--campaign-dir", required=True, type=Path)
    ap.add_argument("--batch-dir", type=Path,
                    help="run data (default: <campaign>/notes/spell_pass_batch)")
    ap.add_argument("--scratch", required=True, type=Path,
                    help="where the trial applies are written")
    args = ap.parse_args()

    global CAMP, BATCH, GLOSSARY, STATE
    CAMP = args.campaign_dir.expanduser().resolve()
    BATCH = (args.batch_dir or CAMP / "notes" / "spell_pass_batch").expanduser().resolve()
    GLOSSARY = CAMP / "notes" / "vtt_transcription_corrections.md"
    STATE = CAMP / "notes" / ".vtt_spell_pass_state.json"
    for need in (BATCH / "manifest.json", GLOSSARY):
        if not need.is_file():
            print(f"error: missing {need}", file=sys.stderr)
            return 2
    args.scratch.mkdir(parents=True, exist_ok=True)

    manifest = json.loads((BATCH / "manifest.json").read_text())
    rs = rows()
    ch = chains(rs)
    print(f"glossary: {len(rs)} wrong->right pairs")
    print(f"chained rules: {len(ch)}")
    for i, w, c, j, c2 in ch:
        print(f"  L{i}: {w!r} -> {c!r}  but L{j}: {c!r} -> {c2!r}  => terminal {c2!r}")

    findings = []
    for d, m in manifest["dirs"].items():
        src = CAMP / m["target_file"]
        out = args.scratch / f"{d}{src.suffix}"
        apply_to(src, out)
        before, after = src.read_text(encoding="utf-8"), out.read_text(encoding="utf-8")

        # doubling introduced by THIS apply, not already present in the source
        db_before = {t.group(0).lower() for t in DOUBLE_RE.finditer(before)}
        new_db = [t.group(0) for t in DOUBLE_RE.finditer(after)
                  if t.group(0).lower() not in db_before]

        # idempotency: applying again must change nothing
        out2 = args.scratch / f"{d}.twice{src.suffix}"
        apply_to(out, out2)
        idem = out2.read_text(encoding="utf-8") == after

        changed = sum(1 for a, b in zip(before.splitlines(), after.splitlines()) if a != b)
        findings.append({"dir": d, "lines_changed": changed,
                         "new_doubling": new_db, "idempotent": idem,
                         "out": str(out)})

    print(f"\n{'dir':<24} {'lines':>6}  {'idem':>5}  doubling introduced")
    for f in findings:
        db = ", ".join(sorted(set(f["new_doubling"]))[:4]) or "-"
        print(f"  {f['dir']:<22} {f['lines_changed']:>6}  "
              f"{'ok' if f['idempotent'] else 'FAIL':>5}  {db}")

    bad_idem = [f["dir"] for f in findings if not f["idempotent"]]
    all_db = sorted({d for f in findings for d in f["new_doubling"]})
    print(f"\ntotal lines changed: {sum(f['lines_changed'] for f in findings)}")
    print(f"non-idempotent files: {bad_idem or 'none'}")
    print(f"distinct doubling artefacts introduced: {all_db or 'none'}")

    (BATCH / "stage_c_dryrun.json").write_text(
        json.dumps({"chains": [list(c) for c in ch], "findings": findings}, indent=2) + "\n",
        encoding="utf-8")

    if args.dry_run:
        print("\nDRY RUN — nothing written to summaries/.")
        return 1 if (bad_idem or all_db) else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
