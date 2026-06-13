# RPGBOT Builder — Architecture

## Overview

The builder uses a **static site generator** pattern. The backend is a build-time tool only — the output is a fully self-contained HTML file that requires no server.

```
data/*.json          ← source of truth (edit these)
      │
      ▼  seed.py
rpgbot.db            ← SQLite store
      │
      ▼  build.py
dist/*.html          ← generated output (distribute these)
```

---

## Layers

### Layer 1 — Data model (`data/*.json`)

Each class is a JSON file named `<class-id>.json` (e.g. `rogue-2024.json`). This is the only file you edit when updating content.

The file contains:
- **`name`**, **`edition`** — metadata used as DB columns and injected into the page title
- **`ui`** — UI configuration for the template (skill pick count, expertise flag, section titles, callout text)
- **All content arrays** — `subclasses`, `species`, `feats`, `epicBoons`, `classFeatures`, etc.

The JSON file is the canonical source. The database and all generated HTML are derived from it.

### Layer 2 — Database (`rpgbot.db`)

A single SQLite file with one table:

```sql
CREATE TABLE classes (
    id      TEXT PRIMARY KEY,   -- 'rogue-2024'
    name    TEXT NOT NULL,      -- 'Rogue'
    edition TEXT NOT NULL,      -- '2024'
    data    TEXT NOT NULL       -- full JSON blob
);
```

`seed.py` populates this from `data/`. The `name` and `edition` columns are denormalized for easy listing without parsing JSON. Everything else is in `data`.

### Layer 3 — Template (`builder.html`)

A vanilla JS single-page app with **no embedded class data**. At load time it either:
- **Dev mode** (served by `app.py`): fetches `/api/classes/{id}` and calls `init(D)`
- **Build mode** (generated file): `const D = <json>;` is already present, calls `init()` directly

The template is completely generic — the same HTML renders any class. All class-specific text (section titles, callout copy, skill pick counts) flows in from `D.ui` inside `init()`.

### Layer 4 — Generator (`build.py`)

Makes two string substitutions on `builder.html`:

| What | Before | After |
|------|--------|-------|
| Data declaration | `let D = null;` | `const D = <json from DB>;` |
| Bootstrap block | `// ─── Bootstrap` → end of `<script>` | `init();` |

The result is a self-contained HTML file. No fetch, no server dependency.

---

## Dev server (`app.py`)

FastAPI application that:
- Serves `builder.html` and all static files from the project root
- Exposes `GET /api/classes` (list) and `GET /api/classes/{id}` (full data + injected `meta`)
- Redirects `/` to `/builder.html?class=rogue-2024`

The dev server is only needed during authoring. It reads from `rpgbot.db` at request time so `seed.py` changes take effect immediately on refresh.

```
http://127.0.0.1:5110/builder.html?class=rogue-2024
```

---

## Template internals

### State

```javascript
const S = {
  subclass:   null,   // selected subclass name
  species:    null,   // selected species name
  abilityArr: null,   // index into D.arrays
  skills:     {},     // { skillName: 0|1|2|3 }  (0=none, 1=prof, 2=e1, 3=e2)
  bg:         null,   // selected background name
  asi:        {},     // { level: { type: 'feat'|'asi2'|'split', feat: name|null } }
  fFilt:      'all',  // feat rating filter
  fSearch:    '',     // feat search string
};
```

### Render flow

`init()` is the entry point. It applies `D.ui` settings, updates dynamic header text, and calls each render function once. Subsequent interactions call the affected render functions directly via event listeners — there is no reactive framework or virtual DOM.

### Skill cycling

Skills have four states: `0` (none) → `1` (proficient) → `2` (L1 expertise) → `3` (L6 expertise) → `0`. Transitions are gated:
- 0→1: only if `skCount() < D.ui.skillPicks`
- 1→2: only if `e1Count() < 2` AND `D.ui.hasExpertise`
- 2→3: only if `e2Count() < 2`

### ASI / Feat assignment

Two-step interaction:
1. Click "Take a Feat" on an ASI slot → `S.asi[level] = { type: 'feat', feat: null }`
2. Click "Assign to Lvl X" on a feat card → `S.asi[level].feat = featName`

Open slots (type=feat, feat=null) are tracked by `openSlots()` and surface assignment buttons on every feat card.

### Feat grouping

Feats are split into three visual sections rendered by `renderFeatGroup(cat)`:
- `"origin"` — granted by Background, don't use an ASI slot
- `"general"` — fill ASI slots
- `"dragonmark"` — Eberron-only, campaign-specific

Epic Boons are a separate array (`D.epicBoons`) on their own tab, not mixed with feats.

---

## Data schema reference

### `D.ui`

| Field | Type | Description |
|-------|------|-------------|
| `skillPicks` | number | How many class skills the player chooses (Rogue: 4, most: 2) |
| `hasExpertise` | boolean | Whether to show the expertise cycling UI |
| `optionalTitle` | string | Header for the sub-options section in Class Features tab |
| `optionalDesc` | string | Subheader for the sub-options section |
| `subclassDesc` | string | Pane subtitle for the Subclass tab |
| `featDesc` | string | Pane subtitle for the Feats & ASIs tab |
| `backgroundNote` | string | Callout text in the Background tab |
| `multiclassNote` | string | Callout text in the Multiclassing tab |
| `weaponNote` | string | Subtitle for the Weapons section |
| `armorNote` | string | Subtitle for the Armor section |

### Card shape (shared by most arrays)

```json
{ "n": "Name", "r": "blue|green|orange|red", "d": "Description." }
```

### Feat card (adds `cat`)

```json
{ "n": "Lucky", "r": "blue", "cat": "origin", "d": "Description." }
```

### Class feature card (adds `lv`)

```json
{ "lv": 1, "n": "Sneak Attack", "r": "blue", "d": "Description." }
```

### Weapon card (adds `mastery` and `props`)

```json
{ "n": "Dagger", "mastery": "Nick", "props": "Finesse · Light · Thrown", "r": "blue", "d": "Description." }
```

### Ability score array

```json
{ "n": "Standard Build — Point Buy", "v": { "Str": 8, "Dex": 17, "Con": 15, "Int": 10, "Wis": 14, "Cha": 8 } }
```

### Ability note

```json
{ "s": "Dex", "r": "blue", "n": "Your primary ability." }
```

---

## Adding a new class checklist

- [ ] Create `data/<class-id>.json` with all required keys
- [ ] Set `ui.skillPicks` (2 for most classes, 4 for Rogue)
- [ ] Set `ui.hasExpertise` (true for Rogue and Bard, false for most)
- [ ] Set `ui.optionalTitle` to match the sub-choice type (Fighting Styles, Metamagic, etc.)
- [ ] Run `python3 seed.py <class-id>`
- [ ] Run `python3 build.py <class-id>`
- [ ] Open `dist/<class-id>-builder.html` and click through every tab
- [ ] Run the JS validation: `node -e "...new Function(m[1])..."`

---

## Design constraints

- **No frameworks** — vanilla JS only; no React, Vue, or build step
- **No external JS** — Google Fonts `@import` is the only external resource
- **No localStorage** — state is in-memory only; refreshing the page resets the build
- **Single file output** — the generated HTML is the entire application; it must work when opened directly from disk
