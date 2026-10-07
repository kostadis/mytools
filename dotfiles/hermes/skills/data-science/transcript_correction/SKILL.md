---
name: transcript_correction
description: Correct garbled proper nouns / transcription errors in raw transcript or artifact files (e.g. Zoom/Otter/Whisper .vtt) using a single source-of-truth glossary. Covers the full workflow — locating the actual garbled artifact, word-boundary-safe substitution, preserving file formatting (CRLF), and verifying the result.
---

# Transcript / Artifact Correction from a Glossary

Use when a user asks you to "fix the transcription errors" / "correct the garbled
names" in session transcripts, captions, or generated summary files, and there is
a single source-of-truth glossary (a wrong→right list) to drive the fixes.

Common framing: "go through the transcripts and correct the file" where a
glossary like `vtt_transcription_corrections.md` exists. The deliverable is a
corrected artifact, verified by real tool output — NOT a summary of what you
would change.

## Core workflow

1. **Find the glossary (source of truth).** Locate the file that defines
   wrong→right mappings. It may live in `notes/`, `docs/`, or be referenced by
   other artifacts. Read it FIRST. Honor its own rules — e.g. many glossary
   files explicitly say short-forms / titles / player→character mappings
   (e.g. `Sildar`→`Sildar Hallwinter`, `Nikhil`→`Zenvon`) must NOT be
   substituted, because a word-boundary applier would double-expand them.
   Those belong in a separate bundling/alias generator, never in the text pass.

2. **Inspect the candidate artifacts BEFORE editing.** Grep each candidate file
   for both the *wrong* and the *canonical* forms. This is the single most
   important step: the file you were told to "correct" is often already clean
   (e.g. a human-authored summary), while the *raw* transcript (`.vtt`) still
   holds the garbles. Correct the file that actually contains the errors. Do not
   edit a file that already has the canonical spelling — you'll waste effort or
   introduce risk.

3. **Back up the originals.** `cp file.vtt file.vtt.bak` before any in-place
   edit. Cheap insurance; keep them until the user confirms.

4. **Substitute word-boundary-safe and case-insensitive.** Anchor every wrong
   form with `\b` so you don't mangle substrings (e.g. `Mela`→`Maela` must not
   touch `Melavera`). A reusable script lives in `scripts/apply_glossary.py`.

5. **PRESERVE LINE ENDINGS.** Transcript formats like WebVTT REQUIRE CRLF
   (`\r\n`). Reading/writing in Python text mode (the default) silently
   normalizes `\r\n`→`\n`, which corrupts the file and makes a `diff` show every
   line changed. **Always read/write in binary** (`open(path, "rb")` /
   `f.write(text.encode("utf-8"))`) so only the names change. Verify with
   `file path` → it should still report "with CRLF line terminators".

6. **Verify with a diff, not by eyeballing.** `diff file.vtt.bak file.vtt`
   should show ONLY the name substitutions. Confirm: (a) zero documented garbles
   remain, (b) canonical forms are present, (c) CRLF intact, (d) every changed
   line differs only by the name. A reusable verifier is in
   `scripts/verify_corrections.py`.

7. **Surface what you did NOT fix.** If the transcripts contain garbles NOT in
   the glossary (e.g. `Soldar`→Sildar, `Gundrund`→Gundren), report them and
   offer to add them to the glossary and re-run. Don't silently expand scope.

