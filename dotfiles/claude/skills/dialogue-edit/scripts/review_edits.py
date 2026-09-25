#!/usr/bin/env python3
"""Freeze exact dialogue proposals and apply explicit decisions to derived copies.

Standard library only. This verifies bytes, locations, and declared review scope;
it cannot judge speaker identity, meaning, cadence, or whether evidence supports
an edit. Those decisions belong to the skill's reading pass and the GM.
"""

import argparse
import difflib
import hashlib
import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


class Refusal(ValueError):
    pass


ID = re.compile(r"[A-Za-z0-9_.:-]{1,64}\Z")
SCOPES = {"dialogue", "adjacent-attribution", "out-of-scope"}
VERDICTS = {"approve", "reject", "discuss"}


def require(condition, message):
    if not condition:
        raise Refusal(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")


def pairs_unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path):
    return json.loads(Path(path).read_bytes(), object_pairs_hook=pairs_unique)


def nonempty(value, label):
    require(isinstance(value, str) and bool(value.strip()), f"Missing {label}")
    return value


def protected(path):
    return any(part.startswith("scene_extractions") or part.endswith("_smoothed")
               for part in path.parts) or path.suffix.lower() == ".vtt"


def within(path, directory):
    return path.is_relative_to(directory)


def run_path(session, requested, new=False):
    session = Path(session).resolve(strict=True)
    require(session.is_dir() and not protected(session), "Invalid session directory")
    parent = session / "dialogue_edit"
    require(not parent.is_symlink(), "dialogue_edit directory cannot be a symlink")
    requested = Path(requested).absolute()
    require(not requested.is_symlink(), "Run directory cannot be a symlink")
    target = requested.resolve()
    require(target.parent == parent, "Run must be a direct child of <session>/dialogue_edit/")
    require(ID.fullmatch(target.name) and target.name not in {".", ".."}, "Invalid run name")
    require(not protected(target), "Refusing output inside a protected source layer")
    if new:
        require(not target.exists(), f"Output already exists: {target}")
    return session, target


def locate(text, before, start, label):
    nonempty(before, f"{label} original text")
    if start is None:
        start = text.find(before)
        require(start >= 0, f"{label}: original text not found")
        require(text.find(before, start + 1) < 0,
                f"{label}: text occurs more than once; supply an exact start offset")
    require(type(start) is int and start >= 0, f"{label}: invalid start offset")
    require(text[start:start + len(before)] == before, f"{label}: stale or incorrect span")
    return start


def normalize_edits(raw_edits, draft, contents, base):
    require(isinstance(raw_edits, list), "edits must be a list")
    edits = []
    seen = set()
    for raw in raw_edits:
        require(isinstance(raw, dict), "Each edit must be an object")
        eid = raw.get("id")
        require(isinstance(eid, str) and ID.fullmatch(eid), "Invalid edit id")
        require(eid not in seen, f"Duplicate edit id: {eid}")
        seen.add(eid)
        before, after = raw.get("before"), raw.get("after")
        start = locate(draft, before, raw.get("start"), eid)
        require(isinstance(after, str) and before != after, f"{eid}: invalid/no-op replacement")
        scope = raw.get("scope")
        require(scope in SCOPES, f"{eid}: invalid scope")
        support = raw.get("support")
        require(support in {"supported", "unresolved"}, f"{eid}: invalid support status")
        reason = nonempty(raw.get("reason"), f"{eid} reason")
        anchors = raw.get("evidence", [])
        require(isinstance(anchors, list), f"{eid}: evidence must be a list")
        evidence = []
        for anchor in anchors:
            require(isinstance(anchor, dict), f"{eid}: invalid evidence anchor")
            path = (base / nonempty(anchor.get("path"), "evidence path")).resolve(strict=True)
            require(str(path) in contents, f"{eid}: evidence was not declared as an input: {path}")
            quote = anchor.get("quote")
            offset = locate(contents[str(path)], quote, anchor.get("start"), f"{eid} evidence")
            evidence.append({"path": str(path), "quote": quote, "start": offset,
                             "line": contents[str(path)][:offset].count("\n") + 1})
        require(support != "supported" or evidence, f"{eid}: supported edits need evidence")
        lines = draft.splitlines(keepends=True)
        first_line = draft[:start].count("\n")
        last_line = draft[:start + len(before)].count("\n")
        context = "".join(lines[max(0, first_line - 2):last_line + 3])
        edits.append({"id": eid, "start": start, "before": before, "after": after,
                      "line": draft[:start].count("\n") + 1, "scope": scope,
                      "support": support, "reason": reason, "evidence": evidence, "context": context})
    edits.sort(key=lambda item: item["start"])
    for left, right in zip(edits, edits[1:]):
        require(left["start"] + len(left["before"]) <= right["start"],
                f"Overlapping edits: {left['id']} and {right['id']}; combine into one consent unit")
    return edits


