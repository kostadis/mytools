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
) -> None:
    """Run the agentic tagging loop until the worklist is drained."""
    from .runner import RunnerError, run as run_agent

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
def status(
    folder: Optional[str] = typer.Option(None, "--folder", help="Scope to a folder id."),
) -> None:
    """Show worklist progress and taxonomy counts."""
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

    typer.echo(f"Worklist (processable files): {len(worklist)}")
    typer.echo(f"Documents stored:             {len(docs)}")
    typer.echo(f"Processed:                    {processed}")
    typer.echo(f"Remaining:                    {remaining}")
    typer.echo(f"Categories:                   {len(categories)}")
    typer.echo(f"File-to-file links:           {link_count}")
    if categories:
        typer.echo("\nTop categories:")
        for c in sorted(categories, key=lambda c: c["member_count"], reverse=True)[:10]:
            typer.echo(f"  {c['member_count']:>4}  {c['name']}")


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
