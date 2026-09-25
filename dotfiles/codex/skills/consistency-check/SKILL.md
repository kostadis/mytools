---
name: consistency-check
description: Run a CampaignGenerator consistency check on one session document, then review and apply only approved fixes. Use when the user asks to check a recap, enhanced summary, scene extraction, or narration for campaign consistency, including when they type /consistency-check [document-path].
metadata:
  short-description: Check one session document for campaign consistency
---

# Consistency Check

Run `check_consistency.py` on one session document, judge the report against
campaign context and transcript evidence, then record the sources and rulings.

This is the Codex port of the Claude skill. Do not edit
`~/src/mytools/dotfiles/claude/skills/consistency-check/` when changing this
skill.

## Codex Compatibility

- Ask user questions in chat. Do not refer to Claude `AskUserQuestion`.
- Use `update_plan` for multi-step progress when useful.
- Use `apply_patch` for manual edits to tracked documents.
- There is no Codex `Artifact` review flow here.
- Use CampaignGenerator's `--backend codex-cli` for the audit. It uses the
  operator's saved ChatGPT subscription login and does not require or forward
  an OpenAI or Codex API key.
- If Codex reports a missing executable, missing login, incompatible model, or
  timeout, surface that failure and stop. Do not silently select another
  backend. Other script backends remain available only when the user explicitly
  requests one: `anthropic`, `dgx`, `openrouter`, or `claude-code`.

## Workflow

### 1. Identify the Document

If the user passed a path, use it. Otherwise ask for the document path.
Resolve it relative to the current working directory.

Common targets:
- `summaries/<date>/gm-assist.md`
- `summaries/<date>/session-summary.md`
- `summaries/<date>/scene_extractions_new/0N_*.md`
- `summaries/<date>/narration/*.md`

Read the document before running the check. Note the session directory, likely
document class, key names, and transcript files next to it.

Classify the document:
- `first-pass recap`: direct session recap or `gm-assist.md`
- `enhanced recap`: `enhance_summary` output, usually larger than its source
- `scene extraction`: per-scene extraction containing quote blocks
- `narration`: final prose output
- `backfill`: old session checked against newer grounding docs

### 2. Locate the Campaign Root and Config

Find the campaign root by walking upward from the document or CWD until you find
`docs/`, `summaries/`, and `config/`.

Current campaign layout is:

```text
<campaign>/
  config/config.yaml
  docs/
  summaries/
```

**`<campaign>/config/config.yaml` is the only valid config.** Pass
`--config <campaign>/config/config.yaml` explicitly. Document paths inside it are
relative to `config/`, so they read `../docs/…`. Anything else is a broken
campaign: **stop, report the failing check and path, and do not run the model.**
Do not build a temporary or absolute-path config, symlink `docs/`, or rewrite
paths to make it resolve. A throwaway config with absolute document paths loads
`campaign_state` and `world_state` and silently loads **no entity registry**,
because the registry is found under the campaign root, never through
`documents[]`.

Preflight before launching — any failure is a STOP:

```bash
CAMP=<abs campaign root>
test -f "$CAMP/config/config.yaml"        || echo "STOP: no $CAMP/config/config.yaml"
test ! -e "$CAMP/config.yaml"             || echo "STOP: misplaced root config $CAMP/config.yaml"
test -f "$CAMP/docs/entity_registry.yaml" || echo "STOP: no registry at $CAMP/docs/entity_registry.yaml"
```

