# RPGBOT Class Builder — Design Document

How to build a single-file character builder from an RPGBOT class guide.
Repeat this process for each class.

---

## Step 1: Scrape the guide

RPGBOT returns 403 to automated fetchers. Use curl with a browser user-agent:

```bash
curl -s \
  -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120" \
  "https://rpgbot.net/dnd5/characters/classes/CLASSNAME/" \
  > /tmp/class.html
```

Then strip HTML to readable text:

```python
import re, sys

with open('/tmp/class.html') as f:
    html = f.read()

for tag in ['script','style','nav','header','footer']:
    html = re.sub(rf'<{tag}[^>]*>.*?</{tag}>', '', html, flags=re.DOTALL)

m = re.search(r'<article[^>]*>(.*?)</article>', html, re.DOTALL)
content = m.group(1) if m else html

content = re.sub(r'<(h[1-6]|p|li|br|div|tr)[^>]*>', '\n', content)
content = re.sub(r'<[^>]+>', '', content)
content = re.sub(r'&nbsp;', ' ', content)
content = re.sub(r'&[a-z]+;', '', content)
content = re.sub(r'\n\s*\n+', '\n\n', content)

print(content[:20000])   # first pass
print(content[20000:])   # second pass if needed
```

---

## Step 2: Extract the data

From the text, pull these sections. Each item needs a **name**, **rating**, and **note**.

### Sections to extract

