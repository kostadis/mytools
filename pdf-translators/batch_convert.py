#!/usr/bin/env python3
"""
batch_convert.py — unattended, resumable batch driver for pdf_to_5etools_v2.py.

Converts a whole directory tree of PDFs to 5etools JSON across one or two
local vLLM (DGX Spark) endpoints, load-balanced at the DOCUMENT boundary.

Design (see also convert_all_ddex.sh, the simpler two-box predecessor):

  * Scan pass (parallel, PyMuPDF) classifies every PDF as content vs skip
    (art/map/token/creator-resource by name; image-only/scanned by ~empty
    text) and records page count + extractable-text size. Cached in a
    manifest so re-runs don't re-scan unchanged files.

  * Size-routing for the smaller endpoint: a doc whose whole extractable
    text fits a safe budget (input tokens + the converter's fixed 50K
    output cap <= the endpoint's context window) is eligible for that box;
    bigger docs are pinned to the large-context box. This keeps prompts on
    the 64K box from ever overflowing without touching converter internals.

  * Dispatch: one worker pool per endpoint (default 6 concurrent docs per
    box, each invoked with --concurrency 1, so <= 6 in-flight sequences per
    box — honoring vLLM --max-num-seqs 6). The large-context box drains its
    pinned (big) docs first, leaving small docs for the smaller box.

  * Resilience: an endpoint that's unreachable at start is simply not used;
    a monitor re-checks it every --health-interval seconds and spins up its
    workers when it comes online. Each doc self-retries with backoff.
    --reuse-responses resumes a partially-converted doc from cached chunk
    responses; an existing <stem>.json means already done. The manifest is
    persisted after every doc, so a kill / reboot resumes cleanly.

Outputs land next to each PDF as <stem>.json (the converter default).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from collections import Counter, defaultdict, deque
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONVERTER = HERE / "pdf_to_5etools_v2.py"

CHARS_PER_TOKEN = 4  # rough English-prose estimate for routing only
# A prompt-capped endpoint (e.g. spark2) accepts a doc only if its largest
# prompt stays under its token cap. We route on whole-document text (a safe
# upper bound on any single chunk's text) and reserve headroom for the system
# prompt, so chunk_text + system_prompt stays under the cap.
SYSTEM_PROMPT_RESERVE_TOKENS = 4_000

DEFAULT_MODEL = "Qwen/Qwen3-Next-80B-A3B-Instruct-FP8"

# Filename / path substrings that mark a PDF as non-convertible (art, maps,
# tokens, VTT assets, creator resources, etc.). Matched case-insensitively
# against the path relative to --root. Conservative on purpose.
SKIP_NAME_PATTERNS = [
    "creator resource", "art pack", "art-pack", "scenes & symbols",
    "scenes and symbols", "heroes & villains art", "map pack", "battlemap",
    "battle map", "map tiles", "tile set", "tileset", " maps", "map set",
    "token pack", "tokens", " vtt", "roll20", "foundry", "card deck",
    "deck of", "cards)", "miniature", "papercraft", "paper mini", "soundtrack",
    "playlist", "music", "ambience", "wallpaper", "coloring", "colouring",
    "sticker", "dice set", "character sheet", "char sheet", "form-fillable",
    "form fillable", "cover art", "stock art", "poster map", "handout pack",
]

# Image-only / scan detection thresholds (extractable text, not OCR).
MIN_TOTAL_TEXT_CHARS = 400      # below this -> image-only/empty
MIN_AVG_CHARS_PER_PAGE = 40     # below this -> mostly images / scan
SCAN_PAGE_CAP = 2000            # don't read text past this many pages


# --------------------------------------------------------------------------
# Canonical-file selection (dedup) — reuse rpg-lib's library DB, then collapse
# format/version variants the library leaves alone.
#
# rpg-lib (../rpg-lib/rpg_library.db, table `books`) already computes, for the
# same DriveThru tree, is_old_version / is_draft / is_duplicate (exact-content
# duplicate). We reuse those flags directly. rpg-lib deliberately does NOT
# collapse PrintFriendly/Optimized/full_res or v1.4-vs-v2 siblings (it treats
# versions as intentional variants), so we add that here: within one folder +
# normalized title we keep a single canonical file. The printer-friendly
# edition is preferred because its stripped-down layout yields a cleaner text
# layer for the converter. Maps booklets, Pathfinder (-PF) editions, and
# Preview/Promo teasers are skipped as separate, non-target content.
# --------------------------------------------------------------------------
DEFAULT_LIBRARY_DB = HERE.parent / "rpg-lib" / "rpg_library.db"

# Format tokens (cleaned out of the title key so variants group together) and
# the rank that decides which format wins (lower = preferred canonical).
# Includes the noise token "pdf" (common in "Optimized_PDF") so it doesn't leak
# into the grouping key. Only affects _variant_title_key, never the rank.
# Format / layout tokens stripped from the grouping key so the same content in
# different exports (printer-friendly, optimized, low-res, 2-page spreads, etc.)
# collapses to one product. The English-word tokens (pages/spreads/final/hd/sd)
# are word-bounded so they don't strip mid-word ("Rampage", "Shadowdale").
_FMT_RE = re.compile(
    r"printer[\s_\-]?friendly|print[\s_\-]?friendly|printfriendly"
    r"|optimi[sz]ed|full[\s_\-]?res|hi[\s_\-]?res|high[\s_\-]?res"
    r"|accessibl?e|compressed|colou?r|phone|image[\s_\-]?only"
    r"|quick[\s_\-]?load"
    r"|low[\s_\-]?res|lowres|screen[\s_\-]?reader|selectable"
    r"|\bspreads?\b|\d+[\s_\-]?page|\bpages?\b|\bhd\b|\bsd\b|\bfinal\b"
    r"|pdf",
    re.I,
)
_FMT_PREFERRED_RE = re.compile(
    r"printer[\s_\-]?friendly|print[\s_\-]?friendly|printfriendly|accessibl?e", re.I
)
# Disfavored (least-preferred) exports: heavy/optimized/low-quality layouts —
# Quick Load (flattened fast-loading), low-res, SD, 2-page spreads, page-layout
# and form-fillable "selectable" variants. Used only to pick a winner, never to
# group; printer-friendly/plain beats these.
_FMT_DISFAVORED_RE = re.compile(
    r"optimi[sz]ed|full[\s_\-]?res|hi[\s_\-]?res|high[\s_\-]?res|compressed"
    r"|quick[\s_\-]?load"
    r"|low[\s_\-]?res|lowres|selectable|\bspreads?\b|\d+[\s_\-]?page|\bpages?\b|\bsd\b",
    re.I,
)
# A version token, matched two ways (each captured in its own group):
#   (1) v/ver prefix + digits        -> v1.4, ver1_5, v_2, v2_7_1, v3_0
#   (2) BARE multi-segment dotted    -> 1.0.1, 1.0.2, 1.1, 2024.01 (>= 2 parts)
# DriveThru stamps versions as bare dotted numbers ("Manual_of_the_Planes_1.0.2"),
# with no v/ver prefix, so branch (1) alone missed them and left every version as
# a distinct product. Branch (2) requires at least two numeric segments and a
# non-digit before it (negative lookbehind), so a single bare number that is real
# title content ("100 NPCs", "5MWD", "Volume 2") is still NOT stripped — only
# things that actually look like a version are. Used for both grouping
# (_variant_title_key) and winner selection (_parse_version).
_VER_RE = re.compile(
    r"v(?:er)?[\s_.\-]?(\d+(?:[._]\d+)*)"     # (1) v-prefixed
    r"|(?<!\d)(\d+(?:[._]\d+)+)",             # (2) bare, >= 2 segments
    re.I,
)
_PRODUCT_ID_RE = re.compile(r"^\d{4,}-")


def _strip_product_id(stem: str) -> str:
    return _PRODUCT_ID_RE.sub("", stem)


def _variant_title_key(filename: str) -> str:
    """Group key for true variants of one product: drop extension, product-ID
    prefix, version tokens, and format tokens, then collapse separators."""
    stem = filename.rsplit(".", 1)[0]
    stem = _strip_product_id(stem)
    stem = _FMT_RE.sub(" ", stem)
    stem = _VER_RE.sub(" ", stem)
    stem = re.sub(r"[\(\)\[\]_\-\s.]+", " ", stem).strip().lower()
    return stem


def _format_rank(filename: str) -> int:
    """0 = printer-friendly/accessible (preferred), 1 = plain, 2 = optimized/
    full-res/compressed (least preferred)."""
    if _FMT_PREFERRED_RE.search(filename):
        return 0
    if _FMT_DISFAVORED_RE.search(filename):
        return 2
    return 1


def _parse_version(filename: str) -> tuple[int, ...]:
    """Comparable version tuple from the last version token; (0,) if none.

    Strips the product-ID prefix first so a numeric product ID can't be mistaken
    for a version, then takes the last _VER_RE match (whichever branch matched —
    v-prefixed group 1 or bare-dotted group 2)."""
    matches = list(_VER_RE.finditer(_strip_product_id(filename)))
    if not matches:
        return (0,)
    token = next((g for g in matches[-1].groups() if g), "")
    parts = re.split(r"[._]", token)
    nums = tuple(int(p) for p in parts if p.isdigit())
    return nums or (0,)


# Companion / non-target files skipped outright (separate deliverables, not
# format variants of the main book). Boundaries avoid mid-word matches.
_MAPS_RE = re.compile(
    r"(?:^|[\s_\-(])maps?(?:[\s_\-).]|$)|map[\s_\-]?only|maps?[\s_\-]?booklet", re.I
)
_PATHFINDER_RE = re.compile(r"[\s_\-]pf(?:[\s_\-).]|$)", re.I)
_PREVIEW_RE = re.compile(r"(?:^|[\s_\-(])(?:preview|promo|teaser|sample)(?:[\s_\-).]|$)", re.I)


def _companion_kind(filename: str) -> str | None:
    if _MAPS_RE.search(filename):
        return "maps"
    if _PATHFINDER_RE.search(filename):
        return "pathfinder"
    if _PREVIEW_RE.search(filename):
        return "preview"
    return None


def load_library_flags(db_path, root: Path, docs: dict) -> dict:
    """Map each manifest relpath to (is_old_version, is_draft, is_duplicate)
    from rpg-lib's books table. Join on absolute filepath. Missing/unreadable
    DB -> empty dict (caller falls back to converting everything)."""
    import sqlite3

    flags: dict[str, tuple[int, int, int]] = {}
    abs_to_rel = {os.path.normpath(str(root / rel)): rel for rel in docs}
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except Exception as e:  # noqa: BLE001
        print(f"[dedup] cannot open library DB {db_path} ({e}); converting all files")
        return flags
    try:
        cur = conn.execute(
            "SELECT filepath, is_old_version, is_draft, is_duplicate FROM books"
        )
        for fp, old, draft, dup in cur:
            rel = abs_to_rel.get(os.path.normpath(fp))
            if rel is not None:
                flags[rel] = (int(old or 0), int(draft or 0), int(dup or 0))
    except Exception as e:  # noqa: BLE001
        print(f"[dedup] library DB query failed ({e}); converting all files")
        flags = {}
    finally:
        conn.close()
    print(f"[dedup] library DB matched {len(flags)}/{len(docs)} manifest files")
    return flags


def select_canonical(docs: dict, flags: dict) -> dict:
    """Mark non-canonical docs status='skipped' with a reason. Two passes:
    (A) rpg-lib flags + companion files; (B) collapse remaining same-title
    variants to one canonical (newest version, then printer-friendly, then
    most text/pages/newest). Mutates *docs*; returns per-reason counts.

    Version election is AUTHORITATIVE in rpg-lib (pdf_indexer.elect_latest_versions
    sets is_old_version on superseded versions), consumed here via Pass A's
    `library:old_version`. Pass B's version ranking (`_parse_version`) is now a
    defensive fallback for files the library DB hasn't indexed yet; its real job
    is the same-version FORMAT tiebreak (printer-friendly > Quick Load), which
    rpg-lib intentionally leaves to the consumer. Keep both."""
    counts: Counter[str] = Counter()

    def _skip(ent: dict, reason: str) -> None:
        ent["status"] = "skipped"
        ent["reason"] = reason
        counts[reason] += 1

    # Pass A — library flags (old/duplicate/draft) and companion files.
    for rel, ent in docs.items():
        if ent.get("status") == "skipped":
            continue
        old, draft, dup = flags.get(rel, (0, 0, 0))
        if old:
            _skip(ent, "library:old_version")
        elif dup:
            _skip(ent, "library:duplicate")
        elif draft:
            _skip(ent, "library:draft")
        elif (kind := _companion_kind(os.path.basename(rel))):
            _skip(ent, f"variant:{kind}")

    # Pass B — collapse same-title variants within a folder.
    groups: dict[tuple, list] = defaultdict(list)
    for rel, ent in docs.items():
        if ent.get("status") == "skipped":
            continue
        key = (os.path.dirname(rel), _variant_title_key(os.path.basename(rel)))
        groups[key].append(rel)

    for rels in groups.values():
        if len(rels) < 2:
            continue

        def _rank(rel: str):
            ent = docs[rel]
            name = os.path.basename(rel)
            # max() picks the canonical: newest version, then printer-friendly
            # (rank 0 -> negate so it sorts highest), then richest/newest file.
            return (
                _parse_version(name),
                -_format_rank(name),
                ent.get("text_chars", 0),
                ent.get("pages", 0),
                ent.get("mtime", 0),
                -len(name),
            )

        winner = max(rels, key=_rank)
        for rel in rels:
            if rel != winner:
                _skip(docs[rel], "variant:superseded")

    return dict(counts)


# --------------------------------------------------------------------------
# Scan pass
# --------------------------------------------------------------------------
def classify_pdf(path_str: str, root_str: str):
    """Worker (runs in a process pool). Returns a dict for the manifest entry.

    Never raises — a failed scan is recorded as a skip with reason 'scan_error'
    so one bad PDF can't abort the whole inventory.
    """
    path = Path(path_str)
    rel = os.path.relpath(path_str, root_str)
    try:
        st = path.stat()
        size, mtime = st.st_size, int(st.st_mtime)
    except OSError as e:
        return rel, {"status": "skipped", "reason": f"stat_error: {e}",
                     "size": 0, "mtime": 0}

    # Name-based non-content filter first (cheap, no open).
    low = rel.lower()
    for pat in SKIP_NAME_PATTERNS:
        if pat in low:
            return rel, {"status": "skipped", "reason": f"noncontent_name:{pat.strip()}",
                         "size": size, "mtime": mtime, "pages": 0, "text_chars": 0}

    # Open and measure extractable text.
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(path_str)
        pages = doc.page_count
        text_chars = 0
        scanned = min(pages, SCAN_PAGE_CAP)
        for i in range(scanned):
            text_chars += len(doc[i].get_text("text"))
        doc.close()
    except Exception as e:  # noqa: BLE001 - never let one PDF kill the scan
        return rel, {"status": "skipped", "reason": f"scan_error: {type(e).__name__}",
                     "size": size, "mtime": mtime, "pages": 0, "text_chars": 0}

    avg = text_chars / scanned if scanned else 0
    if text_chars < MIN_TOTAL_TEXT_CHARS or avg < MIN_AVG_CHARS_PER_PAGE:
        return rel, {"status": "skipped", "reason": "image_only_or_scan",
                     "size": size, "mtime": mtime, "pages": pages,
                     "text_chars": text_chars}

    return rel, {"status": "pending", "reason": "", "size": size,
                 "mtime": mtime, "pages": pages, "text_chars": text_chars}


def build_manifest(root: Path, prior: dict, workers: int) -> dict:
    """Scan all PDFs under root, reusing prior entries for unchanged files."""
    pdfs = sorted(str(p) for p in root.rglob("*.pdf")
                  if not re.search(r"\.old-\d+\.pdf$", p.name, re.I))
    print(f"[scan] {len(pdfs)} PDFs under {root}")

    docs = {}
    to_scan = []
    reused = 0
    for p in pdfs:
        rel = os.path.relpath(p, str(root))
        try:
            st = os.stat(p)
        except OSError:
            to_scan.append(p)
            continue
        ent = prior.get(rel)
        if ent and ent.get("size") == st.st_size and ent.get("mtime") == int(st.st_mtime) \
           and "text_chars" in ent:
            # Reuse classification; status is recomputed at dispatch (json on disk).
            docs[rel] = ent
            reused += 1
        else:
            to_scan.append(p)

    print(f"[scan] reusing {reused} cached entries, scanning {len(to_scan)} ...")
    if to_scan:
        done = 0
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(classify_pdf, p, str(root)): p for p in to_scan}
            for fut in as_completed(futs):
                rel, ent = fut.result()
                docs[rel] = ent
                done += 1
                if done % 100 == 0 or done == len(to_scan):
                    print(f"[scan] {done}/{len(to_scan)}", flush=True)
    return docs


# --------------------------------------------------------------------------
# Endpoints + dispatch
# --------------------------------------------------------------------------
@dataclass
class Endpoint:
    name: str
    url: str                              # OpenAI-compatible base, e.g. http://ip:8001/v1
    max_ctx: int                          # context window in tokens (informational)
    takes_big: bool                       # may run docs too big for a prompt-capped box
    pool: int                             # concurrent docs (== max in-flight seqs @ concurrency 1)
    max_prompt_tokens: int | None = None  # per-request prompt cap; None = no cap
    active: bool = False
    threads: list = field(default_factory=list)

    def safe_input_chars(self) -> int:
        """Max whole-doc text (chars) routable here, with system-prompt headroom.

        None max_prompt_tokens (the large box) accepts any document.
        """
        if self.max_prompt_tokens is None:
            return 1 << 30
        budget = max(0, self.max_prompt_tokens - SYSTEM_PROMPT_RESERVE_TOKENS)
        return budget * CHARS_PER_TOKEN

    def reachable(self) -> bool:
        try:
            with urllib.request.urlopen(self.url.rstrip("/") + "/models", timeout=6) as r:
                return r.status == 200
        except Exception:  # noqa: BLE001
            return False


class Dispatcher:
    def __init__(self, args, docs: dict, root: Path):
        self.args = args
        self.docs = docs
        self.root = root
        self.lock = threading.Lock()
        self.big: deque[str] = deque()    # spark1-only (oversized for small box)
        self.small: deque[str] = deque()  # fits the small box too
        self.stop = threading.Event()
        self.counts = {"done": 0, "failed": 0, "skipped": 0,
                       "already": 0, "total": 0,
                       "carried_failed": 0, "deferred": 0}
        self.logdir = Path(args.logdir)
        self.logdir.mkdir(parents=True, exist_ok=True)

    # ---- queue construction -------------------------------------------------
    def enqueue(self, small_endpoint: Endpoint | None):
        safe_chars = small_endpoint.safe_input_chars() if small_endpoint else 0
        for rel, ent in sorted(self.docs.items()):
            if ent.get("status") == "skipped":
                self.counts["skipped"] += 1
                continue
            prior_status = ent.get("status")  # from the reused prior manifest
            pdf = self.root / rel
            out = pdf.with_suffix(".json")
            if out.exists() and not self.args.force:
                ent["status"] = "done"
                self.counts["already"] += 1
                continue
            # Prior-failure filters: a doc with no JSON is either a never-tried
            # doc or one the last run marked 'failed'. By default both are
            # re-queued; these flags split them so a restart can make forward
            # progress (--skip-failed) or target only the failures in a
            # remediation pass (--only-failed).
            if self.args.skip_failed and prior_status == "failed":
                ent["status"] = "failed"           # carry the failure forward
                self.counts["carried_failed"] += 1
                continue
            if self.args.only_failed and prior_status != "failed":
                self.counts["deferred"] += 1        # not a prior failure; skip
                continue
            ent["status"] = "pending"
            self.counts["total"] += 1
            fits_small = ent.get("text_chars", 1 << 30) <= safe_chars
            ent["eligible_small"] = bool(small_endpoint) and fits_small
            (self.small if ent["eligible_small"] else self.big).append(rel)

    def next_doc(self, takes_big: bool) -> str | None:
        with self.lock:
            if takes_big and self.big:
                return self.big.popleft()
            if self.small:
                return self.small.popleft()
            return None

    # ---- per-doc execution --------------------------------------------------
    def run_doc(self, rel: str, ep: Endpoint):
        pdf = self.root / rel
        out = pdf.with_suffix(".json")
        log = self.logdir / (re.sub(r"[^\w.-]+", "_", rel) + ".log")
        cmd = [
            sys.executable, str(CONVERTER), str(pdf),
            "--provider", "dgx", "--endpoint", ep.url,
            "--model", self.args.model,
            "--concurrency", str(self.args.doc_concurrency),
            "--output-mode", "homebrew", "--type", self.args.type,
            "--reuse-responses",
        ]
        attempts = 0
        ok = False
        last_exit = None
        t0 = time.monotonic()
        while attempts < self.args.max_retries + 1 and not self.stop.is_set():
            attempts += 1
            with open(log, "a") as lf:
                lf.write(f"\n===== attempt {attempts} on {ep.name} ({ep.url}) "
                         f"{time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
                lf.flush()
                try:
                    rc = subprocess.run(
                        cmd, cwd=str(HERE), stdout=lf, stderr=subprocess.STDOUT,
                        timeout=self.args.doc_timeout,
                        env={**os.environ,
                             "PDF2E_MAX_CHUNK_CHARS": str(self.args.max_chunk_chars),
                             # Prompt cap is a HARD ERROR (no chunking): a chunk
                             # whose prompt exceeds this aborts the doc with no
                             # JSON, so it stays failed for a larger-context retry.
                             "PDF2E_MAX_PROMPT_TOKENS": str(self.args.prompt_cap),
                             # Per-chunk soft cap: a chunk over this is skipped
                             # without sending (won't finish in the timeout) and
                             # logged as a failed chunk; the doc continues.
                             "PDF2E_MAX_CHUNK_TOKENS": str(self.args.chunk_token_cap),
                             # Output budget (max_tokens). prompt_cap + this must
                             # stay under the endpoint's served --max-model-len.
                             "PDF2E_MAX_OUTPUT_TOKENS": str(self.args.output_cap)},
                    ).returncode
                except subprocess.TimeoutExpired:
                    lf.write(f"\n[batch] TIMEOUT after {self.args.doc_timeout}s\n")
                    rc = 124
            last_exit = rc
            if rc == 0 and out.exists():
                ok = True
                break
            if rc == 3:
                # Partial conversion: ≥1 chunk failed fast (e.g. a read timeout)
                # but the rest are cached and no JSON was written. Don't spend the
                # remaining doc-level retries re-timing-out the same chunk — mark
                # failed and move on; a later --reuse-responses pass finishes it.
                break
            if attempts <= self.args.max_retries and not self.stop.is_set():
                time.sleep(min(60, 5 * attempts))  # linear backoff, capped

        dur = round(time.monotonic() - t0, 1)
        with self.lock:
            ent = self.docs[rel]
            ent.update(status="done" if ok else "failed", endpoint=ep.name,
                       attempts=attempts, exit=last_exit, duration_s=dur,
                       log=str(log))
            self.counts["done" if ok else "failed"] += 1
            done = self.counts["done"]
            failed = self.counts["failed"]
            total = self.counts["total"]
            self._persist_locked()
        flag = "OK " if ok else "FAIL"
        print(f"[{time.strftime('%H:%M:%S')}] {flag} {done+failed}/{total} "
              f"({ep.name}, {dur}s, try {attempts}) {rel}", flush=True)

    def worker(self, ep: Endpoint):
        while not self.stop.is_set():
            rel = self.next_doc(ep.takes_big)
            if rel is None:
                return
            self.run_doc(rel, ep)

    def start_endpoint(self, ep: Endpoint):
        ep.active = True
        for _ in range(ep.pool):
            t = threading.Thread(target=self.worker, args=(ep,), daemon=True)
            t.start()
            ep.threads.append(t)
        print(f"[dispatch] {ep.name} online — {ep.pool} workers ({ep.url})")

    # ---- persistence --------------------------------------------------------
    def _persist_locked(self):
        path = Path(self.args.manifest)
        tmp = path.with_suffix(".tmp")
        payload = {"root": str(self.root), "saved_at": int(time.time()),
                   "docs": self.docs}
        tmp.write_text(json.dumps(payload, indent=1))
        tmp.replace(path)

    def persist(self):
        with self.lock:
            self._persist_locked()


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", type=Path,
                   default=Path("/mnt/g/My Drive/DriveThru/Dungeon Masters Guild"),
                   help="Directory tree of PDFs to convert (recursively).")
    p.add_argument("--spark1", default="http://192.168.1.147:8001/v1",
                   help="Large-context endpoint (takes any doc).")
    p.add_argument("--spark1-ctx", type=int, default=262144)
    p.add_argument("--spark2", default="http://192.168.1.121:8001/v1",
                   help="Prompt-capped endpoint (small docs only). "
                        "Empty string disables it.")
    p.add_argument("--spark2-ctx", type=int, default=262144,
                   help="spark2 context window (tokens), informational; 256K.")
    p.add_argument("--prompt-cap", type=int, default=40000,
                   help="Max prompt (input) tokens EACH box accepts. Passed to the "
                        "converter as PDF2E_MAX_PROMPT_TOKENS, where it is a HARD "
                        "ERROR: a chunk whose prompt exceeds it aborts the whole doc "
                        "(no JSON written), leaving it failed for a larger-context "
                        "retry. Also used for endpoint routing here.")
    p.add_argument("--chunk-token-cap", type=int, default=20000,
                   help="Per-chunk soft cap (input tokens). Passed to the converter "
                        "as PDF2E_MAX_CHUNK_TOKENS: a single chunk whose estimated "
                        "prompt exceeds it is SKIPPED without being sent (it won't "
                        "finish generating inside the read-timeout) and logged as a "
                        "failed chunk; the doc's other chunks still run, and the doc "
                        "ends as a partial (no JSON, exit 3) so the failure is logged. "
                        "Unlike --prompt-cap (whole-doc abort), this fails just the "
                        "oversized chunk. 0 disables.")
    p.add_argument("--output-cap", type=int, default=80000,
                   help="Output-token budget (max_tokens) handed to the converter via "
                        "PDF2E_MAX_OUTPUT_TOKENS. prompt-cap + output-cap must stay "
                        "under the endpoint's served --max-model-len (DGX Qwen 128K: "
                        "40000 + 80000 = 120000 < 131072). Raise the slot's MAX_LEN "
                        "to ~200K before pushing this past ~85K.")
    p.add_argument("--max-chunk-chars", type=int, default=128000,
                   help="Per-chunk input char cap handed to the converter via "
                        "PDF2E_MAX_CHUNK_CHARS. Splits oversized sections by their "
                        "children to keep prompts under --prompt-cap (128000 ~= 32-37K "
                        "tok + system); only an unsplittable leaf trips the hard cap.")
    p.add_argument("--pool", type=int, default=6,
                   help="Default concurrent docs per endpoint (== max in-flight seqs "
                        "at --doc-concurrency 1). Keep pool*doc-concurrency <= that "
                        "box's vLLM --max-num-seqs. Overridden per box by --pool1/--pool2.")
    p.add_argument("--pool1", type=int, default=None,
                   help="Concurrent docs for spark1 (overrides --pool). Set to spark1's "
                        "--max-num-seqs / --doc-concurrency, e.g. 16 for the seqs-16 box.")
    p.add_argument("--pool2", type=int, default=None,
                   help="Concurrent docs for spark2 (overrides --pool). Set to spark2's "
                        "--max-num-seqs / --doc-concurrency, e.g. 4 for the MTP seqs-4 box.")
    p.add_argument("--doc-concurrency", type=int, default=1,
                   help="Chunk concurrency WITHIN each doc. pool*doc-concurrency "
                        "must stay <= the box's --max-num-seqs.")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--type", choices=["adventure", "book"], default="adventure")
    p.add_argument("--max-retries", type=int, default=2,
                   help="Extra attempts per doc after the first (default 2).")
    p.add_argument("--doc-timeout", type=int, default=10800,
                   help="Hard per-attempt timeout in seconds (default 3h).")
    p.add_argument("--health-interval", type=int, default=60,
                   help="Seconds between re-checks of a down endpoint.")
    p.add_argument("--scan-workers", type=int, default=8)
    p.add_argument("--library-db", type=Path,
                   default=(DEFAULT_LIBRARY_DB if DEFAULT_LIBRARY_DB.exists() else None),
                   help="rpg-lib SQLite DB to reuse for canonical-file selection "
                        "(skips old-version/draft/exact-duplicate files, then collapses "
                        "format/version variants to one printer-friendly canonical per "
                        f"product). Default: {DEFAULT_LIBRARY_DB} if present, else none.")
    p.add_argument("--no-dedup", action="store_true",
                   help="Disable canonical-file selection; convert every content PDF "
                        "(old versions, format variants, maps, etc.) as before.")
    p.add_argument("--manifest", default=str(HERE / "dmsguild-manifest.json"))
    p.add_argument("--skiplist", default=str(HERE / "dmsguild-skiplist.tsv"))
    p.add_argument("--logdir", default=str(HERE / "dmsguild-logs"))
    p.add_argument("--force", action="store_true",
                   help="Reconvert even if <stem>.json already exists.")
    p.add_argument("--skip-failed", action="store_true",
                   help="Don't re-attempt docs the prior run marked 'failed' "
                        "(carry their failure forward). Lets a restart make "
                        "progress on never-attempted docs instead of re-failing "
                        "known timeouts. Pair with --only-failed later to do a "
                        "remediation pass of just those on a less-contended box.")
    p.add_argument("--only-failed", action="store_true",
                   help="Attempt ONLY docs the prior run marked 'failed' (skip "
                        "everything else). The remediation pass: re-run the "
                        "timed-out docs alone, e.g. with --pool 2 on a faster box. "
                        "Cached chunks are reused via --reuse-responses.")
    p.add_argument("--rescan", action="store_true",
                   help="Ignore cached scan entries and re-classify every PDF.")
    p.add_argument("--list", action="store_true",
                   help="Scan + classify + plan, write manifest/skiplist, then exit.")
    return p.parse_args(argv)


def write_skiplist(docs: dict, path: str):
    rows = [(rel, e.get("reason", ""), e.get("pages", 0), e.get("text_chars", 0))
            for rel, e in sorted(docs.items()) if e.get("status") == "skipped"]
    with open(path, "w") as f:
        f.write("relpath\treason\tpages\ttext_chars\n")
        for rel, reason, pages, tc in rows:
            f.write(f"{rel}\t{reason}\t{pages}\t{tc}\n")
    return len(rows)


def main(argv=None):
    args = parse_args(argv)
    root = args.root
    if not root.is_dir():
        sys.exit(f"error: --root not a directory: {root}")

    if args.skip_failed and args.only_failed:
        sys.exit("error: --skip-failed and --only-failed are mutually exclusive")

    prior = {}
    mpath = Path(args.manifest)
    if mpath.exists() and not args.rescan:
        try:
            prior = json.loads(mpath.read_text()).get("docs", {})
        except Exception as e:  # noqa: BLE001
            print(f"[warn] could not read prior manifest ({e}); rescanning")

    docs = build_manifest(root, prior, args.scan_workers)

    # Canonical-file selection: reuse rpg-lib's old/draft/duplicate flags, then
    # collapse format/version variants to one printer-friendly canonical per
    # product. Marks rejects status='skipped' (reason library:* / variant:*) so
    # they flow to the skiplist and are never enqueued. No DB / --no-dedup ->
    # convert everything (prior behavior).
    dedup_counts = {}
    if not args.no_dedup and args.library_db:
        flags = load_library_flags(args.library_db, root, docs)
        dedup_counts = select_canonical(docs, flags)

    # Endpoints.
    # Both boxes are now equally prompt-capped (40K), so both accept any doc and
    # work round-robins across them (larger docs drained first by whichever box is
    # free). The converter's chunk cap (--max-chunk-chars) guarantees no prompt
    # exceeds --prompt-cap on either box, so there is no "big -> spark1 only" split.
    # Per-box pool so asymmetric boxes (e.g. spark1 seqs 16 throughput, spark2
    # MTP seqs 4 latency) can each be driven at their own --max-num-seqs.
    pool1 = args.pool1 if args.pool1 is not None else args.pool
    pool2 = args.pool2 if args.pool2 is not None else args.pool
    spark1 = Endpoint("spark1", args.spark1, args.spark1_ctx, takes_big=True,
                      pool=pool1, max_prompt_tokens=args.prompt_cap)
    spark2 = None
    if args.spark2.strip():
        spark2 = Endpoint("spark2", args.spark2, args.spark2_ctx, takes_big=True,
                          pool=pool2, max_prompt_tokens=args.prompt_cap)

    disp = Dispatcher(args, docs, root)
    disp.enqueue(small_endpoint=spark2)

    n_skip = write_skiplist(docs, args.skiplist)
    disp.persist()

    # Routing summary.
    n_small = sum(1 for r in disp.small)  # noqa: F841 (len works on deque)
    print("\n=== plan ===")
    print(f"  content to convert : {disp.counts['total']}")
    print(f"    larger docs (both boxes): {len(disp.big)}")
    print(f"    smaller docs (both boxes): {len(disp.small)}")
    print(f"  already done       : {disp.counts['already']}")
    if disp.counts["carried_failed"]:
        print(f"  failed (carried)   : {disp.counts['carried_failed']}  "
              f"(--skip-failed: not retried this run)")
    if disp.counts["deferred"]:
        print(f"  deferred (not fail): {disp.counts['deferred']}  "
              f"(--only-failed: only prior failures attempted)")
    print(f"  skipped (total)    : {n_skip}  -> {args.skiplist}"
          f"  (non-content + dedup)")
    if dedup_counts:
        total_dedup = sum(dedup_counts.values())
        print(f"  deduped (canonical): {total_dedup} files dropped as non-canonical")
        for reason in sorted(dedup_counts):
            print(f"      {reason}: {dedup_counts[reason]}")
    elif args.no_dedup:
        print("  deduped (canonical): disabled (--no-dedup)")
    elif not args.library_db:
        print("  deduped (canonical): no library DB found; converting all variants")
    print(f"  manifest           : {args.manifest}")
    print(f"  logs               : {args.logdir}")
    print(f"  prompt cap (both)  : {args.prompt_cap} tok in (HARD ERROR -> doc fails, "
          f"no JSON); output cap {args.output_cap} tok; chunk cap "
          f"{args.max_chunk_chars} chars")
    print(f"  per-chunk cap      : {args.chunk_token_cap} tok in "
          f"(over -> skip that chunk, log it, doc ends partial)"
          if args.chunk_token_cap > 0 else
          "  per-chunk cap      : disabled")
    print()

    if args.list:
        print("[--list] plan only; not converting.")
        return 0
    if disp.counts["total"] == 0:
        print("Nothing to convert.")
        return 0

    # Signal handling: stop spawning, let in-flight docs finish, persist.
    def _sig(_s, _f):
        print("\n[batch] interrupt — finishing in-flight docs, then exiting "
              "(re-run to resume).", flush=True)
        disp.stop.set()
    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)

    # Boxes are symmetric now: start whichever endpoints are reachable, and
    # monitor any that are down (e.g. mid-reconfigure), adding them when they
    # come up. Need at least one box to start.
    endpoints = [e for e in (spark1, spark2) if e]
    up = [e for e in endpoints if e.reachable()]
    if not up:
        sys.exit("error: no endpoints reachable — bring at least one box up first.")
    for e in up:
        disp.start_endpoint(e)
    down = [e for e in endpoints if not e.active]
    if down:
        print(f"[dispatch] waiting on {', '.join(e.name for e in down)}; "
              f"re-checking every {args.health_interval}s.")

        def monitor(pending=down):
            pending = list(pending)
            while pending and not disp.stop.is_set():
                if disp.work_remaining() == 0:
                    return
                for e in list(pending):
                    if e.reachable():
                        disp.start_endpoint(e)
                        pending.remove(e)
                if pending:
                    disp.stop.wait(args.health_interval)
        threading.Thread(target=monitor, daemon=True).start()

    # Wait for completion: poll until all worker threads have exited.
    try:
        while True:
            alive = [t for t in spark1.threads if t.is_alive()]
            if spark2:
                alive += [t for t in spark2.threads if t.is_alive()]
            if not alive and disp.work_remaining() == 0:
                break
            time.sleep(2)
    except KeyboardInterrupt:
        disp.stop.set()

    for t in spark1.threads + (spark2.threads if spark2 else []):
        t.join(timeout=5)

    disp.persist()
    c = disp.counts
    print(f"\n=== done === converted {c['done']}, failed {c['failed']}, "
          f"already {c['already']}, skipped {c['skipped']}.")
    print(f"manifest: {args.manifest}")
    if c["failed"]:
        print("Re-run the same command to retry failed docs (resumable).")
    return 1 if c["failed"] else 0


# Dispatcher needs a work-remaining helper for the monitor / wait loop.
def _work_remaining(self):
    with self.lock:
        return len(self.big) + len(self.small)
Dispatcher.work_remaining = _work_remaining


if __name__ == "__main__":
    raise SystemExit(main())