8. **LOWER-CASE / NON-CAPITALIZED SEMANTIC PASS (mandatory, not optional).** The
   capitalized-name and word-pair hunts above MISS garbles that render as
   common lowercase words or module terms — these never surface as
   unrecognized Capitalized tokens, so the registry scan cannot see them. You
   MUST run this pass on the (partially) cleaned transcript before declaring
   done. Technique (full recipe in `references/lowercase_semantic_pass.md`):
   - Enumerate lower-case module terms and their known ASR garbles, then grep
     the cleaned file for any surviving garble form. Campaign examples that
     were MISSED until this pass was added: `notar`→**dwarf**, `Red Browns`→
     **Redbrands**, `Forward Giants`→**Redbrands**, `red brand`→**Redbrand**,
     `frock-seeker`→**Rockseeker**, `Roxiga`→**Rockseeker**, `Glass Staff`→
     **Glasstaff** (two-word), `Gundren Roxiga`→**Gundren Rockseeker**.
   - Also grep for frail lowercase tokens that are phonetic garbles of module
     terms (e.g. `notar`, `red brown`, `forward giant`) and confirm IN CONTEXT.
   - This pass is what catches the lower-case typos the user explicitly asks
     about ("what about lower case typos? Probably needs a semantic pass?").
     Do not skip it even if the Capitalized scan came back clean.
   ones" / "did you only use the known list").** Applying the existing glossary
   is necessary but NOT sufficient — a raw transcript typically holds garbles
   the glossary never captured. To find them:
   - Pull the **canonical name list** for the domain (for this campaign:
     `docs/background/name_glossary.md`, plus `docs/ensemble/known_names.md` and
     `party.yaml`) and grep each canonical name into both transcripts. A name
     with **zero canonical hits but many phonetic variants** is a smoking gun
     (e.g. Gundren → 0 correct vs ~17 of `Gundran/Gundrin/Gundrum/Gundrun/
     Gundrund`; Sildar → 0 correct vs `Soldar/Siddhar/Silar/Silvar`).
   - Cast a **phonetic scan** over each core name with a loose regex
     (`\bGund[a-z]{2,6}\b`, `\b(Sil|Sold|Sidd)[a-z]+\b`, `\bBart[a-z]*\b`,
     `\bLin[a-z]*\b`) and `sort | uniq -c` the variants. This surfaces the
     misspellings in one pass.
   - **Verify each candidate IN CONTEXT before treating it as a garble.** Some
     near-matches are genuine other words (e.g. `Linux`, `link`, `half`,
     `hardware` are not garbles of Linene/Halia/Harbin). Print the matching
     line and confirm the entity is meant. When confident, ADD the new
     wrong→right rows to the glossary file (it is the source of truth), then
     re-run the full pass from the pristine `.bak` so old + new fixes apply
     together.
   - Cross-check contested sightings against the canonical glossary's ruling
     notes. Example: `Silar`/`Silvar`→Sildar is plausible but flagged
     "verify vs. other names" because those two lines could in theory name a
     different character — note the uncertainty in the glossary entry.

   - **CROSS-CHECK AGAINST THE AUTHORITATIVE ENTITY REGISTRY (stronger than the
     name_glossary grep).** When the domain has a canonical entity list
     (this campaign: `docs/entity_registry.yaml` — GENERATED, 374 entities;
     mirrored in `docs/entity_inventory.md`), use it as the enumerative source
     of truth, NOT just `name_glossary.md`'s curated subset. Technique:
     1. Build a `known` set from the registry: every `name:` + every `aliases:`
        entry, lowercased, plus each word (≥3 chars) of multiword names. Also
        fold in the glossary's right-hand sides and any campaign-original
        names. (No PyYAML? parse `^- name:` and indented `- ` alias lines with
        regex — see `references/entity_registry_scan.md`.)
     2. Walk both transcripts; strip the speaker prefix (`^Name Name:`); collect
        every `Capitalized` token NOT in `known` and NOT a common-English
        stopword. Anything left is a candidate missed garble.
     3. **ALSO scan for word-pair / split garbles** — ASR frequently breaks a
        name into two words or garbles it as a phrase (user-called-out pitfall:
        "proper nouns are turned into word pairs or words"). Examples from this
        campaign: `Weiwe Vekov Cave`→Wave Echo Cave, `Fandele Verpakt`→Phandelver
        Pact, `Linene Lanain`→Linene Graywind, `Jarno Albrecht`→Iarno Albrek.
        Catch these by scanning for a Capitalized word immediately followed by a
        short (2–4 char) lowercase word, and by treating multi-word phrases as
        single garble units in the corrections list (e.g. `Weiwe Vekov Cave`→
        `Wave Echo Cave`). The single-token phonetic regex alone MISSES these.
     4. The registry scan typically surfaces a SECOND WAVE the name_glossary
        grep missed (here: Iarno, Cragmaw, Zhentarim, Phandalin variants,
        Tharden, plus more Toblen/Gundren variants). Fold every confirmed find
        into the glossary and re-run the full pass from `.bak`.

