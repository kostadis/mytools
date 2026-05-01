#!/usr/bin/env python3
"""Batch-mode sidecar merge: fold every `*.new_notes.NNN.md` into its canonical
dossier in one Anthropic Message Batch (50% discount).

Why sidecars exist: `planning.py --build-dossiers` writes per-source-extract
sidecars when a canonical dossier already exists, to avoid clobbering curated
content. They accumulate over many runs and need to be folded back in.

Usage:
    python sidecar_merge_batch.py /path/to/docs/npcs/
    python sidecar_merge_batch.py /path/to/docs/npcs/ --dry-run
    python sidecar_merge_batch.py /path/to/docs/npcs/ --resume

State files written next to the dossier directory:
    .sidecar_merge_state.json  — completed/skipped per NPC (resumable)
    .sidecar_merge_batch.json  — last batch ID for --resume

Successfully merged sidecars are moved to <npc_dir>/merged_sidecars/ rather
than deleted, so a botched merge can be reverted by hand.
"""
import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, "/home/kroussos/src/CampaignGenerator")
from campaignlib import make_client  # noqa: E402

SIDECAR_RE = re.compile(r"^(.+)\.new_notes\.(\d+)\.md$")
FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n+(.*)\Z", re.DOTALL)

SYSTEM_PROMPT = "You are a careful editor folding new session notes into an existing NPC dossier."

MERGE_PROMPT = """The CANONICAL DOSSIER below describes an NPC. The N NEW NOTES that follow contain additional facts extracted from later session sources (one note per source extract). Produce a single updated dossier body that absorbs every unique fact from the new notes into the canonical structure.

Section structure to keep: `## Identity`, `## Personality & Motivations`, `## History with the Party`, `## Current Status`, `## Relationships`, `## Arc Score Events`. Section rules:

- **Identity**: keep the canonical's framing; end with `*Also known as: {aliases}.*`.
- **Personality & Motivations**: union of bullets, deduplicate semantically. New traits revealed in the notes go in.
- **History with the Party**: chronological. If a new note describes the same event as an existing entry but with more detail, REPLACE the existing entry with the richer one. If it's a brand-new event, slot it in by date/order.
- **Current Status**: most recent state wins. If the canonical and a new note contradict on current location/status without clear ordering, flag with `[CONTRADICTION: canonical says X; new note from extract NNN says Y]`.
- **Relationships**: union; prefer specific phrasing over generic. Add new NPCs mentioned.
- **Arc Score Events**: union; preserve every recorded event.

Do NOT drop any factual claim from either source. If something appears only in a sidecar, it goes in. If something appears in the canonical, it stays unless explicitly superseded.

Output ONLY the dossier body (no frontmatter, no preamble).

---

## CANONICAL DOSSIER ({canonical_filename})

{canonical_body}

---

{notes_blob}
"""


def parse_dossier(path: Path):
    text = path.read_text()
    m = FRONTMATTER_RE.match(text)
    if not m:
        return path.stem, [], [], text
    fm, body = m.group(1), m.group(2)
    name_m = re.search(r'^name:\s*(.+)$', fm, re.MULTILINE)
    name = name_m.group(1).strip() if name_m else path.stem
    aliases = []
    in_aliases = False
    for line in fm.splitlines():
        if re.match(r'^aliases:\s*\[\s*\]\s*$', line):
            continue
        if re.match(r'^aliases:\s*$', line):
            in_aliases = True
            continue
        if in_aliases:
            am = re.match(r'^\s*-\s*(.+)$', line)
            if am:
                aliases.append(am.group(1).strip())
            elif line and not line.startswith(' '):
                in_aliases = False
    source_extracts: list[int] = []
    se_m = re.search(r'^source_extracts:\s*\[([^\]]*)\]\s*$', fm, re.MULTILINE)
    if se_m:
        source_extracts = [int(x) for x in re.findall(r'\d+', se_m.group(1))]
    return name, aliases, source_extracts, body


def write_dossier(path: Path, name: str, aliases: list[str],
                  source_extracts: list[int], body: str):
    if aliases:
        alias_yaml = "aliases:\n" + "\n".join(f"  - {a}" for a in aliases) + "\n"
    else:
        alias_yaml = "aliases: []\n"
    nums = sorted(set(int(n) for n in source_extracts))
    extracts_yaml = "source_extracts: [" + ", ".join(str(n) for n in nums) + "]\n"
    fm = f"---\nname: {name}\n{alias_yaml}{extracts_yaml}---\n\n"
    path.write_text(fm + body.lstrip())