`check_consistency.py` enforces the same rules itself (CampaignGenerator#484). It
exits 2 on a misplaced config, and 1 on a missing registry, a missing or
unresolvable `campaign_state`/`world_state`, or a missing `--context` file.
Treat either exit as the same STOP.

Record the config path in the manifest.

### 3. Choose Session Prep

Session prep is required unless the user confirms there is none. It catches VTT
transcription errors that grounding docs cannot.

Search the whole `notes/` tree, not just `notes/session_prep/`. Candidate
locations include:
- `notes/session_prep/`
- `notes/prep/`
- `notes/sessions/`
- `notes/sessions/handouts/`
- `notes/canon/`
- `notes/threads/`
- `notes/npcs/`
- location or arc files directly under `notes/`

Categorize candidates:
- `HIGH`: exact dated/session/location prep, handouts used in this session, and
  NPC trackers.
- `MEDIUM`: arc background, evidence maps, planning, prior session recap.
- `LOW`: adjacent but off-session.

Measure every candidate with Python character counts so the unit matches
CampaignGenerator's `len(text)` telemetry:

```bash
python3 -c 'from pathlib import Path; import sys; [(lambda p: print("{:>9}  {}".format(len(p.read_text(encoding="utf-8")), p)))(Path(x)) for x in sys.argv[1:]]' <candidate files...>
```

Before asking, show `Tier`, `File`, `Characters`, and `Why relevant`, plus a
subtotal for each HIGH/MEDIUM/LOW category. Count optional prep sources only;
keep the campaign-standard sources from step 4 outside tier subtotals and
`prep_selection`. For every proposed minimal, focused, broad, or custom choice,
list the exact de-duplicated prep files and prep-only total. For a custom choice,
calculate and show the exact selection's total before accepting it. Cost informs
the human decision; never select or discard a file automatically because of its
size.

Ask the user to choose the prep set. Recommend a focused set: the exact prep
doc, relevant handouts, and NPC tracker, in addition to the standard sources.
Show that set's exact prep file list and prep-only total before asking. If they
answer `none`, continue but record that the run was prep-less.

### 4. Build Context

Always include these context files when present:
- `docs/party.md`
- `notes/vtt_transcription_corrections.md`
- `notes/vtt_known_additions.md`
- the selected prep and handout files
- the source recap when checking an enhanced recap

`check_consistency.py` auto-loads the configured `campaign_state` and
`world_state` documents. It also renders `docs/entity_registry.yaml` as
authoritative canon, including aliases, `distinct`, and `rejected_aliases`.
Do not pass the registry again through `--context`. Everything else must go
through one `--context` flag followed by all context paths.

### 5. Run the Check

Locate the CampaignGenerator repo: `~/src/CampaignGenerator` or `~/CampaignGenerator`,
depending on the machine. `ls` before building the command.

Run from the campaign root:

```bash
python3 <repo>/session_doc/check_consistency.py <document> \
  --config <campaign>/config/config.yaml \
  --backend codex-cli \
  --context <file1> <file2> ... \
  --output <session-dir>/consistency_report_<tag>.md
```

Validation after the run:
- Confirm the context count is plausible.
- Confirm there are no `context file not found` warnings.
- Never trust the banner's zero. `No issues found` counts the literal
  `**Location**`, and models often emit `**Location:**`, so the banner reports 0
  while the body lists a dozen findings.
- Count issues from the report body, and do not assume one delimiter. The
  finding delimiter varies run to run, even for the same stage on the same
  campaign: `N. **Location:**`, `- **Location:**`, `### N. <title>` with
  sub-bullets, or bold numbered runs under `##` headers. One pattern can return a
  confident 0 (`^### ` on a numbered-bold report) or overcount 4x (`^- \*\*` on a
  report whose findings each carry four sub-bullets). Find the shape, then run
  every candidate pattern:

  ```bash
  grep -n "^## \|^### \|^\*\*[0-9]\|^- \*\*\|^[0-9]\+\. \*\*" <report>   # find the shape
  grep -cE '^\s*[0-9]+\. \*\*' <report>                                    # numbered bold
  grep -cE '^- \*\*' <report>                                              # bullet bold
  grep -c  '^### ' <report>                                                # headings
  grep -cE '^\*\*[0-9]+\.' <report>                                        # bold numbered runs
  ```

  Pick the pattern that matches the report body, and record in the manifest which
  delimiter you counted.
- If `codex-cli` reports a setup, login, model, timeout, process, or empty-result
  error, stop and resolve that condition before continuing; do not treat partial
  output as a report.

### 6. Write the Sources Manifest

Create `<report-stem>.sources.yaml` in the session directory. Include:

```yaml
consistency_check:
  timestamp: "<ISO-8601>"
  campaign: "<campaign name or path>"
  document_checked: "<relative path>"
  document_class: "<class>"
  report: "<relative path>"
  config: "<config path used>"
  model: "<model the script reported>"
  backend: "<backend>"
  issues_found: <count from report body, NOT the banner; name the delimiter counted>
  session_prep_used: true            # false if the user said `none` OR none exists
  prep_selection:
    tier: focused                    # focused | minimal | broad | custom | none
    total_chars: 145429              # prep/handout files only; no standard context
    files:
      - { path: notes/<prep>.md, chars: 65916 }
      - { path: notes/sessions/handouts/<...>.md, chars: 79513 }
  entity_registry_used: true
  session_date: "<the session's own date, not today's>"
  temporal_gap: |                    # OMIT unless this is a backfilled chapter
    Session predates the grounding docs' current state by <N chapters / N years>.
    Party era from tape: <e.g. level 1>. Docs describe: <e.g. level 6, ch~45>.
    Findings rejected as anachronistic: <list>.
  speaker_map: |                     # whenever a speaker-labelled transcript exists
    <speaker> = <character>, derived from tape (not assumed from campaign docs).
    Absent players and who actually ran their PC.
  sources:
    auto_loaded:
      - { label: campaign_state, path: docs/campaign_state.md }
      - { label: world_state, path: docs/world_state.md }
      - { label: entity_registry, path: docs/entity_registry.yaml, role: "canonical entities, aliases, distinct pairs, and rejected aliases" }
    context:
      - { path: docs/party.md, resolved_path: /absolute/campaign/docs/party.md, role: "PCs" }
      - { path: notes/vtt_transcription_corrections.md, resolved_path: /absolute/campaign/notes/vtt_transcription_corrections.md, role: "ASR glossary" }
      - { path: notes/<prep>.md, resolved_path: /absolute/campaign/notes/<prep>.md, role: "session prep" }
  notes: |
    Caveats, missing prep, transcript choice, or
    auto-continuation inspection.
```

After finalizing the CLI list, resolve every explicit context path with
`realpath`. Keep the operator-facing spelling in `path` and record the absolute
value in `resolved_path`. The manifest list must contain exactly the files
actually passed through `--context`, in the same order. Do not include missing
files or the registry skipped as auto-loaded canon.

### 7. Adjudicate Findings

Treat the report as advisory. It can find a real contradiction and still choose
the wrong fix direction. The long worked cases behind these rules live in the
Claude copy of this skill; here each is a rule plus at most a one-line example.

#### Settle against the transcript

- **"VTT review needed" is a work item, not a finding to hand back.** Grep the
  transcript and close it.
- **Pick the file by the question.** Attribution: a speaker-labelled Zoom `.md`
  first. Wording: `*.retranscribed.cleaned.vtt`, then `*.cleaned.vtt`. Rule on
  content and use labels as corroboration; the GM's block absorbs other voices.
- **Attribution is settled by speaker labels, never by a summary.** With no Zoom
  `.md`, read from `*.transcript.cleaned.vtt` and adjudicate against the raw
  `*.transcript.vtt`; build the label-to-PC map once and hold it. Example: in
  Ch 65 the recap and Zoom's summary both credited the Manshoon persuasion to the
  wrong player; the raw labels settled it in one grep.
- **`zoom-summary.md` is a dropped-beat check only.** It catches beats the recap
  dropped; it is unreliable at attribution. Two summaries agreeing on "who" is a
  shared failure mode, not corroboration. If it is absent, say the run lost the
  dropped-beat check.
- **Four classes justify a trip to the tape:** internal contradictions;
  attribution of every named action (who cast, rolled, pitched, killed), not only
  flagged ones; facts no grounding doc records, such as props and equipment
  (the recap invented "Rope" from the GM's offer; the player had said "whip");
  and planned vs resolved, where a resolved action is written as an intention.
- **Watch for retracted GM slips.** Grep ±20 lines around a disputed name for
  `I meant`, `sorry`, `you're right`, `hold on`, `different character`. Example:
  GM said "Veyra", was corrected to "Sister Maela" on tape; the recap kept Veyra.
- **The GM takes back rulings too.** Grep around any number the recap asserts; a
  take-back is often a half-sentence. Check the rule before recording the
  take-back as correct: the GM can reach for the wrong edition (Ch 65).
- **When the GM reads a written passage aloud, diff the quote against that
  source document, not against your ear.** Example: "Thorin … was proved right"
  became "Alyss proved right".
- **A garbled PC name can be two characters fused.** Before any global
  replace of a PC name, read every instance and discriminate by class feature;
  a race+class epithet that matches no one in `party.md` means two PCs merged.
  Batch plain spellings; take each re-attribution to the user one at a time with
  the transcript quote. Fix pronouns from `party.md` in the same edit. Example:
  `Sema` x8 was six Soma (druid) and two Brewbarry (barbarian's rage-kill).
- **A garbled weapon or noun is evidence a word was spoken.** Two ASR passes
  garbling the same word differently means something real was said. Never rule
  an event fabricated on the absence of a noun; rule on the absence of the
  action, and check whether the fix is an addition before assuming a deletion.
  Example: "halberd" kill heard as "helmet" and "club", beside "Without raging?".
- **The absent-player failure mode.** Count distinct speakers against the party.
  A missing player means someone else ran their PC and its attributions are
  unreliable all session: check every one. Derive the speaker-to-character map
  from the tape (or read a `$speaker-attribution` manifest), never from the
  campaign doc's stated cover arrangement, and record it as `speaker_map`.
- **Enhanced recaps fail five ways**, none catchable from grounding docs:
  1. Invented dice values: grep each specific number (`\b28\b|twenty-eight`);
     timestamp-only hits mean invented. Verify values one by one.
  2. Attribution drift toward the prominent character (a heal credited to the
     protagonist in four sections).
  3. Duplication alongside loss: one hit split in two while a separate kill
     vanishes. Reconstruct the whole exchange.
  4. Truncation markers: `*(truncated)*`, a trailing em-dash or ellipsis.
  5. DM asides relocated onto the wrong result.
- **Adjudication discipline.**
  - Read the sequence forward to its end (`sed -n '<start>,<end>p'`) before
    ruling on any part; the first grep hit gives confident wrong answers.
  - A negative finding is only as wide as the grep window: search the concept,
    not just the token, and read ±20 lines around every hit.
  - When the tape cannot settle it (a muddled live count), say so and ask the GM.
    Do not pick the middle.
  - The VTT is consulted by hand, not passed as `--context`; say so in the
    manifest.
  - You are fallible too. When you overturn your own earlier reading, tell the
    GM before they act on it and record it in `vtt_adjudicated`.

#### False-positive filters — run these before anything reaches the table

- **Grep the target for the quoted text first.** The check attributes context
  text to the target. `grep -nF "<fragment>" <target>`; no hit means a false
  positive against this document. Worst at Stage 1, where `gm-assist.md` is
  context; a cluster of these suggests the enhancement pass fixed the text.
- **A session-specific context file is not authoritative.** The model promotes
  any document narrating this session (a bible chapter, a prior recap) to an
  "authoritative tier". On OOTA ch02 (2026-09-25, a backfill) 10 of 19 findings
  rested on the bible split passed as corroboration, and the tape overturned all
  10 (Shoor was in the quarters; the spools thread called fabricated is on tape).
  A finding whose only evidence is such a document is a lead to the tape.
- **Canon can be wrong vs the tape.** When a finding would rewrite the target to
  match a grounding doc or AUTHORITATIVE CANON, verify on tape first; if the tape
  disagrees, the fix belongs in the grounding doc. Ask before editing `docs/`.
  Grep `docs/distill/planning_extractions/` and `docs/ensemble/` for an existing
  correction, and check the report's own citations. Example: canon made Jorlan
  Daz's brother (a lost hedge); the tape says Nym's.
- **A finding about a quoted line may be a tape problem.** If the recap quotes
  the tape faithfully, fix `transcript_corrections.yaml` per cue and regenerate,
  never the quote alone.
- **Ordinary-word garbles inside quotes** (`feed` for feat, `decks` for Dex) are
  invisible to the spell pass and to `sd_verify_quotes`. Fix them per cue, never
  as glossary rows.
- **A real-name scrub is an attribution change.** Verify the speaker on tape
  before replacing `Gabe` with a PC name, then re-run `sd_verify_quotes`.
  Example: the scrub gave the line to Zalthir; the tape said Daz.
- **Table rulings outrank the PHB.** Before accepting any mechanics finding, grep
  the VTT for the GM's declaration (`action surge|2d8|spell slot`). A declared
  ruling is the rule for that session; a doc-level disagreement it reveals
  (character levels) goes to `carry_forward`.
- **Name the PHB edition.** Never write a bare "RAW"; cite "PHB 2024, p.304".
  Check `~/src/5etools-src/data/spells/spells-phb.json` (2014) and
  `spells-xphb.json` (2024). If the table's edition is unknown, ask the GM.
- **Backfilled-chapter anachronism.** "X is not in the documented kit" on an old
  session is doc silence, not error. Confirm on tape (`grep -niE "<spell/item>"`)
  and reject; never rewrite a backfill to match the present. State the expected
  low hit-rate up front.
- **The report can point at the wrong half of a contradiction.** It only
  establishes that the document disagrees with itself; which side to keep is a
  VTT question.
- **Module truth is not party knowledge.** Add a canonical name only if the
  party learned it on screen. Otherwise offer the user three choices: keep
  anonymous, anonymous plus bracketed GM note, or name outright. Cut unearned
  inferences ("the very same family…").
- **Module vocabulary is not table vocabulary.** No registry entry means no
  canonical form; if the phrasing traces to `docs/background/`, both are right
  ("scarlet" vs "red" cloaks). Never bulk-replace a colour, adjective or title;
  never edit `docs/background/`. A fix that would edit it is probably inverted.
- **Do not trust the "No issues found with:" footer.** Read it as findings, not
  clearance.
- **Findings often implicate the grounding docs.** Record them in
  `carry_forward`; do not silently widen scope. When the GM authorises a doc fix,
  grep all four grounding docs for the whole class, re-read old `OPEN` items, and
  check which file is actually wrong first.
- **Play divergence is informational.** Do not fix a recap to match superseded
  prep.

#### Present findings — severity-ranked table

Report your own count from the body, then present the findings that survived the
filters as a severity-ranked table, the rubric `$staged-consistency` uses:

```
  ┌─────┬──────────────────────────────┬──────────────────────────────────────────────────────┐
  │  #  │ Severity                     │                        Issue                         │
  ├─────┼──────────────────────────────┼──────────────────────────────────────────────────────┤
  │ 1   │ Critical · GM ruling needed  │ <one-line description>                               │
  │ 2   │ Moderate                     │ <one-line description>                               │
  │ 3   │ Minor                        │ <one-line description>                               │
  │ 4   │ Trivial                      │ <one-line description>                               │
  └─────┴──────────────────────────────┴──────────────────────────────────────────────────────┘
```

**Severity rubric:**

| Level | Meaning |
|---|---|
| **Critical** | Contradicts established canon (NPC fates, event timing, faction state, established mechanics); would cause player confusion or DM embarrassment if it reaches narration. Must fix before narrating. |
| **Moderate** | Framing drift — what happened is right but characterised wrongly; wrong kill attribution; characterisation that conflicts with the voice file; missing context that changes meaning. Should fix before narrating. |
| **Minor** | Misspelling of a proper noun, wrong pronoun, single-word transcription error, inconsistency within the same document. Easy to fix; fix before narrating. |
| **Trivial** | Stylistic quirk, table-chatter artifact, item you flagged as "leave as-is" in a prior stage, or flavour call that is defensible either way. Surface but do not push. |

Sort by severity (Critical first). Number issues sequentially across the whole
table.

Severity ranks findings; it does not rule on them. A **canon-judgment** finding
(a new fact no doc establishes, prep-vs-play divergence, party knowledge, or a GM
ruling) is the user's call whatever its severity. Mark it in the table (e.g.
`Critical · GM ruling needed`) and never auto-apply one.

Ask in chat before editing. Batch only fixes that are genuinely mechanical and
unambiguous, then take judgment calls one at a time with evidence and a concrete
diff. Order the batch so edits don't collide: when two fixes touch one line, do
the rewrite first with the corrected name in it. Apply accepted edits with
`apply_patch`, then grep for residual bad forms.

### 8. Append the Resolution

Append a `resolution` block to the manifest:

```yaml
  resolution:
    reviewed_by: GM
    reviewed: "<date>"
    gm_rulings_this_run:              # standing rulings the GM stated in conversation,
      - "<e.g. 'the sidekicks are all 2nd level' — records WHY findings were rejected,
         and flags that the grounding docs now disagree with the GM>"
    applied:
      - { finding: 1, fix: "<what changed>" }
    partially_applied:
      - finding: 10
        ruling: "<the user's decision in their words>"
        fix: "<what was actually changed>"
        rationale: "<why the report's suggestion was narrowed>"
    rejected:
      - finding: 2
        ruling: "<decision>"
        rationale: "<evidence>"
  vtt_adjudicated: |
    Findings settled against transcript evidence, with transcript path and
    relevant quotes summarized.
  carry_forward:
    - status: OPEN
      item: "<follow-up with enough evidence to avoid rediscovery>"
```

Every `carry_forward` item must have a status:
`OPEN`, `DONE`, `CORRECTION`, `WONTFIX`, or `NOTE`.

Validate the manifest parses as YAML, show the relevant diff, and close with:
- fixes applied
- findings rejected or deferred
- what transcript review caught
- carry-forward items

## Notes

- **The registry is the arbiter for rejecting findings, but its authority is
  bounded.** A flagged name with no `docs/entity_registry.yaml` entry has no
  canonical form; the proposed "correct" form may be inherited module phrasing.
- **"The registry has the wrong name" is usually "the registry has no name."**
  Check for absence first (`grep -ciE "<name>|<variants>"
  docs/entity_registry.yaml`; beware substring hits). The fix is promotion of
  the entity, not correction; put it in `carry_forward`.
- **Garbles are not aliases.** The registry holds identity (titles, short forms,
  epithets); ASR mishearings belong in `notes/vtt_transcription_corrections.md`.
  A garble written as an alias suppresses true findings.
- **Do not action `registry check`'s grouping drift blindly**
  (CampaignGenerator#216). It compares against the garble map, so every
  registered garble shows as `MISSING`; only `MISSING` on both sides is signal.
- **Two files are named `aliases.json`.** `docs/aliases.json` is the identity
  projection; `docs/ensemble/aliases.json` is the garble map, and it goes stale.
  Check which one you are reading.
- **Adding a glossary row is a behaviour change.** Verify the wrong form occurs
  in a VTT first (`grep -ril "<form>" summaries/*/*.vtt`); a form in no
  transcript is a summarizer invention. Test the applier on a scratch output,
  never in place.
- **Registry CLI:** `python -m entity_registry.registry <verb>` from the
  CampaignGenerator repo root (running `registry.py` directly fails on a relative
  import). A registry MCP exists but may not be registered for the campaign.
- **Three transcripts can give three answers.** Prefer the retranscribed VTT
  and say which you used. A name matching neither the garble nor the truth
  ("Desa" for Dessa/Dosa) is a summarizer invention no glossary will catch.
- **Document classes fail differently.** First-pass recap: names. Enhanced
  recap: numbers, attribution and ordering; expect a poor report hit rate
  (8 of 12 unappliable in one run) and most real errors from the VTT. Scene
  extraction: verbatim quote fidelity and speaker attribution. Backfill: names,
  attribution and era false positives, usually with no prep. A low hit rate does
  not mean the document is clean.