def render(original, edits):
    result = original
    for edit in reversed(edits):
        start = locate(original, edit["before"], edit["start"], edit["id"])
        result = result[:start] + edit["after"] + result[start + len(edit["before"]):]
    return result


def difference(original, changed):
    return "".join(difflib.unified_diff(original.splitlines(keepends=True),
                                       changed.splitlines(keepends=True),
                                       fromfile="original", tofile="derived"))


def check_inputs(payload):
    for name, expected in payload["inputs"].items():
        path = Path(name)
        require(path.resolve(strict=True) == path, f"Input path was redirected: {path}")
        require(digest(path.read_bytes()) == expected["sha256"], f"Stale input: {path}")


def write_new(path, value):
    with path.open("xb") as stream:
        stream.write(value if isinstance(value, bytes) else value.encode("utf-8"))


def write_json(path, value):
    write_new(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def review_page(payload, review_id):
    items = []
    escape = html.escape
    for edit in payload["edits"]:
        evidence = "".join(f"<p><code>{escape(a['path'])}:{a['line']}</code></p>"
                           f"<pre>{escape(a['quote'])}</pre>" for a in edit["evidence"])
        permitted = edit["scope"] != "out-of-scope" and edit["support"] == "supported"
        items.append({
            "id": edit["id"],
            "t": f"{escape(edit['id'])}: {escape(edit['reason'])}",
            "y": ("Include this exact replacement in a new derived revision; keep the original."
                  if permitted else "This proposal cannot be applied as recorded; discuss and revise its scope/evidence first.")
                 + f"<p>Original: <code>{escape(payload['draft'])}:{edit['line']}</code></p>"
                 + f"<p>Output area: <code>{escape(payload['run_dir'])}/applied/</code></p>",
            "n": "Keep the original wording in the derived revision and record this rejection.",
            "ev": f"<p>Scope: {escape(edit['scope'])}; support: {escape(edit['support'])}</p>"
                  f"<p>Before</p><pre>{escape(edit['before'])}</pre>"
                  f"<p>After</p><pre>{escape(edit['after'])}</pre>"
                  f"<p>Surrounding draft</p><pre>{escape(edit['context'])}</pre>{evidence}",
        })
    return {"title": payload["scene"], "reviewId": review_id,
            "outputName": "dialogue_edit_decisions.json",
            "lede": "Rule on each exact proposal. Original narration remains unchanged.",
            "footer": "No narration edits have been applied. Unmarked items remain unresolved.",
            "items": items}


def prepare(session, draft, source, references, proposals, run_dir):
    session, run = run_path(session, run_dir, new=True)
    draft, source = Path(draft).resolve(strict=True), Path(source).resolve(strict=True)
    require(draft.suffix.lower() == ".md" and within(draft, session) and not protected(draft),
            "Draft must be existing narration Markdown in the session, not a source extraction")
    require(draft != source, "Narration and source extraction must be different files")
    declared = [(draft, "draft"), (source, "source")]
    declared.extend((Path(p).resolve(strict=True), "reference") for p in references)
    inputs, contents = {}, {}
    for path, role in declared:
        require(not within(path, run), "An input cannot live inside its output run")
        data = path.read_bytes()
        inputs.setdefault(str(path), {"role": role, "sha256": digest(data)})
        contents[str(path)] = data.decode("utf-8")
    proposals = Path(proposals).resolve(strict=True)
    raw = read_json(proposals)
    require(isinstance(raw, dict), "Proposal file must be an object")
    scene = nonempty(raw.get("scene"), "scene name")
    evidence_contents = {p: text for p, text in contents.items() if p != str(draft)}
    edits = normalize_edits(raw.get("edits"), contents[str(draft)], evidence_contents, proposals.parent)
    observations = raw.get("observations", [])
    require(isinstance(observations, list) and all(isinstance(x, str) for x in observations),
            "observations must be a list of strings")
    skill_root = Path(__file__).resolve().parents[1]
    # Harness-neutral: only the files that are identical in the Codex and
    # Claude copies, so the same run records the same fingerprint on either.
    skill_files = [Path(__file__).resolve(), skill_root / "references" / "editorial-guide.md"]
    payload = {"scene": scene, "session": str(session), "run_dir": str(run),
               "draft": str(draft), "source": str(source), "inputs": inputs,
               "edits": edits, "observations": observations,
               "skill_sha256": {str(p.relative_to(skill_root)): digest(p.read_bytes()) for p in skill_files},
               "prepared_at": datetime.now(timezone.utc).isoformat()}
    review_id = "dialogue-edit:" + digest(encoded(payload))
    original = contents[str(draft)]
    candidate = render(original, edits)
    check_inputs(payload)
    run.parent.mkdir(exist_ok=True)
    run.mkdir()  # Exclusive: no overwrite, including a prior incomplete preparation.
    write_new(run / "original.md", original)
    write_new(run / "candidate.md", candidate)
    write_new(run / "candidate.diff", difference(original, candidate))
    if edits:
        write_json(run / "review_page.json", review_page(payload, review_id))
    report = [f"# {scene}\n\nReview: `{review_id}`\n\nOriginal: `{draft}`\n",
              "Candidate is unapproved. Scope/support labels are human judgments, not verified semantics.\n"]
    for edit in edits:
        report.append(f"\n## {edit['id']} — line {edit['line']}\n\n{edit['reason']}\n\n"
                      f"Scope: {edit['scope']}; support: {edit['support']}\n\n"
                      f"Before:\n\n    " + edit["before"].replace("\n", "\n    ")
                      + "\n\nAfter:\n\n    " + edit["after"].replace("\n", "\n    ") + "\n")
        for anchor in edit["evidence"]:
            report.append(f"\nEvidence: `{anchor['path']}:{anchor['line']}`\n\n    "
                          + anchor["quote"].replace("\n", "\n    ") + "\n")
        report.append("\nSurrounding draft:\n\n    " + edit["context"].replace("\n", "\n    ") + "\n")
    report.extend(f"\nObservation: {item}\n" for item in observations)
    write_new(run / "review.md", "\n".join(report))
    # Written last: absent review.json means preparation did not complete.
    write_json(run / "review.json", {"schemaVersion": 1, "reviewId": review_id, "payload": payload})
    return {"status": "prepared" if edits else "no_changes_proposed", "reviewId": review_id,
            "run_dir": str(run), "proposals": len(edits)}


SESSION_PREFIX = re.compile(r"(s\d{2}):(.+)\Z")


def session_page(run_dirs, spec_path, map_path, title=None):
    """One review page for a whole session, built from scenes already frozen by
    `prepare`. Each scene keeps its own run, reviewId and apply step; the page
    only collects their proposals, with ids prefixed by scene (`s01:<id>`)."""
    require(run_dirs, "Name at least one prepared run")
    items, runs, review_ids = [], {}, []
    for index, run_dir in enumerate(run_dirs, 1):
        run, record, _ = load_review(run_dir)
        payload = record["payload"]
        prefix = f"s{index:02d}"
        runs[prefix] = {"run_dir": str(run), "reviewId": record["reviewId"], "scene": payload["scene"]}
        review_ids.append(record["reviewId"])
        for item in review_page(payload, record["reviewId"])["items"]:
            sid = f"{prefix}:{item['id']}"
            require(ID.fullmatch(sid), f"{sid}: scene-prefixed id is too long for the review page")
            items.append({**item, "id": sid,
                          "t": f"{html.escape(payload['scene'])} — {item['t']}"})
    require(items, "No prepared run has proposals; there is nothing to review")
    session_id = "dialogue-edit-session:" + digest(encoded(review_ids))
    spec = {"title": title or "Dialogue edit — session review", "reviewId": session_id,
            "outputName": "dialogue_edit_session_decisions.json",
            "lede": f"{len(items)} proposals across {len(runs)} scenes. Rule on each; "
                    "every scene is applied separately afterwards. Original narration is unchanged.",
            "footer": "No narration edits have been applied. Unmarked items remain unresolved.",
            "items": items}
    for target in (Path(spec_path), Path(map_path)):
        require(not target.parent.is_symlink(), "Session output directory cannot be a symlink")
        target.parent.mkdir(parents=True, exist_ok=True)
    write_json(Path(spec_path), spec)
    write_json(Path(map_path), {"schemaVersion": 1, "reviewId": session_id, "runs": runs})
    return {"status": "session_page", "reviewId": session_id, "scenes": len(runs),
            "items": len(items), "spec": str(spec_path), "map": str(map_path)}


def split_decisions(map_path, decisions_file, out_dir):
    """Turn a session page's decisions into one decision record per scene run,
    each carrying that run's own reviewId, for `apply`."""
    mapping = read_json(map_path)
    require(isinstance(mapping, dict) and mapping.get("schemaVersion") == 1, "Invalid session map")
    decisions = read_json(decisions_file)
    require(isinstance(decisions, dict), "Decision record must be an object")
    require(decisions.get("schemaVersion") == 1 and decisions.get("reviewId") == mapping["reviewId"],
            "Decisions belong to a different session page or schema")
    saved = nonempty(decisions.get("savedAt"), "decision timestamp (record the actual GM ruling)")
    choices, notes = decisions.get("decisions"), decisions.get("notes", {})
    require(isinstance(choices, dict) and isinstance(notes, dict), "Invalid decisions/notes")
    per_run = {prefix: {"decisions": {}, "notes": {}} for prefix in mapping["runs"]}
    for key, target in [(k, "decisions") for k in choices] + [(k, "notes") for k in notes]:
        match = SESSION_PREFIX.fullmatch(key)
        require(match and match[1] in per_run, f"Foreign session decision or note id: {key}")
        source = choices if target == "decisions" else notes
        per_run[match[1]][target][match[2]] = source[key]
    out = Path(out_dir)
    require(not out.is_symlink(), "Output directory cannot be a symlink")
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for prefix, part in per_run.items():
        info = mapping["runs"][prefix]
        _, record, _ = load_review(info["run_dir"])
        require(record["reviewId"] == info["reviewId"], f"{prefix}: run changed since the session page was built")
        ids = {edit["id"] for edit in record["payload"]["edits"]}
        require(set(part["decisions"]) <= ids and set(part["notes"]) <= ids, f"{prefix}: foreign id")
        path = out / f"{prefix}.decisions.json"
        write_json(path, {"schemaVersion": 1, "reviewId": record["reviewId"], "savedAt": saved,
                          "decisions": part["decisions"], "notes": part["notes"],
                          "discuss": sorted(i for i, v in part["decisions"].items() if v == "discuss"),
                          "unmarked": sorted(ids - set(part["decisions"]))})
        written.append({"scene": info["scene"], "run_dir": info["run_dir"], "decisions": str(path)})
    return {"status": "split", "reviewId": mapping["reviewId"], "runs": written}


def load_review(run_dir):
    require(not Path(run_dir).is_symlink(), "Run directory cannot be a symlink")
    run = Path(run_dir).resolve(strict=True)
    review = read_json(run / "review.json")
    require(isinstance(review, dict), "Review record must be an object")
    require(review.get("schemaVersion") == 1, "Unknown review schema")
    payload = review["payload"]
    require(isinstance(payload, dict), "Invalid review payload")
    require(review["reviewId"] == "dialogue-edit:" + digest(encoded(payload)),
            "Review changed since preparation; prepare again and obtain fresh decisions")
    _, checked = run_path(payload["session"], run)
    require(str(checked) == payload["run_dir"], "Run directory does not match frozen review")
    check_inputs(payload)
    original = (run / "original.md").read_bytes()
    require(digest(original) == payload["inputs"][payload["draft"]]["sha256"], "Original snapshot changed")
    require((run / "candidate.md").read_bytes().decode("utf-8") == render(original.decode("utf-8"), payload["edits"]),
            "Candidate differs from frozen proposals")
    return run, review, original.decode("utf-8")


def apply_review(run_dir, decisions_file, revision, write=False):
    run, review, original = load_review(run_dir)
    decisions = read_json(decisions_file)
    require(isinstance(decisions, dict), "Decision record must be an object")
    require(decisions.get("schemaVersion") == 1 and decisions.get("reviewId") == review["reviewId"],
            "Decisions belong to a different proposal set or schema")
    nonempty(decisions.get("savedAt"), "decision timestamp (record the actual GM ruling)")
    choices, notes = decisions.get("decisions"), decisions.get("notes", {})
    require(isinstance(choices, dict) and isinstance(notes, dict), "Invalid decisions/notes")
    edits = review["payload"]["edits"]
    ids = {edit["id"] for edit in edits}
    require(set(choices) <= ids and set(notes) <= ids, "Foreign decision or note id")
    require(all(isinstance(v, str) and v in VERDICTS for v in choices.values()), "Unknown verdict")
    require(all(isinstance(v, str) for v in notes.values()), "Decision notes must be text")
    for key, expected in (("unmarked", ids - set(choices)),
                          ("discuss", {i for i, v in choices.items() if v == "discuss"})):
        if key in decisions:
            values = decisions[key]
            require(isinstance(values, list) and all(isinstance(v, str) for v in values), f"Invalid {key} list")
            require(len(values) == len(set(values)) and set(values) == expected, f"Inconsistent {key} list")
    selected = [edit for edit in edits if choices.get(edit["id"]) == "approve"]
    for edit in selected:
        require(edit["support"] == "supported" and edit["scope"] != "out-of-scope",
                f"{edit['id']}: unresolved evidence or out-of-scope edit; revise and review again")
    require(isinstance(revision, str) and ID.fullmatch(revision) and revision not in {".", ".."},
            "Invalid revision name")
    parent = run / "applied"
    require(not parent.is_symlink(), "Applied output directory cannot be a symlink")
    output = parent / revision
    require(not output.exists() and not output.is_symlink(), "Revision already exists; choose a new name")
    changed = render(original, selected)
    result = {"schemaVersion": 1, "reviewId": review["reviewId"],
              "status": "dry_run" if selected else "no_approved_changes",
              "approved": [e["id"] for e in selected],
              "rejected": [e["id"] for e in edits if choices.get(e["id"]) == "reject"],
              "unresolved": [e["id"] for e in edits if choices.get(e["id"]) in {None, "discuss"}],
              "output": str(output / "scene.md") if selected else None,
              "output_sha256": digest(changed.encode("utf-8")), "decisions": decisions}
    preview = difference(original, changed)
    if write and selected:
        check_inputs(review["payload"])
        parent.mkdir(exist_ok=True)
        output.mkdir()
        write_new(output / "scene.md", changed)
        write_new(output / "approved.diff", preview)
        result["status"] = "applied_partial" if result["unresolved"] else "applied"
        result["applied_at"] = datetime.now(timezone.utc).isoformat()
        # Written last. An output without application.json is incomplete, not approved.
        write_json(output / "application.json", result)
    return result, preview


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare", help="Freeze exact proposals; never calls a model")
    for flag in ("session-dir", "draft", "source", "proposals", "run-dir"):
        prep.add_argument("--" + flag, required=True)
    prep.add_argument("--reference", action="append", default=[])
    apply = commands.add_parser("apply", help="Validate decisions; dry-run unless --write is supplied")
    for flag in ("run-dir", "decisions", "revision"):
        apply.add_argument("--" + flag, required=True)
    page = commands.add_parser("session-page",
                               help="One review page for several prepared scene runs")
    page.add_argument("--run-dir", action="append", required=True, dest="run_dirs")
    page.add_argument("--spec", required=True, help="review page spec to write (for the shared builder)")
    page.add_argument("--map", required=True, help="session map to write (prefix -> run)")
    page.add_argument("--title")
    split = commands.add_parser("split-decisions",
                                help="Split a session page's decisions into one record per scene run")
    for flag in ("map", "decisions", "out-dir"):
        split.add_argument("--" + flag, required=True)
    mode = apply.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            result = prepare(args.session_dir, args.draft, args.source, args.reference,
                             args.proposals, args.run_dir)
        elif args.command == "session-page":
            result = session_page(args.run_dirs, args.spec, args.map, args.title)
        elif args.command == "split-decisions":
            result = split_decisions(args.map, args.decisions, args.out_dir)
        else:
            result, preview = apply_review(args.run_dir, args.decisions, args.revision, args.write)
            if not args.write:
                print(preview)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (Refusal, OSError, ValueError, KeyError, TypeError) as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
