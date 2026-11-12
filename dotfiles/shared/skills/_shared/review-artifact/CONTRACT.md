# Batch review page — contract

One kit for both agents, at `dotfiles/shared/skills/_shared/review-artifact/`.
It is linked as `~/.claude/skills/_shared/review-artifact` and
`~/.codex/skills/_shared/review-artifact`. Claude builds the page with the
default `--save artifact`; Codex builds it with `--save local`. The card
schema, the verdicts and the decisions file are the same for both; only the
save transport differs (see **Save transports**).

Shared machinery for the review skills that publish a review page:
`dialogue-edit`, `session-summary-consistency`, `speaker-attribution-text`,
`staged-consistency`, `voice-smooth` and `vtt-spell-pass`. (`scrub` does not:
its Phase 2 is a shell-side batch sheet.) Not a skill:
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

1. **Ask first.** The GM chooses *artifact (batch)* or *shell (one at a time)*
   with an explicit `AskUserQuestion` — at the start of the run in
   `staged-consistency`, `session-summary-consistency` and `vtt-spell-pass`, and
   once the queue is long enough to need it in `voice-smooth`. Never default to
   the page. Shell is the existing behaviour and must stay intact.
2. **Apply what needs no ruling.** Only genuine judgement calls become items.
   Everything mechanical is applied and named in the `footer`.
3. **Build and publish.** Name the files per **File names** below.
   ```bash
   python ~/.claude/skills/_shared/review-artifact/build_review.py \
       --in  <session>/<skill>_review/review_items.json \
       --out <session>/<skill>_review/review.html
   ```
   (Codex builds with `--save local` instead: see **Save transports**.)
   Then the `Artifact` tool on that `review.html` with
   **`capabilities: {"artifact": {}}`** — without it the page cannot save and
   the GM gets the read-only fallback. Give it a stable `favicon` and a
   noun-phrase `title`.
4. **Stop.** Hand over the link and say nothing further. See **Pickup** below
   for how the save comes back — it is usually automatic, and it is never a poll.
