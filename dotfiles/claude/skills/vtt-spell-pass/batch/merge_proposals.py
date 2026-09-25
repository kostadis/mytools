#!/usr/bin/env python3
"""Stage B: merge a wave's proposals into a GM question queue.

Deterministic. No LLM judgment happens here -- the point of this file is that
the merge rules are code, so the same evidence always produces the same
question, and nothing gets silently reconciled.

Two things it fixes that no single agent can:

* **Corpus-wide lowercase gate.** apply_replacements.py matches \\bwrong\\b with
  re.IGNORECASE, so a wrong-form that occurs lowercase in ANY transcript will
  corrupt ordinary prose there. One agent only sees its own chapter.
  lint_glossary.py cannot substitute: lint_glossary.py:181 exempts all-lowercase
  wrong-forms from its corpus check entirely, which is exactly the riskiest class.
* **Cross-chapter conflicts.** The same wrong-form proposed for two different
  canonicals is decided by row order if it silently merges -- so it escalates.

Consent granularity: the unit is the (wrong_form -> canonical) PAIR. Questions are
grouped by canonical for batching, but every member carries its own count and
sibling verdict so the GM can accept some and reject others. Collapsing a group
into one yes/no would approve hallucinated members invisibly.

Usage:
    merge_proposals.py --campaign-dir <campaign> --wave 1 [--batch-dir DIR]

Reads <batch-dir>/manifest.json, each wave dir's proposals.json and
<batch-dir>/corpus_all.txt; writes <batch-dir>/wave<N>_queue.json.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path



def lowercase_in_corpus(token: str, corpus: str) -> bool:
    """Does this wrong-form ever appear all-lowercase in any transcript?

    Case-SENSITIVE search of the original text for the lowercased token.
    (Lowercasing the haystack instead was a real bug here; it matches in any
    case and fired for 147/153 members.)
    """
    return bool(re.search(rf"\b{re.escape(token.lower())}\b", corpus))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--campaign-dir", required=True, type=Path)
    ap.add_argument("--batch-dir", type=Path,
                    help="run data (default: <campaign>/notes/spell_pass_batch)")
    ap.add_argument("--wave", type=int, required=True)
    args = ap.parse_args()

    CAMP = args.campaign_dir.expanduser().resolve()
    BATCH = (args.batch_dir or CAMP / "notes" / "spell_pass_batch").expanduser().resolve()
    CORPUS = BATCH / "corpus_all.txt"
    for need in (BATCH / "manifest.json", CORPUS):
        if not need.is_file():
            print(f"error: missing {need}", file=sys.stderr)
            return 2

    manifest = json.loads((BATCH / "manifest.json").read_text())
    dirs = [d for d, m in manifest["dirs"].items() if m["wave"] == args.wave]
    corpus = CORPUS.read_text(encoding="utf-8", errors="replace")

    loaded, missing = {}, []
    for d in dirs:
        p = BATCH / d / "proposals.json"
        if p.exists():
            loaded[d] = json.loads(p.read_text())
        else:
            missing.append(d)
    if missing:
        print(f"MISSING proposals.json for: {', '.join(missing)}")
        return 1

    # --- comparability guard ------------------------------------------------
    counts = {d: p["known_names_count"] for d, p in loaded.items()}
    glos = {d: p["glossary_sha256_at_scan"] for d, p in loaded.items()}
    if len(set(counts.values())) != 1:
        print(f"REJECT: known_names_count diverged across agents: {counts}")
        return 1
    if len(set(glos.values())) != 1:
        print(f"REJECT: agents scanned against different glossary versions: {glos}")
        return 1
    print(f"comparability OK — known_names_count={list(counts.values())[0]}, "
          f"one glossary version across {len(loaded)} dirs\n")

    # --- collect every surfaced member --------------------------------------
    # key: (token.lower(), canonical) -> occurrences across chapters
    pairs: dict[tuple, list] = defaultdict(list)
    blocked, notes, dismissed_n, residual_n = [], [], 0, 0
    for d, p in loaded.items():
        dismissed_n += len(p.get("auto_dismissed", []))
        residual_n += len(p.get("false_residuals_suppressed", []))
        for b in p.get("agent_blocked_on", []):
            blocked.append((d, b))
        for n in p.get("agent_notes", []):
            notes.append((d, n))
        for c in p["clusters"]:
            for m in c["members"]:
                rec = m.get("recommendation")
                if rec in ("ignore", None):
                    continue
                # A `different_canonical` member is one the agent REJECTED the
                # cluster's canonical for. Falling back to the cluster canonical
                # would present the GM with exactly the mapping the agent
                # rejected. Agents vary in whether they name the alternative in a
                # field or only in prose, so if it isn't in a field, carry None
                # and let the escalation show the rationale.
                canon = m.get("proposed_canonical") or m.get("suggested_canonical")
                if rec != "different_canonical":
                    canon = canon or c.get("proposed_canonical")
                pairs[(m["token"].lower(), canon)].append({
                    "dir": d, "token": m["token"], "count": m["count"],
                    "verbatim": m.get("verbatim", ""),
                    "kind": m.get("kind"), "rec": rec,
                    "rationale": m.get("rationale", ""),
                    "requires_gm": bool(m.get("requires_gm")),
                    # NOTE: this is the AUTOMATED best-match from sibling_context.py,
                    # which misaligns often enough to matter. Where the agent re-checked
                    # the sibling by hand its rationale is authoritative, and the two can
                    # disagree: 'Delfino' shows automated "Okay, Doki." while the correctly
                    # aligned sibling cue reads "Okay, Valphine." Never show this field to
                    # the GM without the rationale beside it.
                    "sibling_auto": (m.get("sibling_evidence") or {}).get("sibling_verbatim"),
                    "sibling_alignment": ("agent_corrected"
                                          if re.search(r"manual|mis-align|misalign|re-check",
                                                       m.get("rationale") or "", re.I)
                                          else "automated"),
                })

    # --- conflict detection: one wrong-form, two canonicals ------------------
    by_token = defaultdict(set)
    for (tok, canon) in pairs:
        by_token[tok].add(canon)
    conflicts = {t: c for t, c in by_token.items() if len(c) > 1}

    # --- classify each pair --------------------------------------------------
    queue = []
    for (tok, canon), occ in sorted(pairs.items(), key=lambda kv: -sum(o["count"] for o in kv[1])):
        kinds = {o["kind"] for o in occ}
        total = sum(o["count"] for o in occ)
        low = lowercase_in_corpus(tok, corpus)
        recs = {o["rec"] for o in occ}
        # The agent's RECOMMENDATION is authoritative; sibling `kind` is only
        # supporting evidence. Checking kind first let two wrong proposals
        # through: 'Emerald Gauntlet' (agent: no_rule, "live speaker slip, do
        # not add a rule") was proposed as Miraal because its kind was
        # campaign_correct_name, and 'Lila' (agent: different_canonical, "NOT
        # Lyra - this is Leilon") surfaced as a Lyra confirmation. An agent that
        # declined to propose must never be overridden into proposing.
        if "no_rule" in recs:
            rule, action = "agent_declined", "leave_alone"
        elif "different_canonical" in recs:
            rule, action = "agent_proposed_alternative", "escalate"
        elif recs == {"new_canon"}:
            # Not a correction at all: an already-correct name missing from the
            # known set. Belongs in vtt_known_additions.md, never the glossary.
            rule, action = "new_canon", "add_to_known_set"
        elif canon is None and recs <= {"no_rule"} and not any(o["requires_gm"] for o in occ):
            rule, action = "no_rule", "leave_alone"
        elif canon is None:
            rule, action = "canonical_unnamed", "escalate"
        elif tok in conflicts:
            rule, action = "conflict", "escalate_blocking"
        elif "different_name" in kinds:
            rule, action = "different_name", "escalate"
        elif low:
            rule, action = "lowercase_in_corpus", "targeted_edit_only"
        elif any(o["requires_gm"] for o in occ):
            rule, action = "agent_escalated", "escalate"
        elif "ordinary_words" in kinds:
            rule, action = "ordinary_words_present", "split_per_chapter"
        elif "campaign_correct_name" in kinds:
            rule, action = "sibling_confirms", "propose"
        else:
            rule, action = "unadjudicated", "propose_low_confidence"
        queue.append({
            "token": occ[0]["token"], "canonical": canon,
            "total_count": total, "chapters": len(occ),
            "rule": rule, "action": action,
            "lowercase_in_corpus": low,
            "conflicting_canonicals": sorted(str(c) for c in conflicts.get(tok, [])) or None,
            "occurrences": occ,
        })

    out = {"wave": args.wave, "dirs": dirs,
           "auto_dismissed_total": dismissed_n,
           "false_residuals_total": residual_n,
           "pairs_total": len(queue),
           "blocked": [{"dir": d, **b} for d, b in blocked],
           "agent_notes": [{"dir": d, "note": n} for d, n in notes],
           "queue": queue}
    (BATCH / f"wave{args.wave}_queue.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8")

    # --- report --------------------------------------------------------------
    from collections import Counter
    print(f"{len(loaded)} dirs · {dismissed_n} auto-dismissed · "
          f"{residual_n} false residuals · {len(queue)} decision pairs\n")
    print("by merge rule:")
    for r, n in Counter(q["rule"] for q in queue).most_common():
        print(f"  {r:<26} {n:>3}")
    if conflicts:
        print(f"\nCONFLICTS ({len(conflicts)}) — same wrong-form, different canonicals:")
        for t, c in conflicts.items():
            print(f"  {t!r} -> {sorted(str(x) for x in c)}")
    if blocked:
        print(f"\nAGENT-BLOCKED ({len(blocked)}):")
        for d, b in blocked:
            print(f"  [{d}] {b.get('topic', str(b))[:100]}")
    print(f"\n-> {BATCH / f'wave{args.wave}_queue.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