| Section | What to look for |
|---|---|
| Subclasses | "Roguish Archetype" / "Archetypes" block. Short description per subclass. Ratings usually on a separate subclass guide page — use the context clues in the main text ("I rate orange/red") or leave as `null` and fill in later. |
| Ability scores | The recommendation table near "Ability Scores". Usually two build variants (e.g. typical vs. caster subclass), each with Point Buy and Standard Array columns. |
| Ability score notes | The per-stat paragraphs (Str, Dex, Con, Int, Wis, Cha). Each has a rating and a short explanation. |
| Skills | The "Skills" section. Each skill has a rating and a short note. |
| Backgrounds | The "Backgrounds" section. Each has a rating and a note. |
| Feats | The "Feats" section. Each has a rating and a note. Long — scan for "Blue:", "Green:", "Orange:", "Red:" markers or infer from the tone of the prose. |
| Class features | The "Class Features" section near the top. Each feature has a level, a rating, and a note. |
| Optional features | The "Optional Class Features" section (Tasha's additions). |
| ASI levels | The class progression table. Rogues: 4, 8, 10, 12, 16, 19. Fighters: 4, 6, 8, 12, 14, 16, 19. Varies by class. |

### Rating mapping

RPGBOT uses a color system. Map it to these four keys:

| Color | Key | Meaning |
|---|---|---|
| Blue | `"blue"` | Fantastic — often essential |
| Green | `"green"` | Good — reliably useful |
| Orange | `"orange"` | Situational — sometimes useful |
| Red | `"red"` | Avoid — rarely or never useful |

When the text says "Going first is great for Rogues" without naming a color, infer the rating from the tone:
- Enthusiastic / "essential" / "crucial" → blue
- "good" / "helpful" / "decent" → green
- "situational" / "tempting but" / "only if" → orange
- "bad" / "useless" / "leave for" / "not worth" → red

---

## Step 3: Encode the data

The JS data object for each class follows this shape:

```javascript
const D = {
  // Pick one at level 3 (or wherever the class gets its archetype)
  subclasses: [
    { n: "Name", r: "blue|green|orange|red", d: "One-sentence description." },
  ],

  // Recommended ability score arrays (typically 2–4 variants)
  arrays: [
    { n: "Most <Class> — Point Buy",       v: { Str:8, Dex:15, Con:14, Int:11, Wis:12, Cha:12 } },
    { n: "Most <Class> — Standard Array",  v: { Str:8, Dex:15, Con:14, Int:10, Wis:13, Cha:12 } },
    // add caster-variant if the class has one
  ],

  // Short note + rating for each of the six stats
  abilityNotes: [
    { s: "Str", r: "red",    n: "Why it matters or doesn't." },
    { s: "Dex", r: "blue",   n: "..." },
    { s: "Con", r: "green",  n: "..." },
    { s: "Int", r: "orange", n: "..." },
    { s: "Wis", r: "orange", n: "..." },
    { s: "Cha", r: "green",  n: "..." },
  ],

  // Class skill list with ratings
  skills: [
    { n: "Perception", s: "Wis", r: "blue", d: "Most important skill in the game." },
    // ...
  ],

  // Background options with ratings
  backgrounds: [
    { n: "Criminal", r: "blue", d: "Two key class skills plus tool kits." },
    // ...
  ],

  // Feats with ratings (sorted blue → green → orange → red for readability)
  feats: [
    { n: "Feat Name", r: "blue", d: "Why it's good or bad." },
    // ...
  ],

  // Class features by level
  classFeatures: [
    { lv: 1,  n: "Feature Name", r: "blue", d: "Short note." },
    // ...
  ],

  // Optional/Tasha's features
  optional: [
    { n: "Feature Name", r: "green", d: "Description." },
  ],

  // Levels at which this class gets ASI/feat choices
  // Fighter: [4,6,8,12,14,16,19]  Rogue: [4,8,10,12,16,19]
  // Most classes: [4,8,12,16,19]
  asiLevels: [4, 8, 12, 16, 19],
};
```

### Class-specific adjustments

Some classes need extra data sections:

| Class | Extra sections |
|---|---|
| Wizard / Sorcerer / Bard | Spells section — same card pattern, but add `school` and `level` fields. Add a Spells tab. |
| Paladin / Ranger | Both a spell list and a Fighting Style choice at level 2. |
| Fighter | Fighting Style at level 1. Action Surge / Second Wind class features matter a lot. |
| Cleric | Domain list instead of subclasses. |
| Druid | Wild Shape progression is important — consider adding a table. |
| Monk | Ki point costs are worth noting per feature. |

---

## Step 4: Copy and adapt the HTML template

1. Copy `index.html` to a new file: `<classname>-builder.html`
2. Replace the `const D = { ... }` block with your new class data
3. Update the header title and subtitle
4. Adjust the **Skills tab** if the class gets a different number of skill picks (Rogues get 4; most classes get 2)
5. Adjust the **Expertise tab** if the class doesn't have expertise (remove that UI)
6. Adjust **ASI levels** (`D.asiLevels`)

### Class-specific UI adjustments

| Feature | Code to change |
|---|---|
| Skill pick count (e.g. 2 for most classes) | `skCount()<4` → `skCount()<2` in the click handler |
| No expertise | Remove the `e1`/`e2` counter bar items; remove the cycling logic past state 1; remove L1/L6 expertise from the summary |
| Fighting Style | Add a `fightingStyles` array and a Fighting Style tab or inline picker |
| Spell slots | Add a `spells` array; add a Spells tab with level filter |
| Cantrips | Same as spells but separate array, no slot cost |

---

## Step 5: UI architecture notes

The template is a single HTML file with no build step or dependencies beyond a Google Fonts import.

### Key patterns

**Card grid** — the primary UI unit. Every selectable option is a `.card` in a `.grid`. Cards have:
- `.card-top`: name (left) + rating badge (right)
- `.card-note`: description text
- Optional state indicator below the note

**State cycling (skills)** — each skill card cycles through 0 → 1 → 2 → 3 → 0 on click. The limits (4 skills, 2 per expertise tier) are enforced at transition time, not at render time.

**ASI + feat assignment** — two-step interaction:
1. Click "Take a Feat" on an ASI slot → opens the slot
2. Click "Assign to Lvl X" on a feat card → links them

**Status bar** — fixed at the bottom, shows key choices at all times without taking content space.

**Tab badges** — appear on tabs when that section has selections, using the `.tbadge` class.

### Rating badge CSS

All four rating colors are CSS variables. To change the color scheme, edit only these vars in `:root`:

```css
--rb: #1e40af; --rb-bg: #0c1a35; --rb-t: #93c5fd;   /* blue */
--rg: #15803d; --rg-bg: #0a2416; --rg-t: #86efac;   /* green */
--ro: #c2410c; --ro-bg: #2c1005; --ro-t: #fdba74;   /* orange */
--rr: #b91c1c; --rr-bg: #280606; --rr-t: #fca5a5;   /* red */
```

### Fonts

- `Cinzel` — headings, labels, tab text (classical serif, feels like engraved stone)
- `Crimson Pro` — body text, card notes (readable serif)
- `JetBrains Mono` — numeric counters, stat values, level pills

To change the theme, swap these three. The font pairing (display serif + body serif + monospace) is the main aesthetic driver.

---

## Workflow checklist

- [ ] Curl the class page
- [ ] Strip HTML and read the text in two passes (first 15k and next 15k chars)
- [ ] Extract subclasses with descriptions
- [ ] Extract ability score arrays (usually 2–4 variants in a table)
- [ ] Extract per-stat notes and ratings
- [ ] Extract skill list with ratings
- [ ] Extract backgrounds with ratings
- [ ] Extract feats with ratings (longest section — 30–40 feats typical)
- [ ] Extract class features by level with ratings
- [ ] Extract optional/Tasha's features
- [ ] Note ASI levels from the class progression table
- [ ] Copy `index.html` and swap the data block
- [ ] Adjust skill count limit if not 4
- [ ] Remove or add expertise UI as needed
- [ ] Add class-specific sections (spells, fighting styles, etc.)
- [ ] Open in browser and click through each tab