5. **Read back.** Use the `Artifact` tool, not `WebFetch`: `action: "read"`
   with the artifact `url` and `path: "index.html"`. It saves the live page
   (with the GM's saved state block) to a local file and reports the path; a
   read without `path` returns the HTML inline, which is fine for a small page.
   The Artifact tool's own guidance says to read claude.ai artifact links this
   way, and it is the route that worked on OOTA ch02 (2026-09-25). Point the
   reader at the saved file:
   ```bash
   python ~/.claude/skills/_shared/review-artifact/read_decisions.py \
       --html <saved-artifact.html> --items <session>/<skill>_review/review_items.json \
       --out <session>/<skill>_review/decisions.json
   ```
   Pass the same items file the page was built from: the reader exits 2 if the
   page's items differ, which is how a stale page from an earlier run gets caught.
6. **Apply** through the skill's own existing deterministic path. Never invent
   a second apply route.

**Redeploying to the same URL:** republish the same `file_path` in the same
conversation, or pass `url:` from another one. `staged-consistency` does this
once per stage.

### Where the files live

Every review skill keeps its items, page and decisions files in the **session
directory**, under `<session>/<skill>_review/` (`quote_review/`,
`spell_review/`, `staged_review/`, `voice_review/`, `voice_critic_review/`, or
`dialogue_edit/session-*/`), never in scratch: the question the GM was asked
and the ruling they gave belong with the session they rule on. Transcripts and
cleaned output keep their own rules.

### File names — one items file per page

`--in` and `--out` take any path and nothing is defaulted, so the names are a
convention, and it is the caller's to keep.

- **A run that publishes one page** uses the plain names: `review_items.json`,
  `review.html`, `decisions.json`. `session-summary-consistency` and
  `vtt-spell-pass` are one-page runs.
- **A run that publishes more than one page** — `staged-consistency`, one page
  per stage; `voice-smooth`, one page per review round — suffixes the items file and the
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

## Save transports

`build_review.py --save artifact|local` picks how the GM's marks leave the
page. Everything else on the page is identical. Artifact output is
byte-identical to what the builder produced before `--save` existed, and a
test holds it to that.

| | `--save artifact` (default) | `--save local` |
|---|---|---|
| Used by | Claude | Codex |
| Save | **Save decisions** republishes the page itself with the state embedded in `<script type="application/json" id="state">` (`window.claude.use('artifact')`) | **Copy output**, **Save output** (a download named by the spec's `outputName`, default `decisions.json`), and **Save to VM** |
| Read back | `read_decisions.py --html SAVED.html` | `read_decisions.py --in decisions.json` |
| Needs | the `Artifact` tool with `capabilities: {"artifact": {}}` | nothing: it opens from `file://` and loads no web font |

`--save local` details:

- **Save to VM** appears when `<meta name="codex-review-save" content="enabled">`
  is in the page (`serve_review.py` injects it) and does `PUT ./decisions`.
  Without the meta, the same button is **Save output**, a download.
- Copy output and Save output stay disabled until the GM has marked or noted
  something, so an all-unmarked export cannot pass for a review.
- The export always lists every item in `decisions` or `unmarked`, plus the
  `reviewId` and a `savedAt` stamped by the GM's own gesture. `picks` is added
  when the page has any pick card, and `extraVerdicts` (the declared keys) when
  it has any extra verdict.
- The page keeps no browser storage: a reload loses unsaved marks and a
  re-review never opens with an earlier run's marks ticked.
- The default `reviewId` is the slugged title, capped at 128 (reproducible, so
  `read_decisions.py --in --items` can check it). The artifact default also
  appends the build time. A `reviewId` is 1-128 chars of `[A-Za-z0-9_.:@-]`; to
  put a path or a name with a space in one, derive it with `review_ids.py`
  (`derive_review_id`): the text itself when valid, else a slug plus a short hash
  of the original, so the same text always gives the same id.
- `serve_review.py` validates a Save to VM payload with the same `normalize()`
  as `read_decisions.py --in`. With the items file it accepts approve, reject,
  discuss, the items file's declared `extraVerdicts` and, on a card that offered
  picks, `pick` with one of the offered words (returned as `picks`). Without
  `--items` it can only trust the export's own `extraVerdicts` / `picks`.

The `--in` reader exits 1 on an export with no `savedAt` and 2 on a note for an
id the page never asked about, an id both decided and unmarked, or an export
whose items differ from `--items` (a stale export from an earlier run).

---

## Pickup — how the save comes back

**Publishing arms a live subscription on the publishing session.** When the GM
presses Save, the page republishes itself, and an `artifact-changed`
task-notification naming that artifact arrives on its own. **That is the save
signal** — act on it, read the page back (step 5) and read the decisions without waiting
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
| `outputName` | no | `--save local` only: the download's file name, 1-128 chars of `[A-Za-z0-9_.-]`, default `decisions.json`. |
| `reviewId` | no | Identifies this page's run, e.g. `ch63:stage-1`. Default: the title plus the build time (UTC). It is saved with the decisions, and `read_decisions.py --items` refuses a page whose `reviewId` differs from the items file's. |
| `lede` | no | **Say how many need a ruling and that the rest already ran.** |
| `footer` | no | What was applied without asking, and which state file it went to. |
| `items[].id` | yes | `[A-Za-z0-9_.:-]{1,64}`, unique. Decisions are keyed by it, so it must survive back into your apply step — reuse the skill's own id (`find_residue.py`'s `c1`, a cluster/pair key, a finding number). |
| `items[].t` | yes | The decision as a sentence, not a category. |
| `items[].y` | yes | **What happens if approved. Name the files.** |
| `items[].n` | yes | **What happens if rejected. Name the files.** |
| `items[].ev` | no | The evidence. Cite `file:line`. |
| `items[].edit` | no | **The proposed edit, shown first on the card in bold at reading size**: the exact before → after text. When absent, the builder lifts the `<b>Exact edits:</b>` tail out of `y` into it. `t` then shows below it as the rationale ("Why"). GM feedback 2026-10-19: the edit was the hardest thing to read when it sat in small type under a large headline. |
| `items[].guess` | no | Your best guess at the verdict (`approve`, `reject`, `discuss` or an extra verdict key). Shown in a highlighted box above the buttons and marked "my guess" on its button. **Give one on every card where you are not confident** (GM 2026-10-19: "if there is non confidence in a choice, I want your guess as an option"). It is display only: it is never a pre-filled verdict and is never exported. |
| `items[].guessWhy` | no | One or two sentences of why, shown with the guess. |
| `extraVerdicts` | no | Extra buttons beyond Approve / Reject / Discuss, for a skill whose natural verdicts are more than two, e.g. `[{"key":"chatter","label":"Table chatter","outcome":"Saved as ignored in <code>…state.json</code>."}]`. `key` is 1-24 chars `[a-z_]`; `outcome` is the default text of the card's extra outcome box. Declare only verdicts the skill's apply step maps to an action. |
| `items[].picks` | no | 1-12 distinct words or phrases shown as **clickable buttons** under "Or change to" (label override: `items[].picksLabel`). Use it whenever the GM is choosing a replacement — dictionary suggestions, spelling variants — so they click the word and never type it (GM 2026-11-06). A click saves verdict `pick`, and `read_decisions.py` exports the word in `picks[id]`, refusing any word the card did not offer. Approve still means the card's own proposed `edit`. |
| `items[].guessPick` | no | Which of `picks` you would choose; marked "my guess" on that button. Display only, like `guess`. |
| `items[].x` | no | Per-card override of an extra verdict's outcome text: `{"chatter": "…"}`. |

**Never pre-fill a verdict.** A page always starts unmarked and unsaved: the
builder rejects a spec whose `state` carries `decisions`, `notes` or `savedAt`.
A pre-set verdict would be exported as the GM's ruling on a single Save. Put
your recommendation in the card's `guess` and `guessWhy` instead: they show as
a marked option and are never saved as a verdict.

`title` is **plain text**: it is escaped both when the page is built and every
time it re-renders itself on save. `eyebrow`, `lede`, `footer` and
`t` / `y` / `n` / `ev` are **rendered as HTML** — `<code>`, `<em>`, `<b>` are
yours to use. That also means any literal `<` or `&` in quoted transcript text
must be escaped by the caller. The builder refuses to emit a page containing
an unescaped `</script`.

### Card standard (GM, 2026-10-19; mytools #85)

The GM is dyslexic and rules on dozens of cards per stage. Every card a skill
builds follows this standard, and the builder lays it out:

1. **The proposed edit comes first, in bold at reading size.** Put the exact
   before → after text in `edit` (`<i>old</i> &rarr; <i>new</i>`, one bullet per
   edit, a `(&times;N)` count where it repeats). A card that keeps the older
   `<b>Exact edits:</b>` tail in `y` gets it lifted into `edit` automatically.
   `t` follows as the rationale ("Why"). Never leave the edit in small type
   under a large headline.
2. **Your guess is an option on every card where you are not confident.**
   Set `guess` to the verdict you would pick and `guessWhy` to one sentence of
   why. It is shown in a highlighted box and marked on its button, but it is
   never pre-selected and never exported. A card that arrives as a bare
   question, with no guess, makes the GM do the reviewer's work.
3. **Reject is always keep-verbatim**, and `n` says so.
4. **Body text is 15px or more.** Nothing the GM must read in order to rule is
   set smaller.

A card with no edit (a ruling that changes no text, such as "is this one
troll or two?") leads with `t` as its headline and still carries a guess.

### Why `y` and `n` are mandatory

One uniform verdict set has to work across every calling skill, whose natural verdicts
differ. It only works because **each card states its own consequences** — the
buttons say Approve/Reject, but the card says what that means *here*. A card
without a concrete `y`/`n` is a card the GM has to guess at.

---

## Verdict semantics

| verdict | meaning |
|---|---|
| **Approve** | Do the thing described in `y`. |
| **Reject** | Do the thing described in `n`. |
| **Discuss** | Neither yet — the note carries the GM's instruction, or it comes back to chat. A Discuss with **no note** means "read the surrounding context and bring me your best guess": come back with that guess as the first option, then the card's proposal, then keep-verbatim. Apply nothing until the GM chooses. |

| *extra* | Do the thing the page's `extraVerdicts` entry (or the card's `x`) says. `read_decisions.py` accepts exactly the extra keys the page declared, and tallies them beside the three built-ins. |

Plus a free-text **note** on any card (auto-revealed on Discuss).

**`Discuss all N`** is a deliberate escape hatch back to conversation. When it
is used, bring the discussed items back **as one grouped pass with their notes
attached** — never as a fresh one-at-a-time loop, which is the thing this
whole mechanism exists to avoid.

---

## Output — `decisions.json`

```json
{ "schemaVersion": 1,
  "reviewId": "ch63:stage-1",
  "savedAt":  "2026-08-19 14:02 UTC",
  "decided":  10,
  "tally":    {"approve": 6, "discuss": 3, "reject": 1},
  "decisions":{"alkrist": "discuss", "manshoon": "reject"},
  "notes":    {"alkrist": "Alkrist is alive. What I meant was…"},
  "discuss":  ["alkrist", "keys"],
  "unmarked": ["jorlan"] }
```

`read_decisions.py` **exits 1 when `savedAt` is null.** That is deliberate: a
page the GM has not saved yet must never be read as *"approved nothing."*
Pass `--allow-unsaved` only to inspect a freshly built page.

**Class cards are not expanded here.** A card with a `members` list stands
for those items, but the kit never turns one verdict into per-member records.
`members` and `draftSha256` are passed through to the page's `ITEMS` so they can
be echoed back, and a card with several members (or a `group`) shows an
"Applies to N items" marker so the GM sees how far one verdict reaches; CampaignGenerator expands them from its own stored packet (see
**NPC reviews**).

Items the GM left unmarked do not appear in `decisions`; they are listed in
`unmarked`. Treat them as undecided, not as rejected, and say so when you
report back. A decision or note keyed to an id the page never asked about
exits 2 rather than being passed through.

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
- **One item is one consent unit.** Never imply approval across several findings.
- **The page existing, being opened, or having a newer mtime is never approval.**
  Only a saved decisions file authorizes follow-up work.
- **Read-only viewers.** The page already degrades: marks stay on screen, the
  copy says read-only, and it tells the GM to report picks in chat. If they do
  that, take it — do not insist on the artifact.

---

## NPC reviews

A summary_native NPC review (`<campaign>/docs/reviews/npc-review-*/`) is
reviewed through CampaignGenerator's card contract, not by this kit reading the
review store. The kit holds no review rules: it never opens `manifest.json`,
`items/`, `events/` or `docs/reviews`, and a test enforces that. The schemas
for the packet and the decisions file are in CampaignGenerator
`specs/043-review-card-contract/contracts/card-files.md`.

```bash
KIT=~/.claude/skills/_shared/review-artifact    # or ~/.codex/skills/_shared/review-artifact
python $KIT/npc_review_items.py <campaign>/docs/reviews/<review-id> --campaign <campaign> \
    --out items.json [--ids ID,ID | --ids-file FILE] [--action NAME]
python $KIT/build_review.py --in items.json --out page.html     # add --save local on Codex
#   ... the GM marks and saves ...
python $KIT/read_decisions.py --npc --html saved.html --review <review-id> --out decisions-cards.json
#   Codex (--save local; the page holds no state, so read the exported decisions.json against the items file):
python $KIT/read_decisions.py --npc --in decisions.json --items items.json --review <review-id> --out decisions-cards.json
summary_native review cards decide <review-id> --decisions decisions-cards.json \
    --reviewer GM --campaign-dir <campaign>                       # prints the plan
#   show the plan to the GM and get their confirmation, then:
summary_native review cards decide <review-id> --decisions decisions-cards.json \
    --reviewer GM --campaign-dir <campaign> --write --plan-sha256 <HASH>
```

- `npc_review_items.py` is a shim over `summary_native review cards export`.
  It maps each card to an item (`id`, `t` = title, `y` = approveMeans,
  `n` = rejectMeans, `ev` = body plus evidence), escaping every string. A class
  card carries `members` and `group`, a sign-off card carries `draftSha256`, and
  `reviewId` is the packet id. `--ids` and `--ids-file` map to `--item`. A card
  the GM cannot validly approve is never shown, and the packet already leaves
  out items with a current approve or reject.
- `read_decisions.py --npc` writes a CampaignGenerator decisions file. With
  `--html` it takes `members` and `draftSha256` from the saved page's `ITEMS`;
  with `--in --items` it takes them from the items file (validated against the
  export by `normalize()`: item set and `reviewId` = the packet id), never from
  the GM's export. It copies notes, omits unmarked cards, and refuses `pick` and
  extra verdicts. A note on an unmarked card cannot be recorded, so every such
  card id and note is printed to stdout under "UNMARKED CARDS WITH A NOTE" and
  counted in the summary line. The echoes are compared with CampaignGenerator's stored packet, and
  the whole file is refused on any difference.
- **The agent never builds a decision batch by hand** and never runs
  `review decide` or `review npc sign` for page verdicts. `review cards decide`
  expands class cards, records what a verdict means (Approve keeps a finding as
  written, Reject sends it back for a draft fix, Approve on a sign-off signs the
  exact bytes shown), and a re-save is a no-op or a listed supersede.
- Applying is two steps on purpose: the first `decide` is a plan and writes
  nothing. Only `--write --plan-sha256 HASH` records, after the GM has seen the
  plan.

Tests: `python3 -m pytest tests/` in this directory.

---

## Phone review over Tailscale (`--save local`)

`serve_review.py` serves one built page and saves its decisions on the VM:

```bash
python $KIT/serve_review.py --page review.html --items review_items.json --out decisions.json
```

It binds to `0.0.0.0:8765` by default and prints the machine's Tailscale IPv4
address when the `tailscale` CLI is available. It serves one HTML file at an
unguessable `/r/<token>/` URL and accepts `PUT` only at that URL's `decisions`
endpoint. It exposes no directory listing, arbitrary file read or
caller-selected write path. Keep it in the foreground while the page is in use
and stop it after the decisions file has been saved and validated. Use `--port`
when 8765 is taken and `--host 127.0.0.1` for local-only testing. It is
stdlib-only and meant for a private tailnet or trusted LAN, never the public
internet. An HTTP success is a save: the same validator the CLI uses accepted
the payload. Merely loading the URL is not a decision.

---

The page has a search box and an All / Unmarked / Approved / Rejected / Discuss
filter. They only change what is shown; they are never saved with the decisions.

## Testing without a browser

```bash
python build_review.py --in fixture.json --out page.html
python read_decisions.py --html page.html            # must exit 1: never saved
# simulate a save: replace the #state block with a filled one, then
python read_decisions.py --html page_saved.html --out decisions.json

# the local transport
python build_review.py --in fixture.json --out page.html --save local
python read_decisions.py --in never.json                       # no savedAt -> exit 1
cat > export.json <<'JSON'
{"schemaVersion": 1, "reviewId": "<fixture reviewId>", "savedAt": "2026-01-01 00:00 UTC",
 "decisions": {"c1": "approve"}, "notes": {}, "unmarked": ["c2"]}
JSON
python read_decisions.py --in export.json --items fixture.json   # exit 0
```

`--in` must also exit 2 for a note on an id the fixture never asked about, an
id both decided and unmarked, and an `--items` file whose ids differ. A fixture
whose `state` pre-fills `decisions`, `notes` or `savedAt` must be refused by
the builder.

The generated page's JS can be extracted from the `#src` block and checked
with `node --check`.
