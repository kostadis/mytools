#!/usr/bin/env python3
"""Validate canonical shared skills and intentional runtime adapters."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def files_below(root: Path):
    for path in root.rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts or ".pytest_cache" in path.parts:
            continue
        yield path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dotfiles", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()

    root = args.dotfiles.resolve()
    manifest = json.loads((root / "skill-layout.json").read_text(encoding="utf-8"))
    claude = root / "claude" / "skills"
    codex = root / "codex" / "skills"
    shared = root / "shared" / "skills"
    errors: list[str] = []

    declared = set(manifest["shared_skills"])
    present = {path.name for path in shared.iterdir() if path.is_dir()}
    for name in sorted(declared - present):
        errors.append(f"MISSING shared skill directory: {name}")
    for name in sorted(present - declared):
        errors.append(f"UNDECLARED shared skill directory: {name}")

    shared_files = 0
    for skill in sorted(declared & present):
        for canonical in files_below(shared / skill):
            shared_files += 1
            rel = canonical.relative_to(shared)
            for side_name, side_root in (("claude", claude), ("codex", codex)):
                runtime = side_root / rel
                if not runtime.is_symlink():
                    state = "missing" if not runtime.exists() else "copied, not linked"
                    errors.append(f"{side_name.upper()} {state}: {rel}")
                    continue
                try:
                    target = runtime.resolve(strict=True)
                except FileNotFoundError:
                    errors.append(f"{side_name.upper()} broken link: {rel}")
                    continue
                if target != canonical.resolve():
                    errors.append(f"{side_name.upper()} wrong link: {rel} -> {target}")

    adapters = manifest["intentional_adapters"]
    paired = set(adapters["paired"])
    for rel_text in sorted(paired):
        rel = Path(rel_text)
        if not (claude / rel).exists():
            errors.append(f"MISSING Claude adapter: {rel}")
        if not (codex / rel).exists():
            errors.append(f"MISSING Codex adapter: {rel}")

    for side_name, own, other, key in (
        ("Claude", claude, codex, "claude_only"),
        ("Codex", codex, claude, "codex_only"),
    ):
        for rel_text in adapters[key]:
            rel = Path(rel_text)
            if not (own / rel).exists():
                errors.append(f"MISSING {side_name}-only adapter: {rel}")
            if (other / rel).exists():
                errors.append(f"{side_name}-only adapter also exists on other side: {rel}")

    # A new byte-identical regular file in both runtime trees recreates two
    # authorities. Shared implementations must enter the canonical tree.
    for left in files_below(claude):
        rel = left.relative_to(claude)
        right = codex / rel
        if rel.as_posix() in paired or left.is_symlink() or right.is_symlink():
            continue
        if right.is_file() and left.read_bytes() == right.read_bytes():
            errors.append(f"DUPLICATED neutral file outside shared tree: {rel}")

    if errors:
        print("skill layout is invalid:", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 1

    print(f"skill layout valid: {shared_files} canonical files across {len(declared)} shared skills")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
