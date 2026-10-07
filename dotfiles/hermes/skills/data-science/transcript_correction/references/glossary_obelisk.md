# Condensed obelisk campaign transcription glossary

Source: `notes/vtt_transcription_corrections.md` (single source of truth for
Zoom/Otter/Whisper proper-noun garbles in this campaign's session transcripts).
Canonical spellings verified against `docs/background/name_glossary.md` and
`characters/`. Keep `aliases.json` (generated) in sync via the glossary
generator - never hand-edit it.

## TRUE GARBLES (safe to substitute into transcript text)

PCs
- Xenophon / Zenobon / Zenovon / Xenovan / Xenobon / Xinavan -> **Zenvon**
- Vera / Melavera -> **Veyra**
- Sister Mela / Mela -> **Sister Maela**

NPCs & creatures
- Clarg -> **Klarg**
- Toblin / Tobelin / Tublin -> **Toblen**
- Glastaff -> **Glasstaff**
- Darren Edermeth -> **Daran Edermath**
- Oren Voss -> **Orryn Voss**
- "Ruth exceeds" (garbled whispered name) -> **Ruxithid**
- Soldar / Siddhar / Silar / Silvar -> **Sildar** (ASR garbles of "Sildar
  Hallwinter"; Silar/Silvar flagged "verify vs. other names" - confirmed Sildar
  by context)
- Gundran / Gundrin / Gundrum / Gundrun / Gundrund / Goodrin / Dundrum ->
  **Gundren** (ASR garbles of "Gundren Rockseeker"; ~17 variants, zero correct
  spellings in the raw .vtt)
- Thardin -> **Tharden** (Rockseeker brother)
- Barthin -> **Barthen** ("Barthin's prov[isions]" = Elmina Barthen's shop)
- Linen / Lanain -> **Linene** ("Linene Lanain ... Lionshield coster" = Linene
  Graywind; Lanain is a double-garbled surname)
- Yarno / Yorno / Jano / Yano / Jarno / Vekov / Evoko / Quip -> **Iarno** (ASR
  garbles of "Iarno Albrek"/Glasstaff; "Quip" mapped to Iarno by context - could
  also be Pip, flag if disputed)
- Albrecht -> **Albrek** ("Jarno/Larno Albrecht" = Iarno Albrek)
- Ruxothid / Ruxathid -> **Ruxithid** (Veyra repeating the goblin's name)

Locations
- Tresender Manor / Tressander Manor -> **Tresendar Manor**
- Eldermath Orchard -> **Edermath Orchard**
- Nethrel -> **Netheril**
- Tribor Trail -> **Triboar Trail**
- Fandelin / Fandalin / Fandele / Fendolin / Panelin / Phanalyn / Fandeliever ->
  **Phandalin**
- Nevermember / Nevermber / Neverwin -> **Neverwinter**
- Weiwe Vekov Cave / Evoko Cave -> **Wave Echo Cave** (phrase garbles)
- Fandele Verpakt -> **Phandelver Pact** (phrase garble)
- Kragmaw -> **Cragmaw**
- Zentarim -> **Zhentarim**

## DO NOT SUBSTITUTE (live in the generator's BUNDLING_ALIASES, not the text pass)

The glossary file explicitly forbids these from the word-boundary applier -
substituting them would DOUBLE-EXPAND downstream text:
- Entity short-forms / titles: e.g. `Sildar` -> `Sildar Hallwinter`
- Player -> character mappings: e.g. `Nikhil Reddy Mettupally` / `Nikhil` -> `Zenvon`

## Reality check from session 004 (and the follow-up "continue")

The raw `.vtt` transcripts held the garbles; the human-authored `gm-assist.md`
summary was ALREADY corrected (only the surname "Dawnforge" on Sister Maela
remained - but `docs/background/name_glossary.md`'s appendix explicitly lists
**"Sister Maela Dawnforge"** as campaign canon, and it's in `party.yaml`, so it
is CORRECT, not an error - the old `consistency_report.md` issue 10 was stale).
Lesson: before "fixing" a flagged name, cross-check the canonical glossary - it
may already bless the spelling the report calls wrong.

### HOW the new garbles were found (proactive hunt)

First wave (name_glossary.md grep): grep each canonical name into both
transcripts; zero canonical hits + many variants = smoking gun; phonetic scan
(`\bGund[a-z]{2,6}\b`, `\b(Sil|Sold|Sidd)[a-z]+\b`, `\bBart[a-z]*\b`,
`\bLin[a-z]*\b`) then `sort | uniq -c`; print each candidate line to confirm
(rules out Linux, link, half, hardware).

Second wave (entity_registry.yaml cross-check - the user explicitly asked
"did you use the entity inventory as source of truth?"): build a known-name set
from `docs/entity_registry.yaml` (374 entities; GENERATED, mirrored in
`docs/entity_inventory.md`), then flag ANY unrecognized Capitalized token in the
transcripts. This surfaced Iarno, Cragmaw, Zhentarim, Phandalin, Neverwinter,
Tharden, and more Toblen/Gundren variants that the curated grep never listed.
When the user asks this question, the answer must be YES: drive the hunt from
the authoritative registry, not just a curated subset. Technique in
`references/entity_registry_scan.md`.

### WORD-PAIR / SPLIT garbles (user-called-out pitfall)

ASR turns proper nouns into word pairs or phrases. Single-token scans MISS
these. Handle by scanning for a Capitalized word + short (2-4 char) lowercase
word, and by treating multi-word phrases as single garble units in the
corrections list (e.g. `Weiwe Vekov Cave` -> `Wave Echo Cave`). Session catches:
Weiwe Vekov Cave/Evoko Cave -> Wave Echo Cave, Fandele Verpakt -> Phandelver
Pact, Linene Lanain -> Linene Graywind, Jarno Albrecht -> Iarno Albrek, "Gun
dren" splits -> Gundren.
