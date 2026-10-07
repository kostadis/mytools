#!/usr/bin/env python3
"""
assemble_answers.py — turn per-batch Q/A files (batch_NN.md) into ONE answered
markdown file per source dossier, in "Option A" form.

Option A (settled with the user):
  - Each output file is the ENTIRE original dossier (YAML header + body + facts)
    kept byte-for-byte intact.
  - Under each `## Uncertainty` bullet that fuzzily matches a resolved answer,
    an inline annotation is appended:  `  - <question> -> Resolved [chN]: <answer>`
  - A `## Resolved Answers (from chapter analysis)` footer is appended at the end
    carrying the COMPLETE Q/A (every question + chapter-cited answer) so nothing
    is ever lost, even when inline matching misses (subagents rephrase questions,
    so exact/substring matching is unreliable).
  - Dossiers whose `## Uncertainty` is literally `None.` are written byte-identical
    to the original (proves originals are never mutated — we only write to OUT).

Paths are overridable via env vars so the script is reusable across campaigns.
Defaults point at the Phandalin setup this was built for.

Env overrides:
  DOSSIER_DIR   source dossiers dir (containing <name>.md)
  OUT_DIR       where batches.json / batch_NN.md / answers/ live
  BATCHES_JSON  (default $OUT_DIR/batches.json)
  ANSWERS_DIR   (default $OUT_DIR/answers)

Run:  python3 assemble_answers.py
Then sanity-check:
  - len(os.listdir(ANSWERS_DIR)) == n dossiers
  - every dossier with real questions contains '## Resolved Answers'
  - a None-uncertainty dossier is byte-identical to its original
"""
import os, re, json, difflib

DOSSIER_DIR = os.environ.get(
    "DOSSIER_DIR",
    "/home/kostadis/src/campaigns/Phandalin/docs/ensemble/state_dossiers")
OUT_DIR = os.environ.get("OUT_DIR", "/home/kostadis/phandalin-output")
BATCHES_JSON = os.environ.get("BATCHES_JSON", os.path.join(OUT_DIR, "batches.json"))
ANSWERS_DIR = os.environ.get("ANSWERS_DIR", os.path.join(OUT_DIR, "answers"))

os.makedirs(ANSWERS_DIR, exist_ok=True)


def toks(s):
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def norm(s):
    return re.sub(r"\s+", " ", s.strip().lstrip("-").strip()).lower()


def parse_qa(text, dossier_file):
    name = dossier_file[:-3] if dossier_file.endswith(".md") else dossier_file
    # subagents drop the .md extension in headings -> allow optional .md
    pat = re.compile(r"^##\s+" + re.escape(name) + r"(?:\.md)?\s*:", re.M)
    m = pat.search(text)
    if not m:
        return []
    start = m.start()
    nxt = re.search(r"\n##\s+", text[start + 2:])
    # PITFALL: last dossier in a batch has no trailing '##'; the EOF branch
    # (len(text)-start-2) is required or the final dossier truncates to ~2 chars.
    end = start + 2 + (nxt.start() if nxt else (len(text) - start - 2))
    block = text[start:end]
    pairs = []
    for seg in re.split(r"\nQ:\s*", block)[1:]:
        qm = re.match(r"(.*?)\nA:\s*(.*)", seg, re.S)
        if not qm:
            continue
        q = qm.group(1).strip()
        rest = qm.group(2)
        ae = re.search(r"\n(?:Q:|Status:)", rest)
        a = rest[:ae.start()].strip() if ae else rest.strip()
        pairs.append((norm(q), a))
    return pairs


UNC_RE = re.compile(r"^(##\s*Uncertainty\b.*?)(?=\n##\s|\Z)", re.M | re.S | re.I)


def best_match(bullet_norm, qa_pairs):
    bt = toks(bullet_norm)
    best, bestscore = None, 0.0
    for qn, ans in qa_pairs:
        qt = toks(qn)
        if not bt or not qt:
            continue
        inter = len(bt & qt)
        jac = inter / len(bt | qt)
        ratio = difflib.SequenceMatcher(None, bullet_norm, qn).ratio()
        score = max(jac, ratio)
        if inter >= min(3, len(bt)) and score > bestscore:
            best, bestscore = ans, score
    return best, bestscore


