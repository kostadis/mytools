# Batch review page contract

Shared machinery for Codex skills that need human adjudication of many findings.
This directory is not a skill and intentionally has no `SKILL.md`.

## Workflow

1. Ask whether the user wants batch review or the skill's existing interactive flow.
2. Apply only changes that do not require a ruling. Put those changes in `footer`.
3. Write one shared-schema JSON file and build a standalone page:

   ```bash
   REVIEW_PAGE="${CODEX_HOME:-$HOME/.codex}/skills/_shared/review-page"
   python "$REVIEW_PAGE/build_review.py" --in review_items.json --out review.html
   ```

4. Prefer serving the page from the Codex VM when it is reachable from the
   user's phone over Tailscale:

   ```bash
   python "$REVIEW_PAGE/serve_review.py" \
     --page review.html --items review_items.json --out decisions.json
   ```

   Give the user the capability URL printed by the server and keep the process
   running. **Save to VM** validates and atomically writes the configured
   decisions file in the session directory. The random URL is intended for a
   tailnet or trusted LAN and changes every time the server starts.

   If the VM cannot be reached, give the user the page path instead. A page
   opened directly retains **Copy output** and the **Save output** download.
5. Validate the returned JSON (pasted into a file, or the download) against the
   items file the page was built from:

   ```bash
   python "$REVIEW_PAGE/read_decisions.py" --in decisions.json --items review_items.json
   ```

   It exits 1 on an export with no `savedAt`, and 2 on a note for an id the page
   never asked about or an export whose items differ from `--items` (a stale
   export from an earlier run).

6. Apply approved decisions through the calling skill's existing deterministic
   path. The page itself never edits source files.

## Input schema

```json
{
  "title": "Chapter 63 Rulings",
  "reviewId": "staged-consistency:chapter-63:stage-1",
  "outputName": "staged_consistency_stage_1_decisions.json",
  "eyebrow": "Out of the Abyss / Chapter 63 / staged consistency",
  "lede": "Ten decisions need a ruling. Mechanical corrections are already applied.",
  "footer": "Applied without asking: 20 mechanical corrections across 4 files.",
  "items": [
    {
      "id": "alkrist",
      "t": "Alkrist is alive; the recap says he died",
      "y": "Correct the cited recap and scene files.",
      "n": "Leave the cited files unchanged and defer the finding.",
      "ev": "The GM tally in <code>notes/session.md:84</code> says he is out."
    }
  ]
}
```

Required top-level keys are `title` and non-empty `items`. Optional keys are
`reviewId`, `outputName`, `eyebrow`, `lede`, and `footer`. **Never pre-fill a
verdict:** the builder rejects a `state` carrying `decisions`, `notes` or
`savedAt`, because a pre-set verdict would be exported as the GM's ruling on a
single click. Put a recommendation, or a decision recorded earlier, in the
card's `y` or `ev` text instead.

Each item requires:

- `id`: unique, stable, 1-64 characters from `[A-Za-z0-9_.:-]`.
- `t`: the decision as a sentence.
- `y`: the concrete consequence of Approve, including affected files.
- `n`: the concrete consequence of Reject, including affected files.
- `ev`: optional evidence with `file:line` citations.

`t`, `y`, `n`, and `ev` are trusted HTML. Callers must escape transcript text,
especially `<`, `>`, and `&`. The builder rejects an embedded `</script>`.

## Output schema

```json
{
  "schemaVersion": 1,
  "reviewId": "staged-consistency:chapter-63:stage-1",
  "savedAt": "2026-08-26 20:15 UTC",
  "decided": 10,
  "tally": {"approve": 6, "reject": 1, "discuss": 3},
  "decisions": {"alkrist": "discuss", "manshoon": "reject"},
  "notes": {"alkrist": "Treat this NPC as alive."},
  "discuss": ["alkrist"],
  "unmarked": ["keys"]
}
```

Verdicts are `approve`, `reject`, and `discuss`. Unmarked IDs are unresolved,
not rejected.

