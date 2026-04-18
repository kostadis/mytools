# flexai-combat

A GM tool that implements the **FlexAI for Combat Encounters** rules from
the *FlexAI Guidebook* (Infinium Game Studios, 2020), pages 12–22, driven
by the `FlexAI_Combat_2021_01_04.xlsx` Digital Resource Companion.

Pick a Role × Size × Stance × Rank, see the full d100 Outcome and
Targeting bucket layout, and resolve the creature's turn at one of three
complexity tiers: **Simple** (d20 on fixed tables), **Full** (d100 on the
role-specific FlexTable), or **Advanced** (same roll, keeps the
Minor/Major Surge or Lull tag).

- [`RULES.md`](RULES.md) — verbatim rules text extracted from the Guidebook pp. 12–22.
- [`flexai_combat.py`](flexai_combat.py) — workbook loader and resolver library.
- [`app.py`](app.py) — Flask web UI on port 5106 (pairs with `flexai-social` on 5105).
- [`test_flexai_combat.py`](test_flexai_combat.py) — pytest suite (tiny fixture workbook, no commercial data shipped).

## Quickstart

```bash
pip install -r requirements.txt
python3 app.py
# open http://localhost:5106
```

## Data file

The tool reads one xlsx file from the FlexAI Digital Resource Companion:

```
FlexAI_Combat_2021_01_04.xlsx   # Outcome + Targeting FlexTables per Role
```

This is **commercial content** and is never committed to this repo.

The data directory is resolved in this order:

1. `--data-dir PATH` on the `app.py` command line.
2. `FLEXAI_COMBAT_DATA_DIR` environment variable.
3. Hard-coded default:
   `/home/kroussos/kosta/OneDrive/Dungeons and Dragons/Tools`

The server prints the resolved path at startup so a wrong location is obvious.

## Running tests

```bash
pytest -v
```

Tests build a tiny synthetic workbook into `tmp_path` via
[`fixtures/build_fixtures.py`](fixtures/build_fixtures.py) — no real
commercial xlsx is required or shipped.

Regenerate the fixture workbook on disk (for manual inspection):

```bash
python3 fixtures/build_fixtures.py
```

## CLI reference

```bash
python3 app.py [--data-dir PATH] [--host HOST] [--port 5106] [--debug]
```

| Flag           | Default                                           |
|----------------|---------------------------------------------------|
| `--data-dir`   | `$FLEXAI_COMBAT_DATA_DIR` or hard-coded default   |
| `--host`       | `127.0.0.1`                                       |
| `--port`       | `5106`                                            |
| `--debug`      | off                                               |

## Architecture

```
flexai_combat.py                           # library — no Flask, no HTTP
    load_tables(data_dir)                  # read workbook -> nested dict
    get_cell(table, role, size, st, rank)  # look up one FlexCell
    roll_simple_outcome(rng=...)           # d20, hardcoded table
    roll_simple_target(rng=...)            # d20, hardcoded table
    roll_full_outcome(cell, rng=...)       # d100 -> (outcome, surge|None)
    roll_targeting(cell, rng=...)          # d100 -> target
    resolve_turn(table, ..., tier, rng=...)# full turn, any tier

app.py                                     # Flask UI — thin wrapper
    create_app(table=..., data_dir=...)
    routes: /  /api/cell  /api/resolve  /rules
```

Three complexity tiers, all in one resolver:

- **Simple** — ignores role/size/stance/rank; rolls d20 on the fixed
  Tables 4 and 5 baked into the library from the Guidebook p. 15.
- **Full** — rolls d100 on the loaded Role×Size×Stance×Rank FlexTable;
  surge/lull rows collapse to their base outcome.
- **Advanced** — same d100 roll, but the surge/lull tag is retained so
  the GM can apply Minor/Major Surge or Lull bonuses from Tables 9/10.

The library is deterministic and RNG-injectable — `resolve_turn` accepts
an optional `rng` so tests can pin rolls.

## Scope

Deliberately tiny:

- No database, no state between sessions, no history.
- No surge/lull bonus calculator (the tag is shown; the GM applies the
  bonus from the book).
- No integration with other tools in `~/src/mytools/`.
