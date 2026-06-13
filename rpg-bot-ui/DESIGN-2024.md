# RPGBOT Class Builder — 2024 D&D Design Document

How to build a single-file character builder from an RPGBOT **2024 D&D** class guide.
This document covers what changes compared to `DESIGN.md` (2014 rules). Read both together.

---

## What changed in 2024 D&D (and why it affects the builder)

| System | 2014 | 2024 |
|---|---|---|
| Ability score bonuses | From Race | From Background (+2/+1 or +1/+1/+1) |
| Race/Species | Grants ability score increases | No ability score increases; flavor only |
| Feats | One tier (General) | Three tiers: Origin, General, Epic Boon |
| Optional class features | Tasha's section on the guide | Baked into base class; no separate section |
| Weapon Mastery | Not in base game | Core feature for all martial classes |
| RPGBOT URL | `/dnd5/characters/classes/CLASSNAME/` | `/2024-dnd/classes/CLASSNAME/` |

---

## Step 1: Scrape the guide

The URL pattern is different. Everything else about scraping is the same.

```bash
curl -sL \
  -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120" \
  -H "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8" \
  -H "Accept-Language: en-US,en;q=0.5" \
  -H "Accept-Encoding: identity" \
  "https://rpgbot.net/2024-dnd/classes/CLASSNAME/" \
  -o /tmp/class.html
```

Note `-L` (follow redirects) and `Accept-Encoding: identity` (prevents gzip that confuses output).
Without these flags, Cloudflare may return a partial 583-byte shell instead of the full page.

Strip HTML using the same Python snippet from `DESIGN.md`. The 2024 pages are ~220KB and
produce ~50KB of text — plan two read passes.

---

## Step 2: Extract the data

The sections to extract are the same as `DESIGN.md`, but with these changes:

### Backgrounds (major change)

In 2024, a Background does three things:
1. Sets two ability scores (+2 to one, +1 to another — or +1/+1/+1)
2. Grants an **Origin Feat**
3. Grants skills and/or tool proficiencies

RPGBOT rates backgrounds based on how well the combination of ability scores + feat + skills
fits the class. The guide will typically open the section with:

> "An increase to [key ability] is too crucial to forego, so any Background which doesn't
> include [key ability] is immediately out."

Extract ratings the same way, but note in the card description whether the rating is driven by
ability scores, the feat, or the skills.

**Callout to add in the builder:** "In 2024 D&D, your Background sets ability scores (+2/+1)
and grants an Origin Feat. Prioritize backgrounds that include [class key ability]."

### Ability score arrays

The RPGBOT table shows two columns per variant: **base** and **adjusted**. The adjusted column
includes the +2/+1 Background bonus. Use the **adjusted** values in the builder — those are the
numbers the player actually writes on their sheet.

RPGBOT typically presents 2–3 array variants:
- Point Buy — standard build
- Standard Array — standard build
- PHB Recommended — usually an Intelligence or Charisma-focused caster variant

If the class has a caster subclass or two distinct build paths, there will be a second set of
rows for each variant.

### Feats (major change — three tiers)

2024 RPGBOT guides split feats into four sections. Extract all four:

| Section | In builder as | `cat` field |
|---|---|---|
| Origin Feats | Origin Feat cards | `"origin"` |
| Dragonmark Feats | Skip (Eberron-only, very narrow) | — |
| General Feats | General Feat cards | `"general"` |
| Epic Boons | Epic Boon cards | `"epic"` |

Add a `cat` field to every feat entry. This drives the category filter in the UI.

### Optional class features

There is no "Optional Features (Tasha's)" section in 2024 — those features were either
promoted into the base class or dropped. Repurpose the `optional` array for something else:

- If the class has a "trade resource for rider effects" mechanic (Cunning Strike, Divine Smite
  variants, etc.), use `optional` for the individual sub-options rated on their own merits.
- If the class has nothing equivalent, either remove the section or use it for important
  sub-choices (Fighting Style options, Metamagic options for Sorcerer, etc.).

Update the section header in the HTML from `Optional Features (Tasha's)` to the appropriate
label (e.g., `Cunning Strike Options`, `Fighting Style Options`).

### Weapon Mastery

Most 2024 martial classes (Fighter, Rogue, Paladin, Ranger, Barbarian, Monk) get Weapon
Mastery at level 1. It is a class feature with a fixed rating — add it to `classFeatures`:

