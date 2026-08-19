# Batch review artifact — contract

Shared machinery for the four review skills (`vtt-spell-pass`, `scrub`,
`staged-consistency`, `voice-smooth`). Not a skill: no `SKILL.md`, so it stays
out of the skill list. Each skill calls these two scripts.

**Why it exists.** Every one of those skills ends in a human adjudication loop
that runs one item at a time in the terminal — dozens to hundreds of blocking
round-trips per session. This lets the GM take the whole set in one page, at
their own pace, and hand the lot back in a single gesture.

The page is a direct port of **"Chapter 63 Rulings"**
(`claude.ai/code/artifact/e7370038-fb48-4755-bc47-129d18b0dd23`, 2026-08-19),
which ran a real `/staged-consistency` pass this way. Do not reauthor it.

---

## The loop

1. **Ask first.** Every run of every one of the four skills opens with an
   `AskUserQuestion`: *artifact (batch)* or *shell (one at a time)*. Shell is
   the existing behaviour and must stay byte-for-byte intact.
2. **Apply what needs no ruling.** Only genuine judgement calls become items.
   Everything mechanical is applied and named in the `footer`.
3. **Build and publish.**
   ```bash
   python ~/.claude/skills/_shared/review-artifact/build_review.py \
       --in  $SCRATCH/review_items.json \
       --out $SCRATCH/review.html
   ```
   Then the `Artifact` tool on `$SCRATCH/review.html` with
   **`capabilities: {"artifact": {}}`** — without it the page cannot save and
   the GM gets the read-only fallback. Give it a stable `favicon` and a
   noun-phrase `title`.
4. **Stop.** Hand over the link and say nothing further. **Do not poll.** The
   GM marks the page, presses **Save decisions**, and tells you in chat.
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

One uniform verdict set has to work across four skills whose natural verdicts
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

- **Never poll.** Publish, hand over the link, stop.
- **Never auto-apply something you put on the page.** Anything that reaches
  the page is the GM's call by construction.
- **Shell mode is untouched.** Artifact mode is strictly additive.
- **Ids must round-trip.** If your apply step needs a line number or a file, put
  it in the id or keep a sidecar map — the page only returns ids.
- **One page, one skill, one run.** Do not collate two skills into one artifact.
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
