#!/usr/bin/env python3
"""Prepare contextual VTT decisions and render them without rewriting source text.

This helper performs no identity inference. Fill the decisions using SKILL.md.
It requires Python 3.10+ and only the standard library.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re


STAMP = r"(?:\d{2,}:)?[0-5]\d:[0-5]\d\.\d{3}"
TIMING = re.compile(rf"^({STAMP})[ \t]+-->[ \t]+({STAMP})(?:[ \t]+.*)?$")
RESERVED = {"UNKNOWN", "MIXED"}
CONFIDENCES = {"high", "medium", "low", "unresolved"}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_record(path):
    path = Path(path).resolve(strict=True)
    return {"path": str(path), "sha256": sha256(path)}


def seconds(stamp):
    parts = stamp.split(":")
    return sum(float(part) * 60 ** i for i, part in enumerate(reversed(parts)))


def parse_vtt(raw):
    # Split only VTT line endings; do not normalize CRLF, BOM, or final newline.
    lines = re.findall(r"[^\r\n]*(?:\r\n|\r|\n|$)", raw)
    if lines and lines[-1] == "":
        lines.pop()
    if not lines or not re.fullmatch(r"WEBVTT(?:[ \t].*)?", lines[0].lstrip("\ufeff").rstrip("\r\n")):
        raise ValueError("Expected a UTF-8 WebVTT header")
    blanks = [i for i, line in enumerate(lines) if not line.strip(" \t\r\n")]
    if not blanks:
        raise ValueError("Missing blank line after WebVTT header")
    header_end = blanks[0] + 1
    cues = []
    pos = header_end
    while pos < len(lines):
        if not lines[pos].strip(" \t\r\n"):
            pos += 1
            continue
        end = pos
        while end < len(lines) and lines[end].strip(" \t\r\n"):
            end += 1
        first = lines[pos].rstrip("\r\n")
        if first in {"STYLE", "REGION", "NOTE"} or first.startswith(("NOTE ", "NOTE\t")):
            pos = end
            continue
        timing_line = pos if TIMING.fullmatch(first) else pos + 1
        match = TIMING.fullmatch(lines[timing_line].rstrip("\r\n")) if timing_line < end else None
        if not match or timing_line + 1 >= end:
            raise ValueError(f"Malformed or empty cue block at line {pos + 1}")
        if seconds(match[2]) <= seconds(match[1]):
            raise ValueError(f"Non-positive cue interval at line {timing_line + 1}")
        payload = timing_line + 1
        cues.append({
            "cue_index": len(cues) + 1,
            "cue_id": first if timing_line != pos else None,
            "timing": lines[timing_line].rstrip("\r\n"),
            "text": "\n".join(line.rstrip("\r\n") for line in lines[payload:end]),
            "source_line": payload + 1,
        })
        pos = end
    if not cues:
        raise ValueError("No speech cues found")
    return lines, header_end, cues


def read_vtt(path):
    raw = Path(path).read_bytes().decode("utf-8")
    lines, header_end, cues = parse_vtt(raw)
    return raw, lines, header_end, cues


def check_people(people):
    if not isinstance(people, list) or not people or any(not isinstance(p, str) for p in people):
        raise ValueError("Provide a list of human speaker names")
    if len(set(people)) != len(people):
        raise ValueError("Provide distinct human speaker names")
    for person in people:
        if (not person.strip() or person != person.strip() or person in RESERVED
                or any(c in person for c in "\r\n:<>")):
            raise ValueError(f"Invalid human speaker name: {person!r}")


def check_speakerless(cues, people):
    for cue in cues:
        first = cue["text"].lstrip()
        if (re.search(r"<v(?:[ .>])", first) or
                any(first.startswith(person + ":") for person in [*people, *RESERVED])):
            raise ValueError(f"Cue {cue['cue_index']} already has a speaker label; use a speakerless source")


def write_new(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)


def encoded_json(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def prepare(args):
    check_people(args.speaker)
    source = source_record(args.source)
    raw, _, _, cues = read_vtt(source["path"])
    if hashlib.sha256(raw.encode("utf-8")).hexdigest() != source["sha256"]:
        raise ValueError("Source changed while reading")
    check_speakerless(cues, args.speaker)
    references = [source_record(p) for p in args.reference]
    fingerprints = [source["sha256"], *[r["sha256"] for r in references]]
    if len(set(fingerprints)) != len(fingerprints):
        raise ValueError("Source and selected references must be distinct; remove duplicate exports")
    for cue in cues:
        cue.update(speaker=None, confidence="unresolved", evidence_note="",
                   possible_mixed=False, gm_confirmed=False)
    record = {
        "schema_version": 1, "source": source, "reference_sources": references,
        "context_sources": [source_record(p) for p in args.context],
        "participants": args.speaker, "mode": "provisional", "authorization": "",
        "review_required": False, "method_notes": "", "cues": cues,
    }
    write_new(args.output, encoded_json(record))
    print(json.dumps({"decisions": str(Path(args.output).resolve()), "cues": len(cues)}))


def render(args):
    record = json.loads(Path(args.decisions).read_text(encoding="utf-8"))
    if record.get("schema_version") != 1:
        raise ValueError("Unsupported decisions schema")
    people = record["participants"]
    check_people(people)
    mode = record["mode"]
    if mode not in {"provisional", "best_guess"}:
        raise ValueError("mode must be provisional or best_guess")
    authorization = record.get("authorization", "")
    if mode == "best_guess" and (not isinstance(authorization, str) or not authorization.strip()):
        raise ValueError("Record the user's existing best-guess authorization")
    sources = [record["source"], *record.get("reference_sources", []), *record.get("context_sources", [])]
    outputs = [Path(args.output).absolute(), Path(args.record).absolute()]
    if len({p.resolve() for p in outputs}) != 2:
        raise ValueError("VTT output and record paths must differ")
    inputs = {Path(r["path"]).resolve() for r in sources} | {Path(args.decisions).resolve()}
    if any(p.exists() or p.is_symlink() or p.resolve() in inputs for p in outputs):
        raise ValueError("Use new output paths; inputs and earlier results cannot be overwritten")
    for source in sources:
        if sha256(source["path"]) != source["sha256"]:
            raise ValueError(f"Input changed since preparation: {source['path']}")
    raw, lines, header_end, cues = read_vtt(record["source"]["path"])
    if hashlib.sha256(raw.encode("utf-8")).hexdigest() != record["source"]["sha256"]:
        raise ValueError("Source changed while reading")
    check_speakerless(cues, people)
    decisions = record["cues"]
    if len(decisions) != len(cues):
        raise ValueError("Every source cue needs exactly one decision")
    result_lines = lines.copy()
    for cue, decision in zip(cues, decisions):
        for key in ("cue_index", "cue_id", "timing", "text", "source_line"):
            if decision.get(key) != cue[key]:
                raise ValueError(f"Cue {cue['cue_index']}: source field {key} changed or decisions out of order")
        speaker = decision.get("speaker")
        if not isinstance(speaker, str) or (speaker not in people and speaker not in RESERVED):
            raise ValueError(f"Cue {cue['cue_index']}: unknown human speaker {speaker!r}")
        if mode == "best_guess" and speaker in RESERVED:
            raise ValueError(f"Cue {cue['cue_index']}: best_guess requires a human name")
        confidence = decision.get("confidence")
        if confidence not in CONFIDENCES or (speaker in people and confidence == "unresolved"):
            raise ValueError(f"Cue {cue['cue_index']}: use qualitative confidence for the assignment")
        if not isinstance(decision.get("evidence_note"), str) or not decision["evidence_note"].strip():
            raise ValueError(f"Cue {cue['cue_index']}: missing evidence note")
        for key in ("possible_mixed", "gm_confirmed"):
            if not isinstance(decision.get(key), bool):
                raise ValueError(f"Cue {cue['cue_index']}: {key} must be a boolean")
        decision["accepted_for_use"] = mode == "best_guess" or decision["gm_confirmed"]
        index = cue["source_line"] - 1
        result_lines[index] = speaker + ": " + result_lines[index]
    status = "best_effort_text_attribution_accepted_for_use" if mode == "best_guess" else "provisional_text_inference"
    newline = re.search(r"\r\n|\r|\n", raw).group()
    note = newline.join([
        "NOTE", "Speaker labels inferred from text and conversation context; not acoustically verified.",
        "Labels identify human speakers, including any characters they voice.",
        "Best guesses accepted for use; cue identities remain estimates." if mode == "best_guess"
        else "Provisional attribution; cue confidence and evidence are in the companion record.",
        "Possible within-cue speaker changes are retained in the companion record.", "", "",
    ])
    output = "".join(result_lines[:header_end]) + note + "".join(result_lines[header_end:])
    offset = sum(len(line) for line in result_lines[:header_end])
    restored = output[:offset] + output[offset + len(note):]
    restored_lines, _, _ = parse_vtt(restored)
    for cue, decision in zip(cues, decisions):
        index = cue["source_line"] - 1
        prefix = decision["speaker"] + ": "
        if not restored_lines[index].startswith(prefix):
            raise ValueError("Inserted speaker prefix missing in round-trip check")
        restored_lines[index] = restored_lines[index][len(prefix):]
    if "".join(restored_lines).encode("utf-8") != raw.encode("utf-8"):
        raise ValueError("Exact source-byte recovery failed")
    output_bytes = output.encode("utf-8")
    _, _, output_cues = parse_vtt(output)
    if len(output_cues) != len(cues):
        raise ValueError("Rendered cue count changed")
    record.update(
        status=status, created_utc=datetime.now(timezone.utc).isoformat(),
        acoustic_validation=None, target_accuracy=None,
        output=str(outputs[0]), output_sha256=hashlib.sha256(output_bytes).hexdigest(),
        counts={"cues": len(cues), "speakers": dict(Counter(c["speaker"] for c in decisions)),
                "confidence": dict(Counter(c["confidence"] for c in decisions)),
                "possible_mixed": sum(c["possible_mixed"] for c in decisions)},
        verification={"exact_source_bytes_recovered": True, "all_cues_preserved": True,
                      "all_timestamps_and_payloads_preserved": True, "input_hashes_unchanged": True},
    )
    if mode == "best_guess":
        record["review_required"] = False
    for source in sources:
        if sha256(source["path"]) != source["sha256"]:
            raise ValueError(f"Input changed during rendering: {source['path']}")
    write_new(outputs[0], output_bytes)
    write_new(outputs[1], encoded_json(record))
    print(json.dumps({"output": str(outputs[0]), "record": str(outputs[1]), **record["counts"]}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare", help="Create a manifest to fill with contextual decisions")
    prep.add_argument("--source", required=True, type=Path)
    prep.add_argument("--speaker", required=True, action="append")
    prep.add_argument("--reference", action="append", type=Path, default=[])
    prep.add_argument("--context", action="append", type=Path, default=[])
    prep.add_argument("--output", required=True, type=Path)
    prep.set_defaults(run=prepare)
    write = commands.add_parser("render", help="Write a new labeled VTT and provenance record")
    write.add_argument("--decisions", required=True, type=Path)
    write.add_argument("--output", required=True, type=Path)
    write.add_argument("--record", required=True, type=Path)
    write.set_defaults(run=render)
    args = parser.parse_args()
    try:
        args.run(args)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    main()
