# Quickstart: Verify the Removal Worked

A 60-second walkthrough for a reviewer who wants to confirm spec 004
landed correctly. Assumes the reviewer has the project installed in a
working virtualenv and a typical user cache from a prior run.

## 1. Help text — `synthesise` is gone

```bash
notetaker --help
```

Expect: subcommand list contains `capture`, `extract`, `understand`,
`notes`, `run`. Does NOT contain `synthesise`. Total subcommand count: 5.

```bash
notetaker synthesise "https://zoom.us/rec/share/example"
```

Expect: typer/click prints "no such command 'synthesise'" (or similar)
and exits non-zero.

## 2. `notetaker run` stops at understanding

```bash
notetaker run "https://zoom.us/rec/share/example"
```

Expect (interactively, with a real recording or a mocked one):
- Capture, extraction, and understanding stages execute as before.
- The cache directory `<cache>/<hash>/` is populated with `capture/`,
  `extraction/`, and `understanding/` subdirectories.
- NO `<cache>/<hash>/synthesis/` subdirectory is created.
- The final two lines of console output name the cache directory and
  the next-step command, in the form documented in
  `contracts/cli-surface.md`.

```bash
notetaker run --help
```

Expect: the description does NOT mention "synthesis" or "summary"; it
names only the three chained stages.

## 3. The `[synthesis]` config section is gone but old configs still load

```bash
grep -i 'synthes\|summary_model' config.toml
```

Expect: empty output.

```bash
# Simulate an old user config:
mkdir -p /tmp/quickstart-cfg
cat > /tmp/quickstart-cfg/config.toml <<'EOF'
[synthesis]
summary_model = "claude-opus-4-1"
EOF
NOTETAKER_CONFIG=/tmp/quickstart-cfg/config.toml notetaker --help
```

Expect: the help text still prints, no warning about the unknown
`[synthesis]` section, exit code 0.

## 4. The default model is preserved

```bash
python -c "from notetaker.config import load_config; print(load_config().resolved_notes_model())"
```

Expect: `claude-sonnet-4-6` (matches what the same command printed
before this feature).

## 5. The codebase is clean

```bash
grep -ri 'stages\.synthesis\|notetaker synthesise\|synthesis\.summary_model' \
  src/ tests/ HOWTO.md CLAUDE.md config.toml pyproject.toml
```

Expect: empty output.

```bash
ls src/notetaker/stages/
```

Expect: `capture`, `extraction`, `understanding` (no `synthesis`).

```bash
ls src/notetaker/contracts/
```

Expect: no `summary.py`, no `aligned_segments.py`. The remaining
contracts are `transcript.py`, `slide_timeline.py`, `slide_content.py`,
`frames_manifest.py`, `log_record.py`.

## 6. Tests stay green

```bash
pytest -q
```

Expect: all collected tests pass. The collected count is reduced by
exactly the number of tests removed under FR-009 (the two deleted test
files: `tests/unit/test_aligner.py` and
`tests/contract/test_aligned_segments_contract.py`). No previously-green
non-`live_api` test goes red.

```bash
pytest tests/integration/test_full_pipeline.py -q
```

Expect: passes. The end-to-end golden fixture test now mocks the notes
LLM call and asserts on the notes file rather than the synthesis
summary.

## 7. The constitution and the code agree

```bash
grep -E '^\*\*Version\*\*:' .specify/memory/constitution.md
```

Expect: `**Version**: 1.1.0 | ...`.

```bash
grep -i 'Synthesis\|Aligned Segment\|Final Summary' .specify/memory/constitution.md
```

Expect: matches only inside the SYNC IMPACT REPORT comment block at the
top of the file — no matches in the normative Article text.

## 8. Existing user caches are not broken

```bash
# Find a cache entry that still has a synthesis/ subdirectory:
ls ~/.local/share/notetaker/cache/*/synthesis/ 2>/dev/null | head
```

If you have one, run any current subcommand against the same URL:

```bash
notetaker notes "<url>" /tmp/some-transcript.txt
```

Expect: succeeds (or fails with a normal notes-path error if your
inputs aren't right). Does NOT crash on the orphan `synthesis/` files.
Does NOT print a deprecation warning.
