#!/usr/bin/env python3
"""
flatten_5etools.py — Flatten a 5etools-style adventure JSON into a linear,
section-breadcrumbed text corpus for downstream monster-naming scans.

WHY: 5etools adventures (e.g. homebrew ToEE T14, published modules on
5etools.org) encode prose in nested `entries` / `inset` / `list` / `table` /
`section` nodes. Monsters in homebrew notes live in PROSE — there are no
statblock objects to grep. This flattener walks `adventureData[0].data`
recursively, tracks a header breadcrumb stack, and emits one line per text
leaf prefixed with `[Section > Subsection]` so a scan agent can cite location.

USAGE:
    python flatten_5etools.py <module.json> [--out flattened.txt]
    # defaults --out to <module>_flattened.txt alongside the source

Then split the flattened file by chapter (see SKILL.md Phase 1) and feed each
chunk to a scan subagent.
"""
import json
import sys
import argparse


def flatten(nodes, out):
    breadcrumb = []

    def current():
        return " > ".join(breadcrumb) if breadcrumb else "(root)"

    def walk(node, depth=0):
        if isinstance(node, dict):
            pushed = False
            for key in ("name", "header"):
                v = node.get(key)
                if v and not pushed:
                    breadcrumb.append(str(v))
                    pushed = True
                    out.append(f"\n{'#' * (min(depth, 6) + 1)} {v}\n")
            for k, v in node.items():
                walk(v, depth + 1)
            if pushed:
                breadcrumb.pop()
        elif isinstance(node, list):
            for v in node:
                walk(v, depth)
        elif isinstance(node, str):
            t = node.strip()
            if t:
                out.append(f"[{current()}] {t}")

    walk(nodes)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json_path")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    with open(args.json_path) as f:
        data = json.load(f)

    # 5etools layout: data["adventureData"][0]["data"] is the content tree
    nodes = data["adventureData"][0]["data"]
    out = []
    flatten(nodes, out)
    text = "\n".join(out)

    target = args.out or (args.json_path.rsplit(".", 1)[0] + "_flattened.txt")
    with open(target, "w") as f:
        f.write(text)
    print(f"Wrote {len(text)} chars, {text.count(chr(10)) + 1} lines to {target}")


if __name__ == "__main__":
    main()