```javascript
{lv:1, n:"Weapon Mastery", r:"green", d:"N slots. Key masteries: [list the class's best options]."}
```

The number of slots varies:
- Fighter: 3 slots (most)
- Paladin, Ranger, Rogue: 2 slots
- Barbarian, Monk: 2 slots

RPGBOT usually has a separate Weapon Mastery note in the "Weapons" section. Pull the 2–3 most
important masteries for the class and name them in the description.

---

## Step 3: Encode the data

The JS `D` object shape is the same as `DESIGN.md` with two additions:

```javascript
const D = {
  // ... (subclasses, arrays, abilityNotes, skills, backgrounds same as before)

  // 2024 change: feats now have a `cat` field
  feats: [
    { n: "Lucky",    r: "blue",   cat: "origin",  d: "..." },
    { n: "Skulker",  r: "blue",   cat: "general", d: "..." },
    { n: "Boon of Combat Prowess", r: "blue", cat: "epic", d: "..." },
  ],

  // 2024 change: repurpose optional for sub-choices rather than Tasha's features
  optional: [
    { n: "Cunning Strike: Trip",  r: "green",  d: "..." },
    { n: "Divine Smite: Radiant", r: "blue",   d: "..." },
  ],

  // ASI levels — same shape, but verify per class (some changed in 2024)
  asiLevels: [4, 8, 12, 16, 19],
};
```

### ASI level changes in 2024

Some classes changed their ASI schedule. Verify from the class progression table:

| Class | 2014 ASIs | 2024 ASIs |
|---|---|---|
| Rogue | 4, 8, 10, 12, 16, 19 | 4, 8, 10, 12, 16, 19 (unchanged) |
| Fighter | 4, 6, 8, 12, 14, 16, 19 | 4, 6, 8, 12, 14, 16, 19 (unchanged) |
| Cleric | 4, 8, 12, 16, 19 | 4, 8, 12, 16, 19 (unchanged) |
| Most others | 4, 8, 12, 16, 19 | 4, 8, 12, 16, 19 (unchanged) |

The schedule didn't change in 2024 for any class. Confirm anyway from the table in the guide.

---

## Step 4: Adapt the HTML template

Copy `rogue2024-builder.html` rather than `index.html` as your starting point — it already
has the 2024-specific UI additions. Then:

1. Replace the `const D = { ... }` block with your new class data
2. Update the `<title>` and header subtitle
3. Update the subclass tab description (archetype level varies by class)
4. Update the "optional" section header to match your sub-choice type
5. Adjust skill pick count if needed (most classes get 2, not 4)
6. Remove expertise UI for classes that don't have it (see below)

### Per-class UI adjustments

| Feature | What to change |
|---|---|
| Skill picks ≠ 4 | In the click handler: `skCount()<4` → `skCount()<N` |
| No expertise | Remove the `e1`/`e2` counter bar items; simplify cycling to 0→1→0 only; remove expertise rows from Summary |
| Weapon Mastery slots | Add to classFeatures; no separate UI needed unless the class has a unique selection mechanic |
| Sub-choice type (Fighting Style, Metamagic, etc.) | Update `D.optional` array + the HTML section header |
| Spell tabs (casters) | Add `spells` array + a Spells tab; separate cantrips from leveled spells |

### Class-specific sections to add

| Class | Extra data/tabs |
|---|---|
| Wizard / Sorcerer / Bard | Spells tab (school + level fields); Cantrips tab |
| Paladin / Ranger | Spells tab; Fighting Style sub-choices in `optional` |
| Fighter | Fighting Style in `optional`; Second Wind / Action Surge in `classFeatures` |
| Cleric | Subclass header = "Divine Domain"; no expertise |
| Sorcerer | Sorcery Points section; Metamagic in `optional` |
| Monk | Ki/Focus Points costs per feature; note in classFeature descriptions |

---

## Step 5: 2024-specific UI additions (already in rogue2024-builder.html)

These are already implemented in the template. Understand what each does:

### Feat category filter

The filter bar now has two rows of buttons:
- Rating row: All | Fantastic | Good | Situational | Avoid
- Category row: All Types | Origin | General | Epic Boon

Driven by `S.fCat` state and the `cat` field on each feat. If you add categories
(e.g., "Dragonmark"), add a button and a new `cat` value.

```javascript
S.fCat = 'all';  // add to state

// In filter: skip feat if category doesn't match
if (S.fCat !== 'all' && f.cat !== S.fCat) return false;
```

