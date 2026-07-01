"""drive-tagger command line interface."""

from __future__ import annotations

import shutil
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
    """Write DRIVE-TAGS.md, categories.json, and graph.json to reports/."""
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


if __name__ == "__main__":
    app()
