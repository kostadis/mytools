"""drive-tagger command line interface."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

import typer

from .config import CONFIG

app = typer.Typer(
    add_completion=False,
    help="Agentic, LLM-in-the-loop tagger for Google Drive.",
    no_args_is_help=True,
)


@app.command()
def check() -> None:
    """Test configured endpoints and API keys; exits 1 on any failure."""
    from . import health

    results = health.check_all()
    any_failed = False
    for r in results:
        mark = typer.style("✓", fg=typer.colors.GREEN) if r.ok else typer.style("✗", fg=typer.colors.RED)
        label = typer.style(r.name, bold=not r.ok)
        typer.echo(f"  {mark}  {label:<38} {r.detail}")
        if not r.ok:
            any_failed = True

    if any_failed:
        typer.secho("\nOne or more checks failed.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    typer.secho("\nAll checks passed.", fg=typer.colors.GREEN)


@app.command()
def scan(
    all_drives: bool = typer.Option(
        None, "--all-drives/--my-drive", help="Include shared drives (default from DT_ALL_DRIVES)."
    ),
) -> None:
    """List Drive files into data/scan.jsonl via gdrive-cli."""
    from . import gdrive

    CONFIG.ensure_dirs()
    use_all = CONFIG.all_drives if all_drives is None else all_drives
    typer.echo(f"Scanning Drive (all_drives={use_all}) ...")
    path = gdrive.scan(all_drives=use_all)
    count = sum(1 for _ in open(path, "r", encoding="utf-8"))
    typer.echo(f"Wrote {count} records to {path}")


@app.command()
def run(
    execute: bool = typer.Option(
        False, "--execute", help="Also write tags to Drive appProperties (default: dry-run)."
    ),
    folder: Optional[str] = typer.Option(
        None, "--folder", help="Restrict to direct children of this Drive folder id."
    ),
    max_batches: int = typer.Option(100, "--max-batches", help="Safety cap on agent batches."),
    max_files: Optional[int] = typer.Option(
        None, "--max-files", help="Max files processed this run (overrides DT_MAX_FILES)."
    ),
    provider: Optional[str] = typer.Option(
        None,
        "--provider",
        help="LLM backend: cursor (default), anthropic, openrouter, dgx (overrides DT_PROVIDER).",
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model",
        help="Model id for cursor/anthropic/openrouter (overrides DT_MODEL).",
    ),
    dgx_endpoint: Optional[str] = typer.Option(
        None,
        "--dgx-endpoint",
        help="DGX vLLM base URL (overrides DT_DGX_ENDPOINT).",
    ),
    shard: Optional[str] = typer.Option(
        None,
        "--shard",
        help="Worklist shard e.g. '0/2' (first half) or '1/2' (second half). Run one shard per machine for parallel processing (overrides DT_SHARD).",
    ),
) -> None:
    """Run the agentic tagging loop until the worklist is drained."""
    import os

    from .runner import RunnerError, run as run_agent

    if max_files is not None:
        os.environ["DT_MAX_FILES"] = str(max_files)
    if provider is not None:
        os.environ["DT_PROVIDER"] = provider
    if model is not None:
        os.environ["DT_MODEL"] = model
    if dgx_endpoint is not None:
        os.environ["DT_DGX_ENDPOINT"] = dgx_endpoint
    if shard is not None:
        os.environ["DT_SHARD"] = shard

    try:
        result = run_agent(execute=execute, folder_id=folder, max_batches=max_batches)
    except RunnerError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    typer.echo("")
    typer.echo(
        f"Run {result['status']}: processed {result.get('processed', 0)}, "
        f"remaining {result.get('remaining', 0)} over {result.get('batches', 0)} batch(es)."
    )
    if not execute:
        typer.echo("(dry-run: nothing written to Drive. Re-run with --execute to apply tags.)")


@app.command()
def pipeline(
    execute: bool = typer.Option(
        False, "--execute", help="Also write tags to Drive appProperties (default: dry-run)."
    ),
    folder: Optional[str] = typer.Option(
        None, "--folder", help="Restrict to descendants of this Drive folder id."
    ),
    max_files: Optional[int] = typer.Option(
        None,
        "--max-files",
        help="Stop after this many files (default: run until the worklist is drained).",
    ),
    workers: Optional[int] = typer.Option(
        None, "--workers", help="Concurrent workers (default DT_PIPELINE_WORKERS=4)."
    ),
    shard: Optional[str] = typer.Option(
        None,
        "--shard",
        help="Worklist shard e.g. '0/2' (overrides DT_SHARD).",
    ),
    dgx_endpoint: Optional[str] = typer.Option(
        None,
        "--dgx-endpoint",
        help="DGX vLLM base URL (overrides DT_DGX_ENDPOINT).",
    ),
) -> None:
    """Deterministic tagging pipeline: the harness drives, the LLM judges once per file."""
    import os

    from .pipeline import PipelineError, run_pipeline

    if shard is not None:
        os.environ["DT_SHARD"] = shard
    if dgx_endpoint is not None:
        # CONFIG was frozen at import; update both it and the env.
        os.environ["DT_DGX_ENDPOINT"] = dgx_endpoint
        CONFIG.dgx_endpoint = dgx_endpoint
    # The pipeline always talks to the DGX OpenAI-compat endpoint; make the
    # health preflight check that endpoint regardless of DT_PROVIDER.
    CONFIG.provider = "dgx"

    try:
        result = run_pipeline(
            execute=execute, folder_id=folder, max_files=max_files, workers=workers
        )
    except PipelineError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    typer.echo("")
    if result["status"] == "nothing_to_do":
        typer.echo("Nothing to do: worklist is fully processed.")
        return
    typer.echo(
        f"Pipeline done: processed {result['processed']}, "
        f"skipped {result['skipped']}, judge-failed {result['judge_failed']}, "
        f"errors {result['errors']}, remaining {result['remaining']}."
    )
    typer.echo(f"Elapsed {result['elapsed_s']}s ({result['files_per_min']} files/min).")
    if not execute:
        typer.echo("(dry-run: nothing written to Drive. Re-run with --execute to apply tags.)")


def _dgx_metrics(endpoint: str) -> dict:
    """Fetch key vLLM metrics from the Prometheus /metrics endpoint."""
    import urllib.request
    import urllib.error

    # endpoint is like http://host:port/v1 — metrics live at http://host:port/metrics
    base = endpoint.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    url = f"{base}/metrics"

    want = {
        "vllm:prompt_tokens_total",
        "vllm:generation_tokens_total",
        "vllm:avg_prompt_throughput_toks_per_s",
        "vllm:avg_generation_throughput_toks_per_s",
        "vllm:num_requests_running",
        "vllm:num_requests_waiting",
    }
    result: dict = {}
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            for line in resp.read().decode().splitlines():
                if line.startswith("#"):
                    continue
                name = line.split("{")[0].split(" ")[0]
                if name in want:
                    try:
                        result[name] = float(line.rsplit(" ", 1)[-1])
                    except ValueError:
                        pass
    except (urllib.error.URLError, OSError):
        pass
    return result


_RATE_WINDOW = 20  # number of recently-processed files used to compute rate


def _rate_and_eta(docs: list[dict], remaining: int) -> tuple[Optional[str], Optional[str]]:
    """Return (rate_str, eta_str) from processed_at timestamps, or (None, None)."""
    from datetime import datetime

    stamps = sorted(
        d["processed_at"] for d in docs if d.get("processed_at")
    )
    if len(stamps) < 2:
        return None, None

    window = stamps[-_RATE_WINDOW:]
    try:
        t0 = datetime.fromisoformat(window[0])
        t1 = datetime.fromisoformat(window[-1])
    except ValueError:
        return None, None

    elapsed_min = (t1 - t0).total_seconds() / 60.0
    if elapsed_min <= 0:
        return None, None

    files_in_window = len(window) - 1
    rate = files_in_window / elapsed_min  # files / min

    if rate >= 1:
        rate_str = f"{rate:.1f} files/min"
    else:
        rate_str = f"{rate * 60:.1f} files/hr"

    n_label = f"last {len(window)}"
    rate_display = f"{rate_str}  ({n_label})"

    eta_str: Optional[str] = None
    if rate > 0 and remaining > 0:
        eta_min = remaining / rate
        if eta_min < 90:
            eta_str = f"~{eta_min:.0f}m"
        elif eta_min < 60 * 36:
            eta_str = f"~{eta_min / 60:.1f}h"
        else:
            eta_str = f"~{eta_min / 60 / 24:.1f}d"

    return rate_display, eta_str


def _print_status(folder: Optional[str]) -> None:
    """Print one status snapshot to stdout."""
    from .config import CONFIG
    from .runner import _worklist_ids
    from .store import Store

    try:
        worklist = _worklist_ids(folder)
    except Exception as exc:  # noqa: BLE001
        typer.secho(str(exc), fg=typer.colors.YELLOW)
        worklist = []

    store = Store()
    try:
        docs = store.all_documents()
        processed = sum(1 for d in docs if d.get("processed"))
        categories = store.list_categories()
    finally:
        store.close()

    from .graph import Graph

    graph = Graph()
    try:
        link_count = graph.count()
    finally:
        graph.close()

    work_ids = set(worklist)
    done_ids = {d["id"] for d in docs if d.get("processed")}
    remaining = len(work_ids - done_ids)

    rate_str, eta_str = _rate_and_eta(docs, remaining)

    typer.echo(f"Provider:                     {CONFIG.provider} / embed:{CONFIG.embed_provider}")
    typer.echo(f"Worklist (processable files): {len(worklist)}")
    typer.echo(f"Documents stored:             {len(docs)}")
    typer.echo(f"Processed:                    {processed}")
    typer.echo(f"Remaining:                    {remaining}")
    if rate_str:
        typer.echo(f"Rate:                         {rate_str}")
        if eta_str:
            typer.echo(f"ETA:                          {eta_str}")
    else:
        typer.echo("Rate:                         (no timing data yet)")
    typer.echo(f"Categories:                   {len(categories)}")
    typer.echo(f"File-to-file links:           {link_count}")
    if categories:
        typer.echo("\nTop categories:")
        for c in sorted(categories, key=lambda c: c["member_count"], reverse=True)[:10]:
            typer.echo(f"  {c['member_count']:>4}  {c['name']}")

    if CONFIG.provider == "dgx":
        m = _dgx_metrics(CONFIG.dgx_endpoint)
        typer.echo(f"\nDGX ({CONFIG.dgx_endpoint}):")
        if m:
            prompt_tok = int(m.get("vllm:prompt_tokens_total", 0))
            gen_tok = int(m.get("vllm:generation_tokens_total", 0))
            total = prompt_tok + gen_tok or 1
            typer.echo(f"  Prompt tokens (prefill):  {prompt_tok:>10,}  ({100*prompt_tok//total}%)")
            typer.echo(f"  Generation tokens:        {gen_tok:>10,}  ({100*gen_tok//total}%)")
            typer.echo(
                f"  Prefill throughput:       {m.get('vllm:avg_prompt_throughput_toks_per_s', 0):>8.1f} t/s"
            )
            typer.echo(
                f"  Generation throughput:    {m.get('vllm:avg_generation_throughput_toks_per_s', 0):>8.1f} t/s"
            )
            typer.echo(
                f"  Requests running/waiting: "
                f"{int(m.get('vllm:num_requests_running', 0))} / "
                f"{int(m.get('vllm:num_requests_waiting', 0))}"
            )
        else:
            typer.secho("  (metrics endpoint unreachable)", fg=typer.colors.YELLOW)


@app.command()
def status(
    folder: Optional[str] = typer.Option(None, "--folder", help="Scope to a folder id."),
    watch: Optional[int] = typer.Option(
        None, "--watch", metavar="SECONDS", help="Refresh every N seconds (Ctrl-C to stop)."
    ),
) -> None:
    """Show worklist progress and taxonomy counts."""
    import time

    if watch is None:
        _print_status(folder)
        return

    try:
        while True:
            typer.echo("\033[2J\033[H", nl=False)  # clear screen
            _print_status(folder)
            typer.echo(f"\n(refreshing every {watch}s — Ctrl-C to stop)")
            time.sleep(watch)
    except KeyboardInterrupt:
        pass


@app.command()
def report() -> None:
    """Write reports/DRIVE-TAGS.md (index), reports/categories/*.md, categories.json, and graph.json."""
    from . import report as report_mod

    paths = report_mod.generate()
    typer.echo("Wrote:")
    for label, path in paths.items():
        typer.echo(f"  {label}: {path}")


@app.command()
def reset(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Delete the local vector DB and graph (does NOT touch Drive)."""
    if not yes:
        typer.confirm(
            f"Delete {CONFIG.db_dir} and {CONFIG.graph_db}? (Drive is untouched)",
            abort=True,
        )
    if CONFIG.db_dir.exists():
        shutil.rmtree(CONFIG.db_dir)
    if CONFIG.graph_db.exists():
        CONFIG.graph_db.unlink()
    typer.echo("Local state cleared.")


@app.command("retry-skipped")
def retry_skipped(
    reason: str = typer.Option(
        "gdrive-error",
        "--reason",
        "-r",
        help="Skip reason to clear (gdrive-error, extract-timeout, no-text, or 'all').",
    ),
) -> None:
    """Clear persisted skip records so files are retried on the next run.

    Use after fixing the underlying issue (e.g. refreshing the OAuth token
    clears gdrive-error skips so those files are attempted again).
    """
    from .graph import Graph

    graph = Graph()
    counts = graph.count_skipped()
    if not counts:
        typer.echo("No skipped files recorded.")
        return

    typer.echo("Current skip counts:")
    for r, n in sorted(counts.items()):
        typer.echo(f"  {r}: {n}")

    clear_reason = None if reason == "all" else reason
    deleted = graph.clear_skipped(clear_reason)
    label = reason if reason != "all" else "all reasons"
    typer.echo(f"Cleared {deleted} skip record(s) for {label}.")


consolidate_app = typer.Typer(
    add_completion=False,
    help="Post-run category consolidation: collect merge candidates, review, apply.",
)
app.add_typer(consolidate_app, name="consolidate")


@consolidate_app.command("collect")
def consolidate_collect(
    diagnostics: bool = typer.Option(
        False, "--diagnostics", help="Print pairwise nearest-neighbor category distances for threshold calibration."
    ),
    threshold: Optional[float] = typer.Option(
        None, "--threshold", help="Override DT_CONSOLIDATE_CLUSTER_THRESHOLD for this run only."
    ),
) -> None:
    """Cluster near-duplicate categories -> reports/consolidation/clusters.json."""
    from .consolidate import collect

    result = collect(threshold=threshold, diagnostics=diagnostics)
    typer.echo(f"\nWrote {result['path']}")
    typer.echo(
        f"{result['n_clusters']} multi-member cluster(s) ({result['n_absorbed']} categories), "
        f"{result['n_singletons']} singleton(s)."
    )


@consolidate_app.command("apply")
def consolidate_apply(
    decisions: Path = typer.Option(
        None,
        "--decisions",
        help="Path to decisions.json (default: reports/consolidation/decisions.json).",
    ),
) -> None:
    """Apply approved merge decisions to the store, then regenerate reports/."""
    from .consolidate import apply

    path = decisions or (CONFIG.consolidation_dir / "decisions.json")
    if not path.exists():
        typer.secho(f"No decisions file at {path}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    result = apply(path)
    typer.echo(f"Merged {len(result['merged'])} cluster(s); skipped {len(result['skipped'])}.")
    for m in result["merged"]:
        typer.echo(f"  -> {m['canonical']}  (absorbed: {', '.join(m['sources'])})")


backfill_app = typer.Typer(
    add_completion=False,
    help="Backfill LLM-drafted descriptions for empty-description categories (issue #98).",
)
consolidate_app.add_typer(backfill_app, name="backfill")


@backfill_app.command("draft")
def backfill_draft(
    out: Optional[Path] = typer.Option(
        None,
        "--out",
        help="Output path (default: reports/consolidation/description_backfill.json).",
    ),
) -> None:
    """Draft descriptions for empty-description multi-word categories.

    Read-only against the store — writes reports/consolidation/
    description_backfill.json for human review. Run `apply-descriptions`
    only after reviewing that file.
    """
    from .backfill import draft

    result = draft(out_path=out)
    typer.echo(f"\nWrote {result['path']}")
    typer.echo(
        f"Drafted {len(result['drafted'])} description(s). "
        "Review the file above before running apply-descriptions."
    )


@backfill_app.command("apply-descriptions")
def backfill_apply_descriptions(
    descriptions: Optional[Path] = typer.Option(
        None,
        "--descriptions",
        help="Path to the drafted descriptions artifact "
        "(default: reports/consolidation/description_backfill.json).",
    ),
) -> None:
    """Write human-reviewed drafted descriptions into the store."""
    from .backfill import apply_descriptions

    path = descriptions or (CONFIG.consolidation_dir / "description_backfill.json")
    if not path.exists():
        typer.secho(f"No descriptions file at {path}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    result = apply_descriptions(descriptions_path=path)
    typer.echo(f"Applied {len(result['applied'])} description(s); skipped {len(result['skipped'])}.")
    for a in result["applied"]:
        typer.echo(f"  -> {a['name']}")
    for s in result["skipped"]:
        typer.echo(f"  (skipped {s.get('name')}: {s.get('reason')})")


@consolidate_app.command("collect-links")
def consolidate_collect_links(
    threshold: Optional[float] = typer.Option(
        None, "--threshold", help="Override DT_RELATION_CLUSTER_THRESHOLD for this run only."
    ),
) -> None:
    """Group near-synonym link relations -> reports/consolidation/link_clusters.json."""
    from .link_consolidate import collect_relations

    result = collect_relations(threshold=threshold)
    typer.echo(f"\nWrote {result['path']}")
    typer.echo(
        f"{result['n_clusters']} relation family(ies) proposed from "
        f"{result['n_rogue_types']} rogue relation type(s) ({result['n_rogue_edges']} edges)."
    )


@consolidate_app.command("apply-links")
def consolidate_apply_links(
    decisions: Path = typer.Option(
        None,
        "--decisions",
        help="Path to link_decisions.json (default: reports/consolidation/link_decisions.json).",
    ),
) -> None:
    """Apply approved relation-merge decisions to the graph, then regenerate reports/."""
    from .link_consolidate import apply_relations

    path = decisions or (CONFIG.consolidation_dir / "link_decisions.json")
    if not path.exists():
        typer.secho(f"No decisions file at {path}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    result = apply_relations(path)
    typer.echo(f"Merged {len(result['merged'])} relation family(ies); skipped {len(result['skipped'])}.")
    for m in result["merged"]:
        typer.echo(
            f"  -> {m['canonical']}  (absorbed: {', '.join(m['sources'])}; "
            f"{m['rewritten']} rewritten, {m['deduped']} deduped)"
        )


if __name__ == "__main__":
    app()