def update_identity_aka(body: str, aliases: list[str]) -> str:
    if not aliases:
        return body
    aka = f"*Also known as: {', '.join(aliases)}.*"
    id_pattern = re.compile(r"(^##\s+Identity\s*$)(.*?)(?=^##\s|\Z)", re.MULTILINE | re.DOTALL | re.IGNORECASE)
    m = id_pattern.search(body)
    if not m:
        return body
    section = m.group(2)
    section_stripped = re.sub(r"\n+\*Also known as:[^\n]*\n*", "\n", section).rstrip()
    new_section = section_stripped + "\n\n" + aka + "\n\n"
    return body[:m.start(2)] + new_section + body[m.end():]


def collect_sidecars(npc_dir: Path) -> dict[str, list[Path]]:
    by_canonical: dict[str, list[Path]] = {}
    for p in npc_dir.glob("*.new_notes.*.md"):
        m = SIDECAR_RE.match(p.name)
        if not m:
            continue
        stem = m.group(1)
        by_canonical.setdefault(stem, []).append(p)
    for stem in by_canonical:
        by_canonical[stem].sort(key=lambda p: int(SIDECAR_RE.match(p.name).group(2)))
    return by_canonical


def load_state(state_file: Path):
    if state_file.exists():
        return json.loads(state_file.read_text())
    return {"started_at": datetime.now(timezone.utc).isoformat(), "completed": [], "skipped": []}


def save_state(state_file: Path, state):
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    state_file.write_text(json.dumps(state, indent=2) + "\n")


def build_prompt(canonical_path: Path, sidecar_paths: list[Path]) -> tuple[str, list[str]]:
    name, aliases, _source_extracts, body = parse_dossier(canonical_path)
    notes_blob = ""
    for sp in sidecar_paths:
        notes_blob += f"## NEW NOTES — {sp.name}\n\n{sp.read_text()}\n\n---\n\n"
    prompt = MERGE_PROMPT.format(
        aliases=", ".join(aliases) if aliases else "(none)",
        canonical_filename=canonical_path.name,
        canonical_body=body,
        notes_blob=notes_blob,
    )
    return prompt, aliases


def submit_batch(client, npc_dir: Path, batch_info_file: Path,
                 targets: dict[str, list[Path]], model: str) -> str:
    requests = []
    for stem in sorted(targets):
        canonical_path = npc_dir / f"{stem}.md"
        if not canonical_path.exists():
            print(f"⚠️  Canonical missing for {stem}.md — skipping {len(targets[stem])} orphan sidecars")
            continue
        prompt, _ = build_prompt(canonical_path, targets[stem])
        requests.append({
            "custom_id": stem,
            "params": {
                "model": model,
                "max_tokens": 16000,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": prompt}],
            },
        })
    print(f"Submitting batch with {len(requests)} requests…")
    batch = client.messages.batches.create(requests=requests)
    print(f"Batch submitted: id={batch.id}  status={batch.processing_status}")
    batch_info_file.write_text(json.dumps({
        "batch_id": batch.id,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "request_count": len(requests),
        "stems": [r["custom_id"] for r in requests],
        "npc_dir": str(npc_dir),
    }, indent=2) + "\n")
    return batch.id


def poll_batch(client, batch_id: str, poll_interval: int = 30):
    print(f"\nPolling batch {batch_id} every {poll_interval}s…")
    while True:
        batch = client.messages.batches.retrieve(batch_id)
        counts = batch.request_counts
        print(f"  [{datetime.now().strftime('%H:%M:%S')}] status={batch.processing_status}  "
              f"processing={counts.processing} succeeded={counts.succeeded} "
              f"errored={counts.errored} canceled={counts.canceled} expired={counts.expired}")
        if batch.processing_status == "ended":
            return batch
        time.sleep(poll_interval)