`savedAt` is stamped only by the GM's own **Copy output**, **Save output**, or
**Save to VM** gesture, never when the page loads or renders, so a JSON without
it is not a ruling. Before treating a second export in the same run as new
rulings, check its `savedAt` is newer than the one already processed.

The copy and save controls stay disabled until the GM has marked or noted at
least one item, so an all-unmarked export can never pass for a review.

The page keeps no browser storage. It always opens from the builder's state,
so a re-review never starts with a previous run's marks already ticked, and
reloading a page mid-review loses unsaved marks. Discussed items return to chat as one grouped pass with notes.

## Where the files live

Every review skill keeps its items, page and decisions files in the **session
directory**, under `<session>/<skill>_review/` (`quote_review/`,
`spell_review/`, `staged_review/`, `voice_review/`, `voice_critic_review/`, or
`dialogue_edit/session-*/`), never in scratch: the question the GM was asked
and the ruling they gave belong with the session they rule on. Transcripts and
cleaned output keep their own rules.

## File names when a run publishes more than one page

A run that publishes one page uses plain names: `review_items.json`,
`review.html`, `decisions.json`. A run that publishes more than one page —
`staged-consistency`, one page per stage — gives **each page its own items,
page and decisions files**: `review_items_stage<N>.json`, `review_stage<N>.html`,
`decisions_stage<N>.json`. Reusing one `review_items.json` overwrites the earlier
page's cards, and those cards are the only record of the question the GM was
actually asked; the applied diffs and the decisions cannot reconstruct them.
Give each page its own `reviewId` too (e.g. `…:stage-1`), so `read_decisions.py
--items` can tell the pages apart.

## Rules

- One item is one consent unit. Never imply approval across several findings.
- Never auto-apply an item that reached the page.
- Keep the skill's interactive mode intact; batch mode is additive.
- IDs must round-trip to the calling skill's apply data or a sidecar map.
- One page covers one skill and one run. `staged-consistency` uses one page per stage.
- The page existing, being opened, or having a newer mtime is never approval.
- Only pasted or saved decision JSON authorizes follow-up work. An HTTP success
  from `serve_review.py` is a save: the same validator used by the CLI has
  accepted the payload and written it to the configured path. Merely loading
  the URL is not a decision.

## Phone review over Tailscale

`serve_review.py` binds to `0.0.0.0:8765` by default and prints the machine's
Tailscale IPv4 address when the `tailscale` CLI is available. It serves one
HTML file at an unguessable `/r/<token>/` URL and accepts `PUT` only at that
URL's `decisions` endpoint. It does not expose a directory listing, arbitrary
file reads, or a caller-selected write path.

The server must remain in the foreground while the page is in use. Stop it
after the decisions file has been saved and validated. Use `--port` when 8765
is occupied, and `--host 127.0.0.1` for local-only testing.

The server is stdlib-only. It is designed for a private tailnet or trusted LAN;
do not expose its port to the public internet. The capability URL prevents
ambient tailnet clients from discovering the review, while Tailscale supplies
the network identity and encryption.

## Testing without a browser

```bash
python build_review.py --in fixture.json --out page.html      # builds; no export yet
python read_decisions.py --in never.json                       # {"decisions":{}} -> exit 1: no savedAt
# Simulate the GM's export by hand, then validate it against the items file:
cat > export.json <<'JSON'
{"schemaVersion": 1, "reviewId": "<fixture reviewId>", "savedAt": "2026-01-01 00:00 UTC",
 "decisions": {"c1": "approve"}, "notes": {}, "unmarked": ["c2"]}
JSON
python read_decisions.py --in export.json --items fixture.json   # exit 0
```

It must also exit 2 for a note on an id the fixture never asked about, an id
both decided and unmarked, and an `--items` file whose ids differ (a stale
export). A fixture whose `state` pre-fills `decisions`, `notes` or `savedAt`
must be refused by the builder.
