# Phandalin Module Corpus (docs/background/ + published spine)

Knowledge bank for the **Phandalin** campaign (`~/src/campaigns/Phandalin/`),
covering where the adventure *source modules* live and how they sequence. Read
this before any chronology / lore-map / faction-from-adventure task in Phandalin.
Derived from a direct read of the files in `docs/background/` plus the campaign
`CLAUDE.md`.

## Where the modules live
Unlike `obelisk/` (one big `docs/background/obelisk.md`), Phandalin keeps its
source modules as **separate files in `docs/background/`**. The narrative bible
split lives at `docs/chapters/` (NOT a top-level `chapters/` dir — that path does
not exist). So `cd ../background` from `docs/chapters/` lands you in the right
place.

Files present in `docs/background/` (as of this writing):
- **Essentials Kit adventure books (4):** `Essentials Kit_ Dragon of Icespire Peak.md`,
  `Essentials Kit_ Storm Lord's Wrath.md`, `Essentials Kit_ Sleeping Dragon's Wake.md`,
  `Essentials Kit_ Divine Contention.md`.
- **Inventory / source lists:** `dragon-of-icespire-peak-inventory.md` (DoIP
  source-material nouns — authoritative, not homebrew), `neverwinter-inventory.md`
  (campaign's *working picture* of Neverwinter — explicitly "not raw source").
- **Gazetteers:** `Sword Coast Adventurer's Guide.md`,
  `Forgotten Realms_ Heroes of Faerûn.md`.
- **Faction material:** `3627966-Factions_of_Phandalin_4.5.1.pdf` (prebuilt
  faction write-ups — natural input for a factions-from-adventure pass),
  `The Lord's Alliance Agent.md`, `The Order of the Gauntlet Agent.md`.
- **Campaign-specific lore/scene:** `Withering Grove.md`, `Lathander and Valphine.md`,
  `Storm.md`, `Encounter- The Anonymous Letter.md`,
  `The 1489 Export Regulation on Interplanar Storage Devices.md`.
- **KP / planar thread:** `The Self-Aggrandizing Gnome- Kazneporium
  Ketternopappux's Misadventures.md`, `Knazreponnium Ketternopappux- A Case Study
  on the Structural Dangers of Arcane Potency to Divine Hegemony.md`,
  `KP Post-Barovia - Biographer Note.md`.

## Canonical published spine (verified "sequel to" language)
The four Essentials Kit books are the only true *adventure modules* in the
folder. Their order is taken verbatim from each book's own Introduction / Adventure
Background, which states the sequel relationship explicitly.

| Order | Module | Levels | Base / threat | Connects to next via |
|------|--------|--------|---------------|----------------------|
| A1 | Dragon of Icespire Peak | 1→7 | Phandalin / Cryovain (white dragon) | Slays Cryovain; every later book references "Phandalin, which recently had dealings with a white dragon named Cryovain … dispatched by adventurers" |
| A2 | Storm Lord's Wrath | 7→9 | Leilon / Talos cult (Fheralai Stormsworn) + Myrkul cult (Ularan Mortus); Ebondeath (black-dragon wraith) seeks a living dragon body | Ebondeath wants a dragon body |
| A3 | Sleeping Dragon's Wake | 9→11 | Leilon / Ebondeath **possesses** green dragon Claugiyliamatar ("Old Gnawbone") | Green dragon hijacked by the black-dragon wraith |
| A4 | Divine Contention | 11→13 | Leilon (rebuilt) / Myrkul cult HQ in Mere of Dead Men ("Ebondeath's Mausoleum") | Dracolich Ebondeath climax |

Spine in one line: Cryovain dies (DoIP) → Leilon rises, Talos+Myrkul cults,
Ebondeath wants a body (SLW) → Ebondeath possesses Claugiyliamatar (SDW) →
Myrkul entrenches in the Mere, dracolich showdown (DC). The trilogy is formally
called "**Beyond the Dragon of Icespire Peak**" (SLW = first, SDW = second, DC = third).

## Homebrew overlay modules (from `Phandalin/CLAUDE.md`)
The campaign is a "Dragon of Icespire Peak / Lost Mine of Phandelver hybrid" with
three modified published arcs layered on top. Ordered by *campaign role*, not
standalone publication date:

- **Lost Mine of Phandelver (LMoP)** — early-tier, parallel/merged with DoIP
  (Redbrands, Cragmaw, Glassstaff, the Black Spider, Hamun Kost, Wave Echo Cave).
  The **Carver** (sorcerer-warlord who marched on Icespire Hold to bind Cryovain,
  then burned Phandalin) is the campaign's signature villain built on this tier.
- **War of the Giants** (Storm King's Thunder, modified) — **Hekaton** (Storm
  Giant King) allied with the **Lord's Alliance**, ending the war. Surfaces via
  the Counterforce doctrine (`docs/CounterForce.md`).
- **War of the Dragons** (Tyranny of Dragons, modified) — Cult of the Dragon /
  Tiamat arc: **Severin** (cult leader), **Zariel** (archdevil who used the cult
  as a loophole to expel Tiamat from Avernus), **Iymrith** ("Desert Wind," blue
  dragon, true architect of the giant war; escaped to Avernus). Braids into the
  mid-to-late game on top of SLW/SDW/DC.
- **Neverwinter** (overlay) — city-politics + KP planar thread: Dagult
  Neverember (Lord Protector), the Nashers (Sons of Alagondar), the Ashmadai, the
  Dead Rats, and KP / Kazneporium Ketternopappux + the Counterforce of
  Rimardo+Corrin. Neverember is the through-line linking the Phandalin region to
  the Leilon rebuild.

Overlay in one line: LMoP+Carver (parallel to DoIP) → War of the Giants and War
of the Dragons braid into mid/late game → Neverwinter/KP runs underneath and
collides at the Iymrith endgame.

## Hand-authored vs generated docs convention
`Phandalin/CLAUDE.md` is explicit: `docs/campaign_state.md`, `docs/world_state.md`,
`docs/party.md`, `docs/planning.md` are **CampaignGenerator outputs — do NOT
hand-edit** (clobbered on regeneration). For hand-authored campaign material,
create new dossier files at `docs/` top level (matches the `Aletra.md`,
`Brundar.md`, `Kraken society.md` convention) and reference them from CLAUDE.md.

Practice note: a hand-authored module-chronology doc was written to
`docs/background/module_chronology_and_lore.md` (a subdir of `docs`), which is
acceptable but technically one level deeper than the "docs/ top level" rule
suggests. If strict separation from generated docs matters, prefer `docs/`
top level for new hand-authored files. Do NOT touch the generated `docs/*.md`.

## Reuse
A factions-from-adventure pass in Phandalin should start from the
`Factions_of_Phandalin_4.5.1.pdf` plus this spine, then fold in the overlay arcs.
The chronologically-sorted map itself lives at
`docs/background/module_chronology_and_lore.md`.
