# Batch review artifact — contract

Shared machinery for the five review skills (`vtt-spell-pass`, `scrub`,
`staged-consistency`, `voice-smooth`, `session-summary-consistency`). Not a skill:
no `SKILL.md`, so it stays out of the skill list. Each skill calls these two scripts.

**Why it exists.** Every one of those skills ends in a human adjudication loop
that runs one item at a time in the terminal — dozens to hundreds of blocking
round-trips per session. This lets the GM take the whole set in one page, at
their own pace, and hand the lot back in a single gesture.

The page is a direct port of **"Chapter 63 Rulings"**
(`claude.ai/code/artifact/e7370038-fb48-4755-bc47-129d18b0dd23`, 2026-08-19),
which ran a real `/staged-consistency` pass this way. Do not reauthor it.

---

## The loop

1. **Ask first.** Every run of every one of the five skills opens with an
   `AskUserQuestion`: *artifact (batch)* or *shell (one at a time)*. Shell is
   the existing behaviour and must stay byte-for-byte intact.
2. **Apply what needs no ruling.** Only genuine judgement calls become items.
   Everything mechanical is applied and named in the `footer`.
3. **Build and publish.** Name the files per **File names** below.
   ```bash
   python ~/.claude/skills/_shared/review-artifact/build_review.py \
       --in  $SCRATCH/review_items.json \
       --out $SCRATCH/review.html
   ```
   Then the `Artifact` tool on `$SCRATCH/review.html` with
   **`capabilities: {"artifact": {}}`** — without it the page cannot save and
   the GM gets the read-only fallback. Give it a stable `favicon` and a
   noun-phrase `title`.
4. **Stop.** Hand over the link and say nothing further. See **Pickup** below
   for how the save comes back — it is usually automatic, and it is never a poll.
5. **Read back.** `WebFetch` the artifact URL — it returns raw HTML for
   `claude.ai/code/artifact` URLs, and for a large page also writes it to a
   local file whose path it reports. Point the reader at that file:
   ```bash
   python ~/.claude/skills/_shared/review-artifact/read_decisions.py \
       --html <saved-artifact.html> --out $SCRATCH/decisions.json
   ```
6. **Apply** through the skill's own existing deterministic path. Never invent
   a second apply route.

**Redeploying to the same URL:** republish the same `file_path` in the same
conversation, or pass `url:` from another one. `staged-consistency` does this
once per stage.

### File names — one items file per page

`--in` and `--out` take any path and nothing is defaulted, so the names are a
convention, and it is the caller's to keep.

- **A run that publishes one page** uses the plain names: `review_items.json`,
  `review.html`, `decisions.json`. `session-summary-consistency`, `voice-smooth`
  and `vtt-spell-pass` are one-page runs.
- **A run that publishes more than one page** — `staged-consistency`, one page
  per stage; `scrub`, one page per file — suffixes the items file and the
  decisions file with that page's own key: `review_items_stage2.json`,
  `decisions_stage2.json`. **The `--out` html stays on one path for the whole
  run:** the artifact URL follows the `file_path`, so renaming it per page would
  claim a new URL and give up the single page the pattern is built on.