## Pitfalls

- **Editing the wrong file.** A summary/recap is usually hand-cleaned already;
  the raw `.vtt` is where garbles live. Grep both forms first.
- **CRLF corruption (critical).** Default text-mode I/O strips `\r`. Use binary
  I/O. This bit hard once — the diff lit up every line even though only names
  changed, because the line endings had been rewritten.
- **Double-expansion.** Never include title/short-form/player→character mappings
  in the word-boundary pass; they cascade. Keep them in the glossary file's
  generator only.
- **Substring bleed.** `Mela` without `\b` corrupts `Melavera`. Always anchor.
- **Over-scope.** Only fix what the glossary authorizes. New garbles → report,
  don't auto-invent canonical spellings.
- **False-positive garbles.** A loose phonetic scan returns real other words
  (`Linux`, `link`, `half`, `hardware`, `line`). Always print the candidate
  line and confirm the entity is meant before adding a row. When unsure, note
  "verify vs. other names" in the glossary entry rather than guessing.
- **Glossary drift after adding rows.** When you add new garbles mid-session,
  re-run the FULL pass from the `.bak` originals so old + new fixes apply
  together — don't patch the already-corrected file incrementally (you'd
  double-read CRLF and risk corruption).
- **Skipping the lower-case / semantic module-term pass.** The Capitalized-token
  and word-pair hunts only see Capitalized names; a garble rendered as a common
  lowercase word (`notar`→dwarf, `red browns`→Redbrands, `frock-seeker`→
  Rockseeker, `glass staff`→Glasstaff) is INVISIBLE to those scans. Always run
  the lower-case pass (step 8) on the cleaned file before declaring done. The
  user explicitly calls this out ("what about lower case typos? Probably needs
  a semantic pass?").
- **Only checking the curated glossary / name_glossary, not the entity registry.**
  A phonetic grep over `name_glossary.md` finds garbles for names you thought to
  check, but MISSES entire entities the glossary never listed (here: Iarno,
  Cragmaw, Zhentarim, Phandalin, Tharden). Cross-check against the authoritative
  registry (`entity_registry.yaml` / `entity_inventory.md`): enumerate all known
  entities, then flag any unrecognized Capitalized token in the transcripts. This
  is the enumerative check that catches the second wave. See
  `references/entity_registry_scan.md`.
- **Word-pair / split garbles.** ASR splits names into two words or renders them
  as phrases ("Weiwe Vekov Cave"→Wave Echo Cave, "Fandele Verpakt"→Phandelver
  Pact, "Gun dren"→Gundren). Treat multi-word phrases as single garble units in
  the corrections list and scan for Capitalized+short-lowercase-word pairs. A
  single-token `\bName\b` scan will NOT catch these.

## Support files

- `scripts/apply_glossary.py` — byte-preserving, word-boundary, case-insensitive
  glossary applier. Edit the `CORRECTIONS` list (or load your glossary module).
- `scripts/verify_corrections.py` — ad-hoc verifier: confirms garbles gone,
  canon present, CRLF intact, name-only diffs vs `.bak`.
- `references/glossary_obelisk.md` — condensed copy of the obelisk campaign's
  `vtt_transcription_corrections.md` (PCs, NPCs, locations) and its DO-NOT-SUB
  rules, for context when working this campaign.
- `references/entity_registry_scan.md` — how to drive the PROACTIVE HUNT from the
  authoritative entity registry when a `name_glossary.md` grep isn't enough:
  building the known-name set (incl. regex parsing of `entity_registry.yaml`
  WITHOUT PyYAML), the unrecognized-Capitalized-token scan, and the word-pair /
  split-garble scan. Use this when the user says "did you use the registry /
  entity inventory as source of truth" or "look for word-pair garbles".
- `references/lowercase_semantic_pass.md` — the MANDATORY lower-case / non-
  capitalized module-term sweep (step 8): why the Capitalized scans miss these,
  the list of known lower-case garbles to grep for, and the check recipe. Run it
  on the cleaned file before declaring done.
