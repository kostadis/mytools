# Contract — Notes File Markdown Output

**Feature**: 003-post-capture-notes
**Produced by**: the LLM render call in `src/notetaker/notes/render.py`
**Path**: `<cache-root>/<url-hash>/notes/notes.md` (filename overridable
via `notes.notes_filename` config)

The notes file is the user-facing output. Its structure is *prompted*, not
strictly validated — the LLM render is the only step in this feature with
non-deterministic output. The file is intended for human review and
editing.

---

## Required properties (validated programmatically)

1. **Non-empty**: the file is at least 200 bytes (a sanity floor; renders
   far below this are LLM failure modes).
2. **Starts with a level-1 heading**: the first non-blank line begins with
   `# `.
3. **Valid UTF-8**: the file is decodable as UTF-8 without errors.
4. **No trailing prompt artifacts**: the file does not contain the literal
   strings `Working doc follows.` or `---` as the very last line (these
   would indicate the model echoed the prompt scaffold).
5. **Newline-terminated**: ends with exactly one `\n`.

---

## Expected (prompted) sections

These are described in the render prompt and are expected outputs. They are
NOT enforced by automated validation, because the LLM may legitimately
re-organise for short or unusual meetings.

- Meeting overview: a short paragraph naming the meeting's purpose.
- Speakers: named participants taken from the transcript.
- Per-topic narrative sections: slide titles used as section headings when
  topical match is clear, otherwise headings the model writes.
- Decisions with attribution.
- Action items / follow-ups.
- Open questions / unresolved disagreements.
- (Optional) "Slides shown but not discussed": closing list when slides
  were on-screen but never talked about.

---

## Behaviour around the notes file

- **Default path**: `<cache-root>/<url-hash>/notes/notes.md`.
- **Overwrite**: refused unless `--force` (FR-014). Refusal exits non-zero
  with a message naming the existing path.
- **Retention**: subject to `notes.retention_days` (default 365 days). Not
  governed by the existing `[cache] retention_days` knob.
- **On render failure**: NOT written. The working doc remains in place so
  the user can re-invoke (FR-017).

---

## Test coverage required

Unit tests in `tests/unit/test_notes_render.py` (mocked LLM):

1. The mocked client returns a fixture string; the renderer writes it to
   the configured `notes_filename` path verbatim.
2. The required properties (1)–(5) above are checked by an
   `assert_notes_file_valid()` helper used by every render test.
3. Refusal-on-existing: re-invoking without `--force` raises and does not
   touch the existing file.
4. `--force`: overwrites the existing file with the new content.
5. Render failure: the mocked client raises a transient error; the renderer
   retries per `[api] retry_count`; on persistent failure no notes file is
   written and the working doc is untouched.