def process_results(client, batch_id: str, npc_dir: Path, archive_dir: Path,
                    state_file: Path, targets: dict[str, list[Path]],
                    state: dict, dry_run: bool):
    print(f"\nFetching results for batch {batch_id}…")
    archive_dir.mkdir(exist_ok=True)
    n_ok = n_err = n_contra = 0
    for result in client.messages.batches.results(batch_id):
        stem = result.custom_id
        rtype = result.result.type
        if rtype != "succeeded":
            print(f"❌  {stem}: {rtype}")
            err = getattr(result.result, "error", None)
            state["skipped"].append({"stem": stem, "reason": f"batch result {rtype}: {err}"})
            n_err += 1
            continue

        message = result.result.message
        merged = "".join(b.text for b in message.content if b.type == "text")
        canonical_path = npc_dir / f"{stem}.md"
        _, aliases, existing_source_extracts, _ = parse_dossier(canonical_path)
        had_contra = "[CONTRADICTION" in merged
        if had_contra:
            print(f"⚠️  {stem}: contradiction marker present")
            n_contra += 1
        final_body = update_identity_aka(merged, aliases)

        if dry_run:
            print(f"  [dry-run] {stem}: {len(merged)} chars merged body")
            n_ok += 1
            continue

        name, aliases_kept, _, _ = parse_dossier(canonical_path)
        # Extend source_extracts with the numbers of sidecars being folded in,
        # so future --build-dossiers runs skip re-writing the same sidecars.
        folded_nums: list[int] = []
        for sp in targets.get(stem, []):
            m = SIDECAR_RE.match(sp.name)
            if m:
                folded_nums.append(int(m.group(2)))
        new_source_extracts = sorted(set(existing_source_extracts) | set(folded_nums))
        write_dossier(canonical_path, name, aliases_kept, new_source_extracts, final_body)
        for sp in targets.get(stem, []):
            if sp.exists():
                shutil.move(str(sp), str(archive_dir / sp.name))
        state["completed"].append({
            "canonical": canonical_path.name,
            "sidecars": [s.name for s in targets.get(stem, [])],
            "out_chars": len(merged),
            "had_contradiction": had_contra,
            "via": "batch",
        })
        save_state(state_file, state)
        n_ok += 1
        print(f"  ✓ {stem}  ({len(merged)} chars, {len(targets.get(stem, []))} sidecars archived)")

    print(f"\n========== BATCH RESULTS ==========")
    print(f"Succeeded: {n_ok}  (with contradictions: {n_contra})")
    print(f"Errored:   {n_err}")
    print(f"State:     {state_file}")
    print(f"Archive:   {archive_dir}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("npc_dir", type=Path, help="Path to docs/npcs/ directory")
    ap.add_argument("--model", default="claude-sonnet-4-5")
    ap.add_argument("--dry-run", action="store_true", help="don't write dossiers / archive sidecars")
    ap.add_argument("--resume", action="store_true",
                    help="don't submit new batch; poll + process the batch_id in .sidecar_merge_batch.json")
    ap.add_argument("--poll-interval", type=int, default=30)
    args = ap.parse_args()

    npc_dir = args.npc_dir.resolve()
    if not npc_dir.is_dir():
        sys.exit(f"Not a directory: {npc_dir}")
    archive_dir = npc_dir / "merged_sidecars"
    state_file = npc_dir / ".sidecar_merge_state.json"
    batch_info_file = npc_dir / ".sidecar_merge_batch.json"

    client = make_client()
    state = load_state(state_file)
    completed_stems = {c["canonical"][:-3] for c in state["completed"]}
    by_canonical = collect_sidecars(npc_dir)
    targets = {s: ps for s, ps in by_canonical.items() if s not in completed_stems}

    if args.resume:
        if not batch_info_file.exists():
            sys.exit(f"No {batch_info_file.name} — nothing to resume")
        info = json.loads(batch_info_file.read_text())
        batch_id = info["batch_id"]
        print(f"Resuming batch {batch_id} (submitted {info['submitted_at']}, {info['request_count']} requests)")
    else:
        if not targets:
            sys.exit("Nothing to do — all NPCs already merged.")
        print(f"Pending: {len(targets)} canonicals, "
              f"{sum(len(v) for v in targets.values())} sidecars total")
        if completed_stems:
            print(f"Skipping {len(completed_stems)} already-completed.")
        batch_id = submit_batch(client, npc_dir, batch_info_file, targets, args.model)

    batch = poll_batch(client, batch_id, args.poll_interval)
    if batch.processing_status != "ended":
        sys.exit(f"Batch ended in unexpected state: {batch.processing_status}")

    process_results(client, batch_id, npc_dir, archive_dir, state_file, targets, state, args.dry_run)


if __name__ == "__main__":
    main()
