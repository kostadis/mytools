# Chapter 43 extraction notes — "The Unfated Routine of Rimardo and Corrin"

## Paths & sections
- File: `docs/chapters/chapter_43_the_unfated_routine_of_rimardo_and_corrin.md`
- Six POV sections (no NN.MM numbering in headers this chapter; used `(43.0N)` by section order):
  1. Vukradin — The Late Curtain Call
  2. Valphine — Reflections on Fate and Morning Plans
  3. Soma — Negotiations with the Boars
  4. Brewbarry — Incursion into the Woodland Manse
  5. Valphine — Battle in the Courtyard
  6. Soma — Exploring the Ruined Manse

## Match results (24 hits, all confirmed genuine)
Party: Vukradin, Soma, Valphine, Brewbarry, Prutha.
Performers: Rimardo, Corrin. NPCs: Falcon the Hunter, Sister Kaella, Jenna (Roscoe), Meril, Boney.
Deities/factions: Talos, Lathander, Savras, Lord's Alliance, Anchorites of Talos.
Locations/items: Woodland Manse, Falcon's Hunting Lodge, Shrine of Savras, Leilon, Boots of Elvenkind, Menzoberranzan.
Concept: Orcanese (alias "Orcish").

## Alias-hit audit outcomes
- `Falcon the Hunter` via alias "The Falcon" ("the Falcon mission") and lodge via alias "Falcon's Lodge" — both genuine.
- `Anchorites of Talos` via alias "cleric" — hit was "Cleric of Lathander" (Prutha's line), NOT an Anchorites reference; the anchorite events were attributed via name matches elsewhere. Context-audit saved this from a false bullet.
- `Orcanese` via alias "Orcish" — genuine usage.

## Registry gaps found (no entry → no file, reported)
- Aretha (name-dropped once, ch43.06).
- Church of the Searing Light / "true sect of Lathander" (covered under Lathander file).
- ch43 combatants as such: stirges (3), vine blights (5), twig blights — registry only has old location-specific entries; covered inside Woodland Manse + party files.
- The two talking boars outside the manse — registry has only rejected-alias "boar/boars/talking boar".

## Parser note
Registry ends with `distinct:` and `rejected_aliases:` blocks (e.g. `- - boars / - boar / - talking boar`). A parser keyed on `- name:` ignores them correctly — do not ingest them as entities.