def annotate(dossier_text, qa_pairs):
    m = UNC_RE.search(dossier_text)
    if not m:
        return dossier_text, (0, 0)
    sec = m.group(1)
    lines = sec.split("\n")
    out_lines = []
    total = matched = 0
    for ln in lines:
        out_lines.append(ln)
        if ln.lstrip().startswith("- "):
            total += 1
            key = norm(ln)
            if not key:
                continue
            ans, score = best_match(key, qa_pairs)
            if ans and score >= 0.5:
                chaps = re.findall(r"ch(\d+)", ans)
                cit = ",".join(f"ch{c}" for c in chaps) or "ch?"
                ans_clean = re.sub(r"^\s*-\s*", "", ans)
                out_lines.append(f"  -> Resolved [{cit}]: {ans_clean}")
                matched += 1
    new_sec = "\n".join(out_lines)
    new_text = dossier_text[:m.start()] + new_sec + dossier_text[m.end():]
    return new_text, (matched, total)


def footer(qa_pairs):
    out = ["\n## Resolved Answers (from chapter analysis)\n"]
    for q, a in qa_pairs:
        chaps = re.findall(r"ch(\d+)", a)
        cit = ",".join(f"ch{c}" for c in chaps) or "ch?"
        a_clean = re.sub(r"^\s*-\s*", "", a)
        out.append(f"**Q:** {q}\n\n**A:** [{cit}] {a_clean}\n")
    return "\n".join(out)


def main():
    batches = json.load(open(BATCHES_JSON))
    dossier_to_batch = {}
    for bid, files in batches.items():
        for f in files:
            dossier_to_batch[f] = bid

    batch_text = {}
    for n in range(1, 12):
        bf = os.path.join(OUT_DIR, f"batch_{n:02d}.md")
        batch_text[n] = open(bf, encoding="utf-8").read() if os.path.exists(bf) else ""

    index_rows = []
    written, missing = [], []
    for dossier_file, bid in dossier_to_batch.items():
        n = int(bid.split("_")[1])
        bt = batch_text.get(n)
        if not bt:
            missing.append(dossier_file)
            continue
        qa_pairs = parse_qa(bt, dossier_file)
        orig_path = os.path.join(DOSSIER_DIR, dossier_file)
        if not os.path.exists(orig_path):
            missing.append(dossier_file)
            continue
        dossier_text = open(orig_path, encoding="utf-8").read()
        if not qa_pairs:
            # no answers found; pass original through unchanged
            open(os.path.join(ANSWERS_DIR, dossier_file), "w", encoding="utf-8").write(dossier_text)
            written.append(dossier_file)
            index_rows.append((dossier_file, "No answers found", bid, "-/-"))
            continue
        new_text, (matched, total) = annotate(dossier_text, qa_pairs)
        new_text = new_text.rstrip() + "\n" + footer(qa_pairs) + "\n"
        open(os.path.join(ANSWERS_DIR, dossier_file), "w", encoding="utf-8").write(new_text)
        written.append(dossier_file)
        status = "Answered" if matched > 0 else "Footer only"
        index_rows.append((dossier_file, status, bid, f"{matched}/{total}"))

    answered = sum(1 for _, s, _, _ in index_rows if s == "Answered")
    footer_only = sum(1 for _, s, _, _ in index_rows if s == "Footer only")
    noans = sum(1 for _, s, _, _ in index_rows if s == "No answers found")
    idx = ["# Per-Dossier Uncertainty Answers (Option A: inline + footer) — Index", ""]
    idx.append(f"- Dossiers written: {len(written)}")
    idx.append(f"- With inline annotations: {answered}")
    idx.append(f"- Footer-only (inline match missed but answers present): {footer_only}")
    idx.append(f"- No answers found / no uncertainty: {noans}")
    idx.append(f"- Missing/extraction-failed: {len(missing)}")
    idx.append("")
    idx.append("| Dossier | Status | Batch | Inline Matched/Total |")
    idx.append("|---------|--------|-------|----------------------|")
    for f, s, b, info in sorted(index_rows, key=lambda x: x[0]):
        idx.append(f"| {f} | {s} | {b} | {info} |")
    open(os.path.join(OUT_DIR, "INDEX.md"), "w", encoding="utf-8").write("\n".join(idx) + "\n")

    print(f"Wrote {len(written)} per-dossier answer files to {ANSWERS_DIR}")
    print(f"inline={answered} footer_only={footer_only} no_answers={noans} missing={len(missing)}")
    if missing:
        print("MISSING:", missing[:20])


if __name__ == "__main__":
    main()
