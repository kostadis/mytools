# RPGBOT Class Builder

Single-file interactive character builders for D&D 2024, generated from structured class data scraped from [RPGBOT](https://rpgbot.net/2024-dnd/classes/).

Each output file is a self-contained HTML page that works offline with no backend. Open it in a browser and it's ready.

---

## Quick start

```bash
# Open the pre-built Rogue builder directly
open dist/rogue-2024-builder.html   # macOS
xdg-open dist/rogue-2024-builder.html  # Linux
```

Or just drag `dist/rogue-2024-builder.html` into your browser.

---

## Adding a new class

### 1. Scrape the class guide

```bash
curl -sL \
  -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120" \
  -H "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8" \
  -H "Accept-Language: en-US,en;q=0.5" \
  -H "Accept-Encoding: identity" \
  "https://rpgbot.net/2024-dnd/classes/CLASSNAME/" \
  -o /tmp/class.html
```

Strip HTML to readable text:

```python
import re

with open('/tmp/class.html') as f:
    html = f.read()

for tag in ['script','style','nav','header','footer']:
    html = re.sub(rf'<{tag}[^>]*>.*?</{tag}>', '', html, flags=re.DOTALL)

m = re.search(r'<article[^>]*>(.*?)</article>', html, re.DOTALL)
content = m.group(1) if m else html
content = re.sub(r'<(h[1-6]|p|li|br|div|tr)[^>]*>', '\n', content)
content = re.sub(r'<[^>]+>', '', content)
content = re.sub(r'&nbsp;', ' ', content)
content = re.sub(r'\n\s*\n+', '\n\n', content)

print(content[:20000])   # read in passes — guides are ~50KB of text
```

### 2. Create the data file

Create `data/CLASSNAME-2024.json`. See `data/rogue-2024.json` for the full schema, and `DESIGN-2024.md` for extraction guidance. Required top-level keys:

| Key | Description |
|-----|-------------|
| `name` | Display name, e.g. `"Fighter"` |
| `edition` | `"2024"` |
| `ui` | UI config object (skill picks, expertise flag, section titles) |
| `subclasses` | Array of subclass cards |
| `species` | Array of species cards |
| `arrays` | Recommended ability score arrays |
| `abilityNotes` | Per-stat priority notes |
| `skills` | Class skill list with ratings |
| `backgrounds` | Background options with ratings |
| `feats` | Feats with `cat` field: `"origin"`, `"general"`, or `"dragonmark"` |
| `epicBoons` | Epic Boon options |
| `classFeatures` | Class features by level |
| `optional` | Sub-options (Cunning Strike effects, Fighting Styles, Metamagic, etc.) |
| `asiLevels` | Array of levels that grant ASI/feat choices |
| `weapons` | Weapon options with mastery ratings |
| `armor` | Armor options |
| `multiclass` | Multiclass dip ratings |

### 3. Seed the database

```bash
python3 seed.py CLASSNAME-2024
```

### 4. Generate the builder

```bash
python3 build.py CLASSNAME-2024
# → dist/CLASSNAME-2024-builder.html
```

### 5. Verify

Open `dist/CLASSNAME-2024-builder.html` in a browser. Click through every tab and check counters.

Also verify the JS is clean:

```bash
node -e "
const fs=require('fs');
const html=fs.readFileSync('dist/CLASSNAME-2024-builder.html','utf8');
const m=html.match(/<script>([\s\S]*?)<\/script>/);
new Function(m[1]);
console.log('OK');
"
```

---

## Updating existing data

```bash
# 1. Edit the JSON source
vim data/rogue-2024.json

# 2. Push to database
python3 seed.py rogue-2024

# 3. Regenerate
python3 build.py rogue-2024
# dist/rogue-2024-builder.html is updated
```

---

## Dev server (live preview)

The `builder.html` template can be served live so you see changes without rebuilding.

```bash
# Install dependencies (once)
pip install -r requirements.txt

# Start server on http://127.0.0.1:5110
./service.sh start

# Open live preview
open "http://127.0.0.1:5110/builder.html?class=rogue-2024"

# Stop server
./service.sh stop
```

Other service commands: `restart`, `status`, `logs [N]`, `tail`.

The live server reads the database at request time, so you can `seed.py` a change and refresh without restarting.

---

## Files

| File | Purpose |
|------|---------|
| `data/*.json` | Class data (edit these) |
| `rpgbot.db` | SQLite store seeded from `data/` |
| `builder.html` | Generic template — no embedded data |
| `build.py` | Generator — produces self-contained HTML from DB |
| `seed.py` | Loads `data/*.json` into `rpgbot.db` |
| `app.py` | FastAPI dev server |
| `service.sh` | Start/stop the dev server |
| `dist/*.html` | Generated output files (open directly in browser) |
| `rogue2024-builder.html` | Standalone reference builder (data embedded) |
| `DESIGN.md` | Extraction guide for 2014 D&D guides |
| `DESIGN-2024.md` | Extraction guide for 2024 D&D guides |

---

## Rating system

RPGBOT uses a four-color rating scale, mapped here to:

| Color | Meaning |
|-------|---------|
| Blue ★★★★ | Fantastic — often essential |
| Green ★★★ | Good — reliably useful |
| Orange ★★ | Situational — sometimes useful |
| Red ★ | Avoid — rarely worth it |