### Feat category chip in cards

Cards for Origin Feats and Epic Boons show a small label below the name.
General feats show nothing (they're the default).

```javascript
const catLabel = { origin: 'Origin Feat', epic: 'Epic Boon' };
const catChip = catLabel[f.cat]
  ? `<div class="card-cat">${catLabel[f.cat]}</div>` : '';
```

### Background callout

The background tab has a callout explaining the 2024 mechanic. Update the key ability name
for each class:

```html
<div class="callout">
  <strong>Rule:</strong> Any Background that doesn't increase [KEY ABILITY] is immediately out.
  The Origin Feat from your Background is one of your most important choices.
</div>
```

### Ability scores note

Update the ability tab subtitle to clarify that arrays shown are post-background-adjusted:

```html
<p>Values shown are after Background bonuses (+2/+1). Click an array to preview.</p>
```

---

## Step 6: Rating inference for 2024 guides

RPGBOT's color coding is the same. But 2024 guides often use more explicit color calls:
- "Blue" / "blue" appears in the text for fantastic options
- "Orange" / "orange" for situational

For sections without explicit colors (backgrounds are common), infer from prose:
- "Perfect for...", "Absolutely fantastic...", "God [scores]..." → blue
- "Good...", "works well...", "decent..." → green  
- "could work...", "situationally...", "hard to justify..." → orange
- "Bad...", "useless...", "never...", "you should not..." → red

Background ratings in 2024 guides are unusually blunt. RPGBOT will often say
"Bad ability scores, bad feat, bad skills" for an immediate red call.

---

## Workflow checklist (2024)

- [ ] Curl with `-sL` and `Accept-Encoding: identity` flags
- [ ] Strip HTML, read text in two passes (first 18k chars, then rest)
- [ ] Extract 4 subclasses (2024 PHB has far fewer than 2014)
- [ ] Extract ability arrays — use the **Adjusted** columns from the table
- [ ] Extract per-stat notes and ratings
- [ ] Extract skill list with ratings (note any 2024 rule changes in descriptions)
- [ ] Extract backgrounds — note that ratings are driven by ability scores + feat + skills together
- [ ] Extract **Origin Feats** (from Background section and top of Feats section)
- [ ] Extract **General Feats** (largest section)
- [ ] Extract **Epic Boons** (end of Feats section — often 10–15 options)
- [ ] Skip Dragonmark Feats (Eberron-specific, include only if campaign warrants it)
- [ ] Extract class features — note level changes from 2014 (e.g., Reliable Talent → level 7)
- [ ] Identify the "trade resource for rider effects" mechanic and extract sub-options for `optional`
- [ ] Note ASI levels from class progression table
- [ ] Note Weapon Mastery slot count and key mastery options
- [ ] Copy `rogue2024-builder.html` to `CLASSNAME-builder.html`
- [ ] Replace `const D = { ... }` block
- [ ] Update title, header subtitle, subclass tab description
- [ ] Update "optional" section header in HTML
- [ ] Adjust skill pick count if not 4; remove expertise UI if class lacks it
- [ ] Add class-specific tabs if needed (Spells, Fighting Style, etc.)
- [ ] Open in browser, click every tab, verify counters and status bar
- [ ] Run: `node -e "const h=require('fs').readFileSync('CLASSNAME-builder.html','utf8');const m=h.match(/<script>([\s\S]*?)<\/script>/);new Function(m[1]);console.log('OK')"`

---

## Key 2024 rule changes that affect RPGBOT ratings

These shift which options RPGBOT rates highly — good to know when inferring ratings from prose:

- **Sleight of Hand** picks locks in 2024 (was Thieves' Tools only). Often rated higher than 2014.
- **Two-weapon fighting** works differently — the Light property triggers the bonus attack, not the action. Nick mastery gives a free attack. This affects feat recommendations.
- **Steady Aim** is a core class feature (not optional) for Rogues — affects its rating.
- **Spell save DC** now uses the ability score that powers the spell, not a fixed stat. True Strike (uses any mental stat) enables Int-based caster builds on non-caster classes.
- **Backgrounds grant Origin Feats** — feats that used to be mediocre (Magic Initiate, Lucky, Musician) are now "effectively free" and therefore rated higher because they don't cost an ASI slot.
- **Epic Boons** are new — RPGBOT typically rates them for the specific class on the class guide page, which is new content not in the 2014 guides.
