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
import urllib.error
import urllib.request
from collections import Counter, defaultdict, deque
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from batch_state import StateDB

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
# Canonical-file selection (dedup) — rpg-lib is the AUTHORITY, reached via its
# HTTP API (never the SQLite DB directly).
#
# rpg-lib computes is_old_version / is_draft / is_duplicate / is_printer_friendly
# for the same DriveThru tree and elects the latest version of each product.
# batch_convert POSTs the file list to /api/library/resolve and consumes those
# flags: Pass A drops old/draft/duplicate; Pass B keeps ONE file per product when
# rpg-lib left several current (same-version FORMAT variants — e.g. plain vs
# Quick Load — which it intentionally doesn't collapse), preferring the
# printer-friendly edition (rpg-lib's is_printer_friendly) for its cleaner text
# layer. Version dedup is NOT done here anymore — that's rpg-lib's job. Maps
# booklets, Pathfinder (-PF) editions, and Preview/Promo teasers are skipped as
# separate, non-target content.
# --------------------------------------------------------------------------

# Format / version tokens stripped from the grouping key so the same content in
# different exports/versions GROUPS together (winner selection no longer uses
# format or version ranking — that comes from rpg-lib's flags). The English-word
# tokens (pages/spreads/final/hd/sd) are word-bounded so they don't strip
# mid-word ("Rampage", "Shadowdale").
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
# Version token (v-prefixed OR bare multi-segment dotted) — stripped from the
# title key so version variants of one product share a group. Used by
# _variant_title_key ONLY (grouping); the latest-version decision is rpg-lib's.
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


class LibraryAPIError(RuntimeError):
    """rpg-lib API was unreachable or returned an error on a fresh pull."""


def resolve_flags_via_api(api_base: str, root: Path, docs: dict) -> dict:
    """POST the docs' absolute filepaths to rpg-lib's /api/library/resolve and
    map the per-file flags back to relpaths.

    Returns ``{rel: {is_old_version, is_duplicate, is_draft, is_printer_friendly}}``
    for files the library knows. Raises :class:`LibraryAPIError` if the API is
    unreachable or returns non-200 — the caller ERRORS OUT (no silent
    "convert everything" fallback). rpg-lib is the authority; we never touch its
    SQLite DB directly."""
    abs_to_rel = {os.path.normpath(str(root / rel)): rel for rel in docs}
    payload = json.dumps({"filepaths": list(abs_to_rel.keys())}).encode()
    url = api_base.rstrip("/") + "/api/library/resolve"
    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            if r.status != 200:
                raise LibraryAPIError(f"{url} -> HTTP {r.status}")
            body = json.loads(r.read())
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise LibraryAPIError(f"rpg-lib API unreachable at {url}: {e}") from e
    flags: dict[str, dict] = {}
    for abspath, fl in body.items():
        rel = abs_to_rel.get(os.path.normpath(abspath))
        if rel is not None:
            flags[rel] = fl
    print(f"[dedup] rpg-lib API matched {len(flags)}/{len(docs)} files")
    return flags


