# flexai-social

A GM tool that implements the **FlexAI for Social Encounters** rules from the
*FlexAI Guidebook* (Infinium Game Studios, 2020), pages 260–265, driven by the
two Digital Resource Companion spreadsheets.

Pick a Role × Size × Context × Rank, see which PC Choices are available and
their DCs (5E or PF2e), roll the NPC's turn in the conversational volley, and
resolve PC attempts against the appropriate success/failure result table.

- [`RULES.md`](RULES.md) — verbatim rules text extracted from the Guidebook pp. 260–265.
- [`flexai_social.py`](flexai_social.py) — workbook loader and resolver library.
- [`app.py`](app.py) — Flask web UI on port 5105.
- [`test_flexai_social.py`](test_flexai_social.py) — pytest suite (tiny fixture workbooks, no commercial data shipped).

## Quickstart

```bash
pip install -r requirements.txt
python3 app.py
# open http://localhost:5105
```

## Data files

The tool reads two xlsx files from the FlexAI Digital Resource Companion:

```
FlexAI_Social_2021_01_04.xlsx              # NPC turn + success/failure results
FlexAI_Social_Choice_DCs_2021_01_04.xlsx   # DCs per Role × Size × Context × Rank
```

These are **commercial content** and are never committed to this repo.

The data directory is resolved in this order:

1. `--data-dir PATH` on the `app.py` command line.
2. `FLEXAI_DATA_DIR` environment variable.
3. Hard-coded default:
   `/mnt/g/My Drive/DriveThru/Infinium Game Studios/FlexAI Digital Resource Companion (unisystem_5E_Pathfinder_P2E_OSR)/`

The server prints the resolved path at startup so a wrong location is obvious.

### Known data gap

The DC workbook ships with DCs for **Ally, Asset, Opponent, Bystander** but
not **Acquaintance**. The Acquaintance role is fully usable for NPC-turn rolls
and result rolls, but every DC shows as `—` (auto-fail) in the UI. Use the
"Starting Points" guidance on p. 261 to improvise DCs when playing
Acquaintance encounters.

## Running tests

```bash
pytest -v
```

Tests build tiny synthetic workbooks into `tmp_path` via
[`fixtures/build_fixtures.py`](fixtures/build_fixtures.py) — no real
commercial xlsx files are required or shipped.

You can also regenerate the fixture workbooks on disk (for manual inspection):

```bash
python3 fixtures/build_fixtures.py
```

## CLI reference

```bash
python3 app.py [--data-dir PATH] [--host HOST] [--port 5105] [--debug]
```

| Flag           | Default                                  |
|----------------|------------------------------------------|
| `--data-dir`   | `$FLEXAI_DATA_DIR` or hard-coded default |
| `--host`       | `127.0.0.1`                              |
| `--port`       | `5105`                                   |
| `--debug`      | off                                      |

## Architecture

```
flexai_social.py                 # library — no Flask, no HTTP
    load_tables(data_dir)        # read both workbooks → nested dict
    get_cell(table, R, S, C, r)  # look up one FlexCell
    available_choices(cell, system)
    roll_npc_turn(cell, rng=...)
    roll_result(cell, success, rng=...)
    attempt(cell, choice, pc_total, system, rng=...)

app.py                           # Flask UI — thin wrapper
    create_app(table=..., data_dir=...)
    routes: /  /api/cell  /api/roll/npc-turn  /api/roll/result  /api/attempt  /rules
```

The library is deterministic and RNG-injectable — `attempt()` takes an
optional `rng` so tests can pin rolls.

## Scope

This tool is intentionally tiny:

- No database, no state between sessions, no history.
- No dice modifier UI beyond a single "PC total" number input.
- No integration with other tools in `~/src/mytools/`.

All of those are reasonable follow-ups, but bloat the initial build.
