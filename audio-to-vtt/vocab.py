#!/usr/bin/env python3
"""Gather campaign proper-noun vocabulary for Whisper hotword biasing.

Ranked, deduped (case-insensitive) list, highest-value first:

  1. notes/vtt_transcription_corrections.md canonicals — proven ASR
     failure points for this exact campaign. Parsed by reusing
     find_unknowns.parse_glossary from the vtt-spell-pass skill (never
     re-derived); only the canonical (right-column) forms are used —
     the wrong-forms must never be fed in, or the model gets biased back
     toward the mistakes this tool exists to fix.
  2. docs/entity_registry.yaml name+aliases — the authoritative structured
     source. If missing, falls back to flattening docs/entity_inventory.md
     (its rendered markdown companion) using the same bold-span-extraction
     steps vtt-spell-pass/SKILL.md already documents for that exact file.
  3. docs/background/*-inventory.txt — flat pre-session module vocabulary
     (lowest priority, broadest).

Token-budget trimming happens on the Spark side (spark/transcribe_remote.py),
against the loaded model's own tokenizer — this module only builds the
full, ranked, uncapped candidate list; that is what ships inside the run
manifest.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

_SKILL_DIR = Path(__file__).resolve().parents[1] / "dotfiles" / "claude" / "skills" / "vtt-spell-pass"
sys.path.insert(0, str(_SKILL_DIR))
from find_unknowns import parse_glossary  # noqa: E402


def _dedupe_preserve_order(names: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        n = n.strip()
        key = n.lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(n)
    return out


def glossary_canonicals(glossary_path: Path) -> list[str]:
    if not glossary_path.exists():
        return []
    _replacements, canonicals = parse_glossary(glossary_path)
    return list(canonicals)


def registry_names(registry_path: Path) -> list[str]:
    if not registry_path.exists():
        return []
    data = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    names: list[str] = []
    for entity in data.get("entities", []):
        name = entity.get("name")
        if name:
            names.append(name)
        for alias in entity.get("aliases", []) or []:
            if alias:
                names.append(alias)
    return names


_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def entity_inventory_names(inventory_md_path: Path) -> list[str]:
    """Fallback for campaigns without docs/entity_registry.yaml: flatten
    docs/entity_inventory.md's bold-bullet spans, mirroring the exact steps
    vtt-spell-pass/SKILL.md documents for this file: pull every **bold**
    span from each "- " bullet line, split multi-alias spans on " / ",
    unescape \\' -> ', and let the caller's dedupe handle case-insensitive
    collisions."""
    if not inventory_md_path.exists():
        return []
    names: list[str] = []
    for line in inventory_md_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        for span in _BOLD_RE.findall(stripped):
            for part in span.split(" / "):
                part = part.replace("\\'", "'").strip()
                if part:
                    names.append(part)
    return names


def module_inventory_names(background_dir: Path) -> list[str]:
    if not background_dir.exists():
        return []
    names: list[str] = []
    for txt_path in sorted(background_dir.glob("*-inventory.txt")):
        for line in txt_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                names.append(line)
    return names


def gather_vocabulary(campaign_root: Path) -> list[str]:
    """Ranked, deduped candidate vocabulary list for a campaign. Uncapped —
    the caller (spark/transcribe_remote.py) trims to the loaded model's
    real token budget."""
    campaign_root = Path(campaign_root)
    ranked: list[str] = []

    ranked.extend(glossary_canonicals(campaign_root / "notes" / "vtt_transcription_corrections.md"))

    registry_path = campaign_root / "docs" / "entity_registry.yaml"
    if registry_path.exists():
        ranked.extend(registry_names(registry_path))
    else:
        ranked.extend(entity_inventory_names(campaign_root / "docs" / "entity_inventory.md"))

    ranked.extend(module_inventory_names(campaign_root / "docs" / "background"))

    return _dedupe_preserve_order(ranked)


def find_campaign_root(start: Path) -> Path | None:
    """Walk up from `start` looking for a campaign root (a dir containing
    docs/entity_registry.yaml or notes/vtt_transcription_corrections.md),
    mirroring vtt-spell-pass/SKILL.md's own campaign-root detection."""
    for candidate in [start, *start.parents]:
        if (candidate / "docs" / "entity_registry.yaml").exists() or \
           (candidate / "notes" / "vtt_transcription_corrections.md").exists():
            return candidate
    return None


if __name__ == "__main__":
    import json
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    print(json.dumps(gather_vocabulary(root), indent=2))