**Why the items file is the one that must not collide.** A multi-page run
republishes over its own page, so the wording of an earlier page — the question
the GM was actually asked, and the evidence shown beside it — survives only in
that page's items file; reuse one name and each page silently overwrites the
last. It is not recoverable from the applied diffs or the decisions, and it is
what the next run reads back out of `consistency_report_stage*.md`. (Phandalin
Ch 50, 2026-08-28: only stage 2's file survived; stages 0 and 1 were gone.)

---

## Pickup — how the save comes back

**Publishing arms a live subscription on the publishing session.** When the GM
presses Save, the page republishes itself, and an `artifact-changed`
task-notification naming that artifact arrives on its own. **That is the save
signal** — act on it, `WebFetch` the URL and read the decisions without waiting
to be told.

Two things it is not:

- **Not the GM speaking.** It means *the page was republished*, nothing more. It
  is never approval, never confirmation, and never an answer to a question you
  asked. The rulings come from the state block and nowhere else.
- **Not guaranteed.** The subscription arms in the background and can lag, and it
  only lives as long as the session that published. A GM who closes the terminal
  and comes back tomorrow just says they are done — same action, same read-back.

So the rule is: **publish, stop, and take whichever arrives first — the
notification, or the GM's word.** Never poll on a timer; the two routes cover
every case and a poll loop burns a turn per check for nothing.

**On republished pages** (`staged-consistency` publishes once per stage), every
republish re-arms the subscription, so a later notification names the same
artifact. Before treating one as a fresh set of rulings, check that the state's
`savedAt` is **newer than the one you already processed** — otherwise you will
re-apply a stage you have already applied.

---

## Input schema — `review_items.json`

```json
{ "title":   "Chapter 63 Rulings",
  "eyebrow": "Out of the Abyss · Chapter 63 · staged consistency",
  "lede":    "Ten decisions the audit cannot make for you. Everything else — about twenty mechanical corrections — needs no ruling and runs on your word.",
  "footer":  "Applied without asking: 20 mechanical corrections across 4 files. Ignored terms went to notes/.scrub_state.json.",
  "items": [
    { "id": "alkrist",
      "t":  "Alkrist is alive — “neutralized” was right all along",
      "y":  "Correct four canon lines that assert he died: <code>campaign_state.md:86</code>, <code>world_state.md:88</code>…",
      "n":  "Alkrist is dead. I fix “neutralized” → “dead” in gm-assist, session-summary and scene 03.",
      "ev": "Flagged by three separate checks. Supporting your side: the GM’s own tally counts him among “5 of these wizards are <em>out</em>”." }
  ] }
```

| key | required | notes |
|---|---|---|
| `title` | yes | Becomes `<title>`, the `<h1>`, and the artifact's gallery name. Short noun phrase. |
| `eyebrow` | no | Campaign · chapter · which skill. |
| `lede` | no | **Say how many need a ruling and that the rest already ran.** |
| `footer` | no | What was applied without asking, and which state file it went to. |
| `items[].id` | yes | `[A-Za-z0-9_.:-]{1,64}`, unique. Decisions are keyed by it, so it must survive back into your apply step — reuse the skill's own id (`find_residue.py`'s `c1`, a cluster/pair key, a finding number). |
| `items[].t` | yes | The decision as a sentence, not a category. |
| `items[].y` | yes | **What happens if approved. Name the files.** |
| `items[].n` | yes | **What happens if rejected. Name the files.** |
| `items[].ev` | no | The evidence. Cite `file:line`. |

`t` / `y` / `n` / `ev` are **rendered as HTML** — `<code>`, `<em>`, `<b>` are
yours to use. That also means any literal `<` or `&` in quoted transcript text
must be escaped by the caller. The builder refuses to emit a page containing
an unescaped `</script`.

### Why `y` and `n` are mandatory

One uniform verdict set has to work across five skills whose natural verdicts
differ. It only works because **each card states its own consequences** — the
buttons say Approve/Reject, but the card says what that means *here*. A card
without a concrete `y`/`n` is a card the GM has to guess at.

---

## Verdict semantics

| verdict | meaning |
|---|---|
| **Approve** | Do the thing described in `y`. |
| **Reject** | Do the thing described in `n`. |
| **Discuss** | Neither yet — the note carries the GM's instruction, or it comes back to chat. |

Plus a free-text **note** on any card (auto-revealed on Discuss).

**`Discuss all N`** is a deliberate escape hatch back to conversation. When it
is used, bring the discussed items back **as one grouped pass with their notes
attached** — never as a fresh one-at-a-time loop, which is the thing this
whole mechanism exists to avoid.

---

## Output — `decisions.json`

```json
{ "savedAt":  "2026-08-19 14:02 UTC",
  "decided":  10,
  "tally":    {"approve": 6, "discuss": 3, "reject": 1},
  "decisions":{"alkrist": "discuss", "manshoon": "reject"},
  "notes":    {"alkrist": "Alkrist is alive. What I meant was…"},
  "discuss":  ["alkrist", "keys"] }
```

`read_decisions.py` **exits 1 when `savedAt` is null.** That is deliberate: a
page the GM has not saved yet must never be read as *"approved nothing."*
Pass `--allow-unsaved` only to inspect a freshly built page.

Items the GM left unmarked simply do not appear in `decisions` — treat them as
undecided, not as rejected, and say so when you report back.

---

## Rules

- **Never poll.** Publish, hand over the link, stop — see **Pickup**.
- **Never auto-apply something you put on the page.** Anything that reaches
  the page is the GM's call by construction.
- **Shell mode is untouched.** Artifact mode is strictly additive.
- **Ids must round-trip.** If your apply step needs a line number or a file, put
  it in the id or keep a sidecar map — the page only returns ids.
- **One page, one skill, one run.** Do not collate two skills into one artifact.
- **One page, one items file.** A run that publishes more than one page names
  each page's items and decisions file for that page — see **File names**.
- **Read-only viewers.** The page already degrades: marks stay on screen, the
  copy says read-only, and it tells the GM to report picks in chat. If they do
  that, take it — do not insist on the artifact.

---

## Testing without a browser

```bash
python build_review.py --in fixture.json --out page.html
python read_decisions.py --html page.html            # must exit 1: never saved
# simulate a save: replace the #state block with a filled one, then
python read_decisions.py --html page_saved.html --out decisions.json
```

The generated page's JS can be extracted from the `#src` block and checked
with `node --check`.