def select_canonical(docs: dict, flags: dict) -> dict:
    """Mark non-canonical docs status='skipped' with a reason. Two passes:
    (A) rpg-lib flags (old/duplicate/draft) + companion files; (B) when rpg-lib
    left several current files for one product (same-version FORMAT variants),
    keep the printer-friendly one and mark the rest `variant:superseded`.
    Mutates *docs*; returns per-reason counts.

    *flags* is ``{rel: {is_old_version, is_duplicate, is_draft,
    is_printer_friendly}}`` from rpg-lib. The latest-version decision is rpg-lib's
    (Pass A `library:old_version`); Pass B is a FORMAT tiebreak only — no version
    or format ranking is computed here."""
    counts: Counter[str] = Counter()

    def _skip(ent: dict, reason: str) -> None:
        ent["status"] = "skipped"
        ent["reason"] = reason
        counts[reason] += 1

    # Pass A — library flags (old/duplicate/draft) and companion files.
    for rel, ent in docs.items():
        if ent.get("status") == "skipped":
            continue
        fl = flags.get(rel, {})
        if fl.get("is_old_version"):
            _skip(ent, "library:old_version")
        elif fl.get("is_duplicate"):
            _skip(ent, "library:duplicate")
        elif fl.get("is_draft"):
            _skip(ent, "library:draft")
        elif (kind := _companion_kind(os.path.basename(rel))):
            _skip(ent, f"variant:{kind}")
        else:
            # Survivor — record rpg-lib's printer-friendly flag for the Pass B tiebreak.
            ent["is_pf"] = 1 if fl.get("is_printer_friendly") else 0

    # Pass B — collapse same-title format variants within a folder to one file.
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
            # max() picks the canonical: rpg-lib's printer-friendly edition
            # first, then richest/newest file, then shortest name.
            return (
                ent.get("is_pf", 0),
                ent.get("text_chars", 0),
                ent.get("pages", 0),
                ent.get("mtime", 0),
                -len(os.path.basename(rel)),
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


# Deterministic over-cap reasons -> the run-arg that, when raised, can fix them.
_CAP_REASONS = {"chunk_too_big:cap=": "chunk_token_cap",
                "prompt_too_big:cap=": "prompt_cap"}


def _stuck_under_caps(reason: str, args) -> bool:
    """True iff *reason* is a deterministic over-cap failure the current caps
    can't fix. Each such reason is tagged ``<kind>:cap=<N>`` with the cap value
    it tripped; if the current matching cap (--chunk-token-cap / --prompt-cap) is
    no larger, a verbatim re-run fails identically, so skip it. A current cap of
    0 disables that guard entirely (the chunk/doc would be sent this time), so
    never auto-skip then. Raising the cap above the tripped value re-queues it."""
    for prefix, arg_name in _CAP_REASONS.items():
        if reason.startswith(prefix):
            cur_cap = getattr(args, arg_name, 0)
            if cur_cap <= 0:
                return False
            try:
                tripped = int(reason.split("=", 1)[1])
            except (ValueError, IndexError):
                return True  # right kind, cap unparseable -> treat as stuck
            return cur_cap <= tripped
    return False


class Dispatcher:
    def __init__(self, args, docs: dict, root: Path, state=None):
        self.args = args
        self.docs = docs
        self.root = root
        self.state = state          # StateDB | None (None in unit tests)
        self.lock = threading.Lock()
        self.big: deque[str] = deque()    # spark1-only (oversized for small box)
        self.small: deque[str] = deque()  # fits the small box too
        self.stop = threading.Event()
        self.counts = {"done": 0, "failed": 0, "skipped": 0,
                       "already": 0, "total": 0,
                       "carried_failed": 0, "deferred": 0, "unfixable": 0}
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
            # Deterministic-failure filter: a doc the last run failed with an
            # over-cap reason (chunk_too_big / prompt_too_big) fails identically
            # on a verbatim re-run — the caps are uniform across boxes, so routing
            # won't help; only raising the matching cap will. Auto-skip it unless
            # the current cap is *higher* than the one it tripped (then it might
            # fit now) or --retry-too-big forces a re-attempt. Saves burning a doc
            # slot re-failing into the same wall every run.
            if (prior_status == "failed"
                    and not getattr(self.args, "retry_too_big", False)
                    and _stuck_under_caps(ent.get("reason", ""), self.args)):
                ent["status"] = "failed"           # carry the failure forward
                self.counts["unfixable"] += 1
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
        reason = "" if ok else self._failure_reason(log, last_exit)
        with self.lock:
            ent = self.docs[rel]
            ent.update(status="done" if ok else "failed", reason=reason,
                       endpoint=ep.name, attempts=attempts, exit=last_exit,
                       duration_s=dur, log=str(log))
            self.counts["done" if ok else "failed"] += 1
            done = self.counts["done"]
            failed = self.counts["failed"]
            total = self.counts["total"]
            if self.state:
                self.state.update_progress(
                    rel, status=ent["status"], reason=reason, endpoint=ep.name,
                    attempts=attempts, exit=last_exit, duration_s=dur,
                    log=str(log))
        flag = "OK " if ok else "FAIL"
        why = f" [{reason}]" if reason else ""
        print(f"[{time.strftime('%H:%M:%S')}] {flag} {done+failed}/{total} "
              f"({ep.name}, {dur}s, try {attempts}) {rel}{why}", flush=True)

    def _failure_reason(self, log: Path, last_exit: int | None) -> str:
        """Classify a doc failure into a machine-readable reason string.

        The key distinction is *deterministic* (a verbatim re-run fails the same
        way — pointless to retry until a cap is raised) vs *transient* (worth a
        retry). The two deterministic, cap-tagged reasons are:
          * ``chunk_too_big:cap=<N>`` — the per-chunk soft cap (exit 3 partial,
            log shows ``[chunk-too-big]``); fixed by raising --chunk-token-cap.
          * ``prompt_too_big:cap=<N>`` — the prompt HARD cap (exit 1, the whole
            doc aborts with no JSON); fixed by raising --prompt-cap (and a box
            whose context window accepts it).
        Tagging each with the cap it tripped lets enqueue re-queue it
        automatically once the relevant cap is raised. Transient reasons:
        ``timeout`` (read-timeout), ``interrupted`` (Ctrl-C / killed by signal,
        never a real failure), ``partial`` (some other exit-3), ``exit<N>``."""
        if last_exit == 124:
            return "timeout"
        if last_exit is not None and last_exit < 0:
            return "interrupted"          # killed by signal (e.g. SIGINT) — retry
        try:
            tail = log.read_text(errors="replace")[-20000:]
        except OSError:
            tail = ""
        if last_exit == 3:
            if "[chunk-too-big]" in tail:
                return f"chunk_too_big:cap={self.args.chunk_token_cap}"
            return "partial"
        if last_exit == 1 and "prompt cap; aborting" in tail:
            return f"prompt_too_big:cap={self.args.prompt_cap}"
        return f"exit{last_exit}"

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
    def persist(self):
        """Bulk-save the current plan (statuses + routing) to the state DB.
        Called after enqueue and at shutdown; per-doc progress is written
        incrementally by run_doc via state.update_progress."""
        if not self.state:
            return
        with self.lock:
            self.state.save_docs(self.docs)


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
    p.add_argument("--library-api", default="http://127.0.0.1:8000",
                   help="rpg-lib API base. On a fresh pull the docs' filepaths are "
                        "POSTed to /api/library/resolve for canonical/dedup flags "
                        "(old/draft/duplicate + printer-friendly). A fresh pull "
                        "ERRORS OUT if the API is unreachable (no convert-everything "
                        "fallback). rpg-lib is the authority — its SQLite DB is never "
                        "read directly.")
    p.add_argument("--no-dedup", action="store_true",
                   help="Disable canonical-file selection (no API call); convert every "
                        "content PDF (old versions, format variants, maps, etc.).")
    p.add_argument("--state-db", default=str(HERE / "dmsguild-state.db"),
                   help="SQLite state DB: the conversion plan + per-doc progress. "
                        "batch_convert writes it; batch_status reads it. Replaces the "
                        "old JSON manifest.")
    p.add_argument("--plan", choices=["ask", "fresh", "reuse"], default="ask",
                   help="On restart (state DB already populated): 'fresh' re-scans + "
                        "re-pulls rpg-lib flags + re-runs dedup (preserving done/failed "
                        "progress for unchanged docs); 'reuse' continues from the "
                        "existing DB with NO API call (works when rpg-lib is down); "
                        "'ask' prompts. Non-interactive runs with an existing DB MUST "
                        "pass fresh or reuse.")
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
    p.add_argument("--retry-too-big", action="store_true",
                   help="Re-queue docs the prior run failed over a cap "
                        "(chunk_too_big / prompt_too_big) even when the current "
                        "--chunk-token-cap / --prompt-cap is no larger than the one "
                        "they tripped. By default those are auto-skipped (a verbatim "
                        "re-run fails identically); raising the matching cap "
                        "re-queues them automatically, so this flag is only for "
                        "forcing a re-attempt at the same caps.")
    p.add_argument("--rescan", action="store_true",
                   help="Ignore cached scan entries and re-classify every PDF.")
    p.add_argument("--list", action="store_true",
                   help="Scan + classify + plan, write state DB + skiplist, then exit.")
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

    state = StateDB(args.state_db)
    legacy_manifest = HERE / "dmsguild-manifest.json"

    # Decide the startup mode. A populated state DB + restart -> ask the user
    # (or honor --plan). 'reuse' is the only path that works with rpg-lib down.
    if not state.exists_with_docs():
        mode = "fresh"
    elif args.rescan:
        mode = "fresh"
    else:
        mode = args.plan
        if mode == "ask":
            if not sys.stdin.isatty():
                sys.exit("error: state DB exists and this run is non-interactive; "
                         "pass --plan fresh or --plan reuse (cron/unattended must "
                         "not block on the restart prompt).")
            ans = input(f"State DB {args.state_db} exists. "
                        f"[f]resh pull from rpg-lib or [r]euse existing DB? "
                        ).strip().lower()
            mode = "fresh" if ans.startswith("f") else "reuse"

    # Canonical-file selection comes from rpg-lib via its HTTP API: Pass A drops
    # old/draft/duplicate; Pass B keeps the printer-friendly file when several
    # remain for one product. A fresh pull errors out if the API is down.
    dedup_counts = {}
    if mode == "reuse":
        print("[plan] reuse — loading existing state DB (no rpg-lib call, no rescan)")
        docs = state.load_docs()
    else:  # fresh
        prior = {} if args.rescan else state.load_docs()
        if not prior and not args.rescan and legacy_manifest.exists():
            try:  # one-time migration: keep the costly scan cache + prior progress
                prior = json.loads(legacy_manifest.read_text()).get("docs", {})
                print(f"[migrate] seeded scan cache from {legacy_manifest.name} "
                      f"({len(prior)} docs)")
            except Exception as e:  # noqa: BLE001
                print(f"[warn] could not read legacy manifest ({e})")
        docs = build_manifest(root, prior, args.scan_workers)
        state.save_docs(docs)  # persist scan cache BEFORE the API call
        if not args.no_dedup:
            try:
                flags = resolve_flags_via_api(args.library_api, root, docs)
            except LibraryAPIError as e:
                state.close()
                sys.exit(f"error: {e}\n"
                         f"(a fresh pull needs rpg-lib running; start it, or "
                         f"resume the existing plan with --plan reuse)")
            dedup_counts = select_canonical(docs, flags)
        state.save_docs(docs)
    state.set_meta(root=str(root), source=mode, api_base=args.library_api)

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

    disp = Dispatcher(args, docs, root, state=state)
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
    if disp.counts["unfixable"]:
        print(f"  skipped (cap-bound): {disp.counts['unfixable']}  "
              f"(prior chunk_too_big/prompt_too_big at >= current caps "
              f"--chunk-token-cap {args.chunk_token_cap} / --prompt-cap "
              f"{args.prompt_cap}; raise the matching cap or --retry-too-big)")
    print(f"  skipped (total)    : {n_skip}  -> {args.skiplist}"
          f"  (non-content + dedup)")
    if dedup_counts:
        total_dedup = sum(dedup_counts.values())
        print(f"  deduped (canonical): {total_dedup} files dropped as non-canonical")
        for reason in sorted(dedup_counts):
            print(f"      {reason}: {dedup_counts[reason]}")
    elif args.no_dedup:
        print("  deduped (canonical): disabled (--no-dedup)")
    elif mode == "reuse":
        print("  deduped (canonical): from existing state DB (reuse)")
    print(f"  state db           : {args.state_db}  (mode: {mode})")
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
        state.close()
        return 0
    if disp.counts["total"] == 0:
        print("Nothing to convert.")
        state.close()
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
    print(f"state db: {args.state_db}")
    if c["failed"]:
        print("Re-run the same command to retry failed docs (resumable).")
    state.close()
    return 1 if c["failed"] else 0


# Dispatcher needs a work-remaining helper for the monitor / wait loop.
def _work_remaining(self):
    with self.lock:
        return len(self.big) + len(self.small)
Dispatcher.work_remaining = _work_remaining


if __name__ == "__main__":
    raise SystemExit(main())
