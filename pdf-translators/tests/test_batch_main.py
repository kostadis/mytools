"""main() startup-flow guards: API-down error-out and the non-interactive
restart-prompt guard. Both exit before any scan/dispatch, so no PDFs or
endpoints are needed."""
import pytest

import batch.batch_convert as bc
import lib.batch_state as bs


def _argv(tmp_path, root, *extra):
    return [
        "--root", str(root),
        "--state-db", str(tmp_path / "s.db"),
        "--logdir", str(tmp_path / "logs"),
        "--skiplist", str(tmp_path / "skip.tsv"),
        *extra,
    ]


def test_fresh_pull_errors_out_when_api_down(tmp_path):
    """Fresh pull + unreachable rpg-lib API -> SystemExit (no convert-all fallback)."""
    root = tmp_path / "pdfs"
    root.mkdir()  # empty: build_manifest returns {}, then the API call fails
    argv = _argv(tmp_path, root, "--library-api", "http://127.0.0.1:1")
    with pytest.raises(SystemExit):
        bc.main(argv)


def test_non_interactive_ask_exits(tmp_path, monkeypatch):
    """Existing state DB + --plan ask + non-TTY stdin -> SystemExit (never blocks)."""
    db = bs.StateDB(str(tmp_path / "s.db"))
    db.save_docs({"a.pdf": {"status": "pending"}})
    db.close()
    root = tmp_path / "pdfs"
    root.mkdir()
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    argv = _argv(tmp_path, root, "--plan", "ask")
    with pytest.raises(SystemExit):
        bc.main(argv)


def test_reuse_makes_no_api_call(tmp_path, monkeypatch):
    """--plan reuse loads the state DB and never calls the API (works API-down)."""
    db = bs.StateDB(str(tmp_path / "s.db"))
    # one already-skipped doc so there's nothing to convert -> main returns cleanly
    db.save_docs({"x.pdf": {"status": "skipped", "reason": "library:old_version"}})
    db.close()
    root = tmp_path / "pdfs"
    root.mkdir()

    def boom(*a, **k):
        raise AssertionError("reuse must not call the rpg-lib API")
    monkeypatch.setattr(bc, "resolve_flags_via_api", boom)

    # spark endpoints unreachable, but total==0 (only a skipped doc) -> early return
    rc = bc.main(_argv(tmp_path, root, "--plan", "reuse", "--spark2", ""))
    assert rc == 0
