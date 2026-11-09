# dde-npc

Quick NPC generator driven by the random tables in **Castle Oldskull DDE1: Book One – The Dragon Rises** (Kent David Kelly, *Dungeon Delver Enhancer*, 2nd printing Feb 2017). It is rpg-lib book #8317.

**This repo is public, so it holds no book content.** `extract.py` reads your own copy of the PDF and writes the tables to
`~/src/homebrew-private/book/dde1-castle-oldskull/tables.json` (override with `$DDE_DATA` or `--out`). `dde_npc.py` reads them from that same path.

## Setup (once)

```bash
python3 extract.py          # needs pdftotext (poppler-utils); default PDF path is the Drive copy
```

No pip dependencies; stdlib only.

## Use

```bash
./dde_npc.py                                  # one quick NPC
./dde_npc.py -n 5                             # five
./dde_npc.py --race dwarf --sex f --class fighter --full
./dde_npc.py --culture norse --alignment CE --stats "16 9 10 12 14 7"
./dde_npc.py --class commoner --rank 100      # a lowly commoner
./dde_npc.py --json                           # machine-readable
./dde_npc.py --list                           # every table key
./dde_npc.py --table step-35-speech-patterns -n 3   # roll one table
```

Defaults: race is weighted (human 60%), sex is random, the NPC is a commoner 50% of the time and otherwise a random class, ability scores are 3d6 each, alignment is random.

**Quick mode** rolls these steps: name and epithet (1–4), ability descriptors (5), handedness (6), class theme (10), background and secondary skill (13, 18), clan trade (12), social standing (23), purse (25), grooming (26), eyes, hair and skin (27–29), unusual trait (30), demeanor (31), likes and dislikes (32–33), company (34) and speech (35).

**`--full`** adds the class and race steps: druidic clan and spirit companion (8, 21), tribal land and calling (9), spell sphere (11), rogue talent (15), fighting style (16), racial lore (17), extra languages (14), famous ancestor (19), bardic trickery (20), familiar (22), coat of arms (24) and company name (37).

The rules follow the book:
- The epithet comes from the highest score if any score is above 15. Otherwise it comes from the lowest score if any is below 8. Otherwise it comes from alignment: 60% good/evil axis, 40% law/chaos axis.
- Handedness resolves "If Dexterity 15+" against the actual score.
- Entries that say "roll twice" are followed, and "Reroll" entries are rerolled.
- Social standing starts at the class's level-1 rank. Commoners roll a rank from 68 to 112.

## Extraction notes

The extraction is deterministic: `pdftotext -layout` followed by regex. No LLM is involved. Every table is checked to cover 1..N with no overlaps.
- **Printed typos** in the book (e.g. Clerics `[54-07]`, Uncommon Languages `[01-15]`/`[06-01]`, overlapping ranges) are fixed in the explicit `ERRATA` table in `extract.py`. Each fix has a comment and the corrected entry records its `printed` range.
- **Ranges the book simply omits** remain as gaps, and the generator rerolls when it hits one: Orcish male names 7–9, Illusionist theme 54, Heraldic charges 65–68, Cleanliness 81–85. `extract.py` reports these every run.
- **Not extracted:** the per-school mage and illusionist spell lists (the tool reports only the sphere), the multi-class alternate titles (step 7), and the second "Charisma / social standing" adjustment to cleanliness.
