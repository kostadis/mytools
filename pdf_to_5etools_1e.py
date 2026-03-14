#!/usr/bin/env python3
"""
pdf_to_5etools_1e.py
====================
Specialised converter for 1st/2nd Edition AD&D module PDFs → 5etools JSON.

Designed for classic TSR modules such as:
  T1-4  Temple of Elemental Evil
  B2    Keep on the Borderlands
  S1    Tomb of Horrors
  A1-4  Slave Lords series
  GDQ   Giants/Drow/Queen of Spiders

Key capabilities beyond the base OCR converter
-----------------------------------------------
1.  Recognises 1e keyed-room structure (numbered area entries).
2.  Detects inline stat blocks (AC N; MV N"; HD N; THAC0 N; #AT N; D N-N).
3.  Detects named-NPC blocks with ability scores.
4.  Tags wandering-monster tables.
5.  Converts 1e → 5e stat blocks:
      - Descending AC   → 5e ascending AC   (19 − 1e_AC)
      - THAC0           → attack bonus      (20 − THAC0)
      - MV in inches    → feet              (MV × 5)
      - Hit Dice        → approximate CR    (table lookup)
      - Ability scores  → estimated or copied from NPC blocks

Dependencies
------------
    pip install pymupdf anthropic pytesseract pillow pdf2image
    sudo apt install tesseract-ocr tesseract-ocr-eng poppler-utils

Usage
-----
    python3 pdf_to_5etools_1e.py <input.pdf> [options]

1e-specific options (all standard options also apply)
------------------------------------------------------
    --module-code CODE     TSR module code, e.g. "T1-4" (default: from filename)
    --system {1e,2e}       AD&D edition (default: 1e; 2e uses same stat format)
    --skip-pages RANGE     Skip pages, e.g. "1-3" or "127" (repeatable)
    --no-cr-adjustment     Disable CR bump for special abilities
    --dpi N                Render DPI for OCR pages (default: 400)
    --force-ocr            OCR every page (recommended for scanned modules)
    --lang LANG            Tesseract language code (default: eng)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import textwrap
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

# ── Hard dependencies ────────────────────────────────────────────────────────
try:
    import fitz  # PyMuPDF
except ImportError:
    sys.exit("PyMuPDF required:  pip install pymupdf")

try:
    import anthropic
except ImportError:
    sys.exit("anthropic required:  pip install anthropic")

try:
    import pytesseract
    from PIL import Image, ImageFilter, ImageEnhance
    from pdf2image import convert_from_path
except ImportError:
    sys.exit(
        "OCR packages required:\n"
        "    pip install pytesseract pillow pdf2image\n"
        "    sudo apt install tesseract-ocr tesseract-ocr-eng poppler-utils"
    )


def normalise_path(raw: str) -> Path:
    r"""Accept Windows, WSL-mount, or Unix paths."""
    s = raw.strip().strip('"\'')
    m = re.match(r'^([A-Za-z]):[/\\](.*)', s)
    if m:
        drive = m.group(1).lower()
        rest  = m.group(2).replace('\\', '/')
        s = f'/mnt/{drive}/{rest}'
    return Path(s).expanduser().resolve()


# ── Constants ────────────────────────────────────────────────────────────────

DEFAULT_MODEL     = "claude-haiku-4-5-20251001"
DEFAULT_CHUNK     = 3      # smaller chunks: 1e pages are information-dense
DEFAULT_DPI       = 400    # higher DPI for aged/scanned modules
MIN_DIGITAL_CHARS = 50
MAX_CHUNK_CHARS   = 14_000
COLUMN_GAP_RATIO  = 0.15   # T1-4 has narrow columns — lower threshold
TESS_CONFIG       = r"--oem 3 --psm 1"


# ── 1e stat-detection regex patterns ─────────────────────────────────────────

# Room key: "17." or "17)" or "17:" optionally followed by an ALL-CAPS title
ROOM_KEY_RE = re.compile(
    r'^(\d{1,3})[.:)]\s{1,4}([A-Z][A-Z0-9 \',\-]{0,70})?$'
)

# Lines that carry 1e stat tokens (need at least two distinct tokens)
_STAT_TOKENS = re.compile(
    r'(?:(?<!\w)AC(?!\w)|(?<!\w)MV(?!\w)|(?<!\w)HD(?!\w)|'
    r'(?<!\w)THAC0(?!\w)|(?<!\w)#AT(?!\w)|'
    r'(?:hp|HP)\s*\d|(?:XP\s*\d))',
    re.IGNORECASE,
)

# Ability-score line for NPCs: "S: 15  I: 12  W: 17  ..."
ABILITY_LINE_RE = re.compile(
    r'\b(?:Str|S):\s*\d{1,2}.*?\b(?:Dex|D):\s*\d{1,2}',
    re.IGNORECASE,
)

# Wandering/random encounter table header
WANDER_RE = re.compile(r'\b(WANDERING|RANDOM)\s+(MONSTER|ENCOUNTER)', re.IGNORECASE)


# ── 1e → 5e conversion helpers ───────────────────────────────────────────────

def ac_1e_to_5e(ac_1e: int) -> int:
    """Convert 1e descending AC to 5e ascending AC.  Formula: 19 - 1e_AC."""
    return max(9, 19 - ac_1e)


def thac0_to_attack_bonus(thac0: int) -> int:
    """Convert THAC0 to a 5e attack bonus.  Formula: 20 - THAC0."""
    return 20 - thac0


def mv_to_5e_speed(mv_inches: float) -> int:
    """Convert 1e MV (inches) to 5e speed in feet.  MV × 5, rounded to 5."""
    raw = mv_inches * 5
    return max(5, round(raw / 5) * 5)


# Hit Dice → approximate CR (sorted list of (max_hd_exclusive, cr_string))
_HD_CR_TABLE: list[tuple[float, str]] = [
    (0.5,  "0"),
    (1.0,  "1/8"),
    (1.5,  "1/4"),
    (2.5,  "1/2"),
    (3.5,  "1"),
    (4.5,  "2"),
    (5.5,  "3"),
    (6.5,  "4"),
    (7.5,  "5"),
    (9.0,  "6"),
    (11.0, "8"),
    (13.0, "10"),
    (16.0, "13"),
    (20.0, "17"),
    (float("inf"), "21"),
]

def hd_to_cr(hd: float) -> str:
    """Look up approximate 5e CR from 1e HD value."""
    for max_hd, cr in _HD_CR_TABLE:
        if hd < max_hd:
            return cr
    return "21"


def post_process_monster_1e(monster: dict, no_cr_adjustment: bool = False) -> dict:
    """
    Validate and correct numeric fields on a monster dict produced by Claude.

    - Re-derives AC if a '1e_ac' hint field is present.
    - Re-derives attack bonus if 'thac0' hint is present.
    - Re-derives speed if 'mv_inches' hint is present.
    - Re-derives CR if 'hd' hint is present (unless --no-cr-adjustment).
    - Removes hint fields before returning.
    """
    hints = {k: monster.pop(k, None)
             for k in ("_1e_ac", "_thac0", "_mv_inches", "_hd", "_has_special")}

    if hints["_1e_ac"] is not None:
        try:
            computed = ac_1e_to_5e(int(hints["_1e_ac"]))
            monster["ac"] = [computed]
        except (ValueError, TypeError):
            pass

    if hints["_thac0"] is not None:
        try:
            bonus = thac0_to_attack_bonus(int(hints["_thac0"]))
            monster.setdefault("_attack_bonus_hint", bonus)
        except (ValueError, TypeError):
            pass

    if hints["_mv_inches"] is not None:
        try:
            speed = mv_to_5e_speed(float(hints["_mv_inches"]))
            monster["speed"] = {"walk": speed}
        except (ValueError, TypeError):
            pass

    if hints["_hd"] is not None and not no_cr_adjustment:
        try:
            hd_val = float(hints["_hd"])
            cr = hd_to_cr(hd_val)
            # If the monster has special abilities and Claude didn't already
            # bump CR, try to detect that from the original string
            if hints.get("_has_special"):
                cr_val = _CR_TO_FLOAT.get(cr, 0.0)
                bumped = min(cr_val + 2, 21.0)
                cr = _FLOAT_TO_CR.get(bumped, cr)
            monster["cr"] = cr
        except (ValueError, TypeError):
            pass

    return monster


# CR float↔string maps for the bump logic
_CR_TO_FLOAT: dict[str, float] = {
    "0": 0, "1/8": 0.125, "1/4": 0.25, "1/2": 0.5,
    "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6,
    "7": 7, "8": 8, "9": 9, "10": 10, "11": 11, "12": 12,
    "13": 13, "14": 14, "15": 15, "16": 16, "17": 17,
    "18": 18, "19": 19, "20": 20, "21": 21,
}
_FLOAT_TO_CR: dict[float, str] = {v: k for k, v in _CR_TO_FLOAT.items()}


# ── System prompts ────────────────────────────────────────────────────────────

SYSTEM_PROMPT_1E = textwrap.dedent("""
You are a tabletop role-playing game archivist and rules converter.  Your task
is to convert text from a published 1st Edition Advanced Dungeons & Dragons
adventure module into 5etools JSON format.  All content is fictional game
material intended for adult tabletop gaming; dark themes (evil cults, monster
violence, dungeon hazards) are standard genre conventions in this context.
The text was extracted from a scanned PDF and may have minor OCR artefacts.
Correct obvious OCR errors silently.

The text is annotated with these structural markers:

    [H1] Title            — chapter or part heading
    [H2] Title            — section heading
    [H3] Title            — sub-section or named area heading
    [ROOM-KEY-N]          — keyed encounter area (room, cavern, corridor)
    [1E-STAT]             — line containing 1e stat data (AC/MV/HD/THAC0/#AT)
    [STAT-BLOCK-START]    — start of a run of stat lines
    [STAT-BLOCK-END]      — end of the stat run
    [NPC-BLOCK]           — the stat block is a named NPC with ability scores
    [WANDERING-TABLE]     — the following table is a wandering monster table
    [TABLE-START]         — beginning of a detected table
    [TABLE-END]           — end of a detected table
    [INSET-START]         — beginning of boxed or indented text
    [INSET-END]           — end of boxed text
    [IMAGE: caption]      — image placeholder
    [italic]…[/italic]    — italic span
    [OCR]                 — this page was OCR'd (expect minor noise)
    [2-COLUMN]            — two-column layout detected on this page
    [3-COLUMN]            — three-column layout detected on this page

Return ONLY a valid JSON array of 5etools entry objects.  No markdown fences,
no explanation — raw JSON only.

Object types to use:

  Plain paragraph  → a bare JSON string
  Named section    → {"type":"entries","name":"Title","entries":[...]}
  Top section      → {"type":"section","name":"Title","entries":[...]}
  Keyed room area  → {"type":"entries","name":"17. Vestibule","entries":[...]}
  Bulleted list    → {"type":"list","items":["a","b"]}
  Table            → {"type":"table","caption":"","colLabels":[],"colStyles":[],"rows":[[]]}
  Boxed/sidebar    → {"type":"inset","name":"Title","entries":[...]}
  Read-aloud text  → {"type":"inset","name":"","entries":["text..."]}
  Image stub       → {"type":"image","href":{"type":"internal","path":"img/placeholder.webp"},"title":"caption"}

Rules:
- Every [ROOM-KEY-N] opens a new {"type":"entries","name":"N. Room Name"} block.
  If there is no explicit room name, use the first few words of the description.
- [INSET-START/END] blocks that have no heading and read as atmospheric prose are
  read-aloud text: use {"type":"inset","name":""}.
- Named sidebars, DM notes, or special features use {"type":"inset","name":"..."}.
- Preserve all 1e game-mechanical text accurately.
- Use {@b text} for bold, {@i text} for italic.
- Use {@creature Name} for monster names, {@spell Name} for spells,
  {@item Name} for magic items, {@dice NdN} for dice expressions.
- Wandering monster tables ([WANDERING-TABLE]) → {"type":"table"} with colLabels
  from the table headers (e.g., ["d12","Monster","Number Appearing"]).
- Stat lines ([1E-STAT], [STAT-BLOCK-START/END]) should be kept verbatim inside
  the room entry as italic text: "{@i Gnolls (6): AC 5; MV 9\"; HD 2; hp 9; #AT 1; D 2-8}"
  A separate pass converts these stats; do NOT attempt conversion here.
- NPC blocks ([NPC-BLOCK]) should be a {"type":"entries","name":"NPC Name"}
  with the stat lines as italic body text.
- Do NOT add IDs — they are added later.
- Merge hyphenated line-breaks: "adven-\nture" → "adventure".
- If a page contains only noise or blank content, return [].
""").strip()


MONSTER_SYSTEM_PROMPT_1E = textwrap.dedent("""
You are a tabletop role-playing game archivist converting published 1st Edition
Advanced Dungeons & Dragons monster and NPC stat blocks into 5etools bestiary
JSON.  All content is fictional game material for adult tabletop gaming.
Apply the conversion rules below precisely.

━━━ 1E STAT BLOCK FORMATS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Inline encounter format (most common in room keys):
  Gnolls (6): AC 5; MV 9"; HD 2; hp 9 each; #AT 1; D 2-8; AL CE; XP 28+2/hp

Full NPC format (named bosses and villains):
  HEDRACK, High Priest of the Elder Elemental God
    S: 15  I: 12  W: 17  D: 11  Co: 14  Ch: 10
    AC: 2 (plate +1 & shield +1)  MV: 9"  Level: 8 Cleric
    hp: 52  THAC0: 13  #AT: 1  D: 1-6+2 (mace +2)
    Spells (Cleric): P: 5/5/4/3/2/1
    XP: 3,000+10/hp

━━━ CONVERSION RULES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ARMOUR CLASS
  1e uses descending AC (lower = better, base 10).
  Formula: 5e_AC = 19 − 1e_AC
  Examples: AC 10 → 9  |  AC 5 → 14  |  AC 2 → 17  |  AC 0 → 19  |  AC −2 → 21
  If computed AC > 20: use 20 and add "natural armor" as the source.
  Output format: [{"ac": 14, "from": ["chain mail"]}]  or  [14] if source unknown.
  Also output the hint field: "_1e_ac": <original_1e_integer>

ATTACK BONUS (from THAC0)
  Formula: attack_bonus = 20 − THAC0
  Examples: THAC0 20 → +0 | THAC0 17 → +3 | THAC0 13 → +7 | THAC0 7 → +13
  Use this value for "{@hit N}" in action strings.
  Also output the hint field: "_thac0": <original_thac0_integer>

MOVEMENT SPEED
  Formula: 5e_speed_ft = MV_inches × 5   (rounded to nearest 5)
  Examples: MV 6" → 30 ft | MV 9" → 45 ft | MV 12" → 60 ft | MV 15" → 75 ft
  Fly speed: "Fl N"" or second value after "/" → fly: N × 5
  Swim speed: "Sw N"" → swim: N × 5
  Burrow: "Br N"" → burrow: N × 5
  Also output the hint field: "_mv_inches": <mv_number_as_float>

HIT DICE → CR
  Use this table. Adjust UP by 1–2 steps if the creature has level drain,
  paralysis, petrification, breath weapon, or can cast 4+ spells:
    HD < 0.5  → CR "0"      HD 0.5–1   → CR "1/8"   HD 1–1.5   → CR "1/4"
    HD 1.5–2.5→ CR "1/2"   HD 2.5–3.5 → CR "1"     HD 3.5–4.5 → CR "2"
    HD 4.5–5.5→ CR "3"     HD 5.5–6.5 → CR "4"     HD 6.5–7.5 → CR "5"
    HD 7.5–9  → CR "6"     HD 9–11    → CR "8"     HD 11–13   → CR "10"
    HD 13–16  → CR "13"    HD 16–20   → CR "17"    HD 20+     → CR "21"
  Output the hint field: "_hd": <hd_as_float>
  If creature has special abilities: output "_has_special": true

HIT POINTS
  If exact hp listed (e.g., "hp 52"): use as average, infer formula.
  Otherwise use: average = HD × 4.5  (1d8 average is 4.5).
  Formula: NdM where M=8 for most creatures; M=6 for undead; M=10 for large
           beasts; M=12 for giants/dragons.
  Add CON modifier per die for creatures with known CON.

ABILITY SCORES
  Use listed values for named NPCs.
  For generic monsters, estimate:
    STR = min(22, 8 + round(HD × 1.5))  rounded to nearest even
    DEX = 14 if MV > 12" or described as agile/quick; otherwise 10
    CON = min(20, 10 + round(HD / 2))    rounded to nearest even
    INT from description:
      "non-intelligent" / "animal"     → 2
      "semi-intelligent"               → 4
      "low intelligence"               → 6
      "average" / not described        → 10
      "high intelligence"              → 14
      "exceptional" / "genius"         → 18
    WIS = 10 (beasts) / 12 (humanoids) / 14 (spellcasters)
    CHA = 10; use 6 for "horrifying/hideous"; 16 for "awe-inspiring/beautiful"

SAVING THROWS
  Include only for spellcasters and creatures with notable save resistances.
  Map 1e categories: Death/Poison → CON | Wands → DEX | Paralysis/Stone → WIS
                     Breath → DEX | Spells → WIS (divine) or INT (arcane)
  5e save bonus = proficiency − (1e_target − 11)
  Proficiency from CR: CR 0–4 → +2 | CR 5–8 → +3 | CR 9–12 → +4 |
                       CR 13–16 → +5 | CR 17–20 → +6 | CR 21+ → +7

ALIGNMENT
  LG/NG/CG → ["L","G"] / ["N","G"] / ["C","G"]
  LN/N/CN  → ["L","N"] / ["N"]    / ["C","N"]
  LE/NE/CE → ["L","E"] / ["N","E"] / ["C","E"]
  Unaligned (animals, constructs, oozes) → ["U"]

DAMAGE NOTATION
  Convert 1e ranges to standard dice: 1-6→1d6, 2-8→1d8, 1-10→1d10,
  2-12→2d6, 3-18→3d6, 1-4→1d4, 1-3→1d3.  Add STR modifier to melee damage.

SPELLCASTING (for NPCs with class/level)
  Map 1e slot notation "P: 3/3/2/2/1" (Priest) or "M: 4/3/2" (Magic-User)
  to 5e spell slot counts using standard 5e tables.
  Set spell save DC = 8 + proficiency + WIS (cleric) or INT (MU).
  List spells in "spells" block by level.  Use {@spell Name} for each spell.

SPECIAL ATTACKS / DEFENSES
  Translate 1e abilities to 5e equivalents:
    Level drain         → "On a hit the target's hit point maximum is reduced by N"
    Paralysis           → target is paralyzed, CON save DC (8 + prof + relevant mod)
    Petrification       → target is petrified, CON save DC
    Poison              → target is poisoned/takes poison damage, CON save DC
    Breath weapon       → Nft cone/line, damage type, DEX save DC for half
    Spell-like ability  → list as an action/trait with recharge or at-will

XP values: discard 1e XP entirely.

━━━ OUTPUT FORMAT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Return ONLY a valid JSON array.  Return [] if no stat blocks present.
No markdown fences, no explanation — only raw JSON.

REQUIRED: name, source ("HOMEBREW"), size, type, alignment, ac, hp, speed,
          str, dex, con, int, wis, cha, passive, cr
OPTIONAL: save, skill, senses, languages, immune, resist, conditionImmune,
          trait, action, bonus, reaction, legendary, spellcasting,
          isNamedCreature (true for unique NPCs), isNpc

Size codes: T S M L H G (Tiny/Small/Medium/Large/Huge/Gargantuan)

Attack format: "{@atk mw} {@hit 5} to hit, reach 5 ft., one target. {@h}{@damage 2d6+3} slashing."
passive Perception = 10 + WIS modifier (+ proficiency if Perception trained)

Include the original 1e stat line for verification:
  "_1e_original": "Gnolls (6): AC 5; MV 9\\"; HD 2; hp 9 each; #AT 1; D 2-8; AL CE"
""").strip()


# ── Image preprocessing ───────────────────────────────────────────────────────

def preprocess_image(img: Image.Image) -> Image.Image:
    """Preprocess for aged/scanned module pages — higher contrast than base OCR."""
    img = img.convert("L")
    img = ImageEnhance.Contrast(img).enhance(2.5)   # stronger for aged ink
    img = img.filter(ImageFilter.SHARPEN)
    img = img.point(lambda p: 255 if p > 120 else 0, "1")  # lower threshold
    return img


# ── 1e pattern annotator ─────────────────────────────────────────────────────

def annotate_1e_patterns(text: str) -> str:
    """
    Post-process OCR/digital annotated text to add 1e-specific markers:
      [ROOM-KEY-N]         numbered encounter area
      [1E-STAT]            line carrying AD&D stat tokens
      [STAT-BLOCK-START/END] run of consecutive stat lines
      [NPC-BLOCK]          stat block that includes ability scores
      [WANDERING-TABLE]    wandering-monster table header
    """
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # ── Wandering monster table header ───────────────────────────────────
        if WANDER_RE.search(stripped):
            out.append("[WANDERING-TABLE]")
            out.append(line)
            i += 1
            continue

        # ── Room key ─────────────────────────────────────────────────────────
        m = ROOM_KEY_RE.match(stripped)
        if m:
            room_num = m.group(1)
            out.append(f"[ROOM-KEY-{room_num}]")
            out.append(line)
            i += 1
            continue

        # ── Stat block run ───────────────────────────────────────────────────
        token_count = len(_STAT_TOKENS.findall(stripped))
        if token_count >= 2:
            # Collect the full run of stat-adjacent lines
            stat_run = [line]
            has_ability = bool(ABILITY_LINE_RE.search(stripped))
            j = i + 1
            while j < len(lines):
                next_stripped = lines[j].strip()
                if not next_stripped:
                    break
                next_tokens = len(_STAT_TOKENS.findall(next_stripped))
                if next_tokens >= 1 or ABILITY_LINE_RE.search(next_stripped):
                    stat_run.append(lines[j])
                    if ABILITY_LINE_RE.search(next_stripped):
                        has_ability = True
                    j += 1
                else:
                    break

            out.append("[STAT-BLOCK-START]")
            if has_ability:
                out.append("[NPC-BLOCK]")
            for stat_line in stat_run:
                out.append(f"[1E-STAT] {stat_line.strip()}")
            out.append("[STAT-BLOCK-END]")
            i = j
            continue

        out.append(line)
        i += 1

    return "\n".join(out)


# ── OCR pipeline ─────────────────────────────────────────────────────────────

def ocr_page_image(img: Image.Image, lang: str = "eng") -> dict:
    """Run Tesseract on a pre-processed image; annotate with 1e markers."""
    processed = preprocess_image(img)

    data = pytesseract.image_to_data(
        processed, lang=lang, config=TESS_CONFIG,
        output_type=pytesseract.Output.DICT,
    )

    page_width = img.width

    words: list[dict] = []
    n = len(data["text"])
    for k in range(n):
        w = data["text"][k].strip()
        if not w:
            continue
        conf = int(data["conf"][k])
        if conf < 10:
            continue
        words.append({
            "text": w, "left": data["left"][k], "top": data["top"][k],
            "width": data["width"][k], "height": data["height"][k],
            "block": data["block_num"][k], "par": data["par_num"][k],
            "line": data["line_num"][k], "conf": conf,
        })

    if not words:
        return {"text": "", "columns": 1}

    # ── Column detection (supports 1, 2, or 3 columns) ─────────────────────
    xs = sorted(w["left"] for w in words)
    gap_threshold = page_width * COLUMN_GAP_RATIO
    # Collect all significant gaps not at the page edges
    raw_gaps: list[tuple[int, int]] = []  # (gap_size, mid_x)
    for k in range(len(xs) - 1):
        gap = xs[k + 1] - xs[k]
        mid_x = (xs[k] + xs[k + 1]) // 2
        if gap > gap_threshold and page_width * 0.08 < mid_x < page_width * 0.92:
            raw_gaps.append((gap, mid_x))
    raw_gaps.sort(reverse=True)

    # Keep up to 2 splits that are sufficiently separated from each other
    min_sep = page_width * 0.15
    col_splits: list[int] = []
    for _, mid_x in raw_gaps:
        if all(abs(mid_x - s) > min_sep for s in col_splits):
            col_splits.append(mid_x)
        if len(col_splits) == 2:
            break
    col_splits.sort()
    columns = len(col_splits) + 1 if col_splits else 1

    def _col_of(cx: int) -> int:
        for i, split in enumerate(col_splits):
            if cx < split:
                return i
        return len(col_splits)

    def reading_order_key(w: dict) -> tuple:
        col = _col_of(w["left"] + w["width"] // 2)
        return (col, w["top"], w["left"])

    words.sort(key=reading_order_key)

    heights = sorted(w["height"] for w in words if w["height"] > 0)
    # Median is more robust than mean: one very tall glyph won't skew the reference.
    avg_h = heights[len(heights) // 2] if heights else 20
    # Raised thresholds reduce false-positive H3 tagging of body text.
    h1_h, h2_h, h3_h = avg_h * 1.9, avg_h * 1.55, avg_h * 1.30

    line_map: dict[tuple, list[dict]] = defaultdict(list)
    for w in words:
        line_map[(w["block"], w["par"], w["line"])].append(w)

    def line_order_key(key: tuple) -> tuple:
        first = line_map[key][0]
        col = _col_of(first["left"] + first["width"] // 2)
        return (col, first["top"])

    sorted_keys = sorted(line_map.keys(), key=line_order_key)

    annotated_lines: list[str] = []
    prev_block = None

    for key in sorted_keys:
        line_words = sorted(line_map[key], key=lambda w: w["left"])
        line_text  = " ".join(w["text"] for w in line_words).strip()
        if not line_text:
            continue
        block_num = key[0]
        if prev_block is not None and block_num != prev_block:
            annotated_lines.append("")
        prev_block = block_num

        lh = sorted(w["height"] for w in line_words if w["height"] > 0)
        line_h   = lh[int(len(lh) * 0.75)] if lh else avg_h   # 75th-pct avoids one-tall-cap false positives
        is_short = len(line_text) < 80

        if line_h >= h1_h and is_short:
            annotated_lines.append(f"[H1] {line_text}")
        elif line_h >= h2_h and is_short:
            annotated_lines.append(f"[H2] {line_text}")
        elif line_h >= h3_h and is_short:
            annotated_lines.append(f"[H3] {line_text}")
        else:
            annotated_lines.append(line_text)

    # Inset detection
    block_bounds: dict[int, dict] = {}
    for w in words:
        b = w["block"]
        if b not in block_bounds:
            block_bounds[b] = {"left": w["left"], "right": w["left"] + w["width"],
                               "top": w["top"], "bottom": w["top"] + w["height"]}
        else:
            block_bounds[b]["left"]   = min(block_bounds[b]["left"], w["left"])
            block_bounds[b]["right"]  = max(block_bounds[b]["right"], w["left"] + w["width"])
            block_bounds[b]["top"]    = min(block_bounds[b]["top"], w["top"])
            block_bounds[b]["bottom"] = max(block_bounds[b]["bottom"], w["top"] + w["height"])

    inset_blocks: set[int] = set()
    for b, bbox in block_bounds.items():
        bw = bbox["right"] - bbox["left"]
        il = bbox["left"] / page_width
        ir = 1.0 - bbox["right"] / page_width
        if bw < page_width * 0.60 and il > 0.08 and ir > 0.08:
            inset_blocks.add(b)

    final_lines: list[str] = []
    cur_inset = False

    for key in sorted_keys:
        b = key[0]
        is_inset = b in inset_blocks
        if is_inset and not cur_inset:
            final_lines.append("[INSET-START]")
            cur_inset = True
        elif not is_inset and cur_inset:
            final_lines.append("[INSET-END]")
            cur_inset = False

        line_words = sorted(line_map[key], key=lambda w: w["left"])
        line_text  = " ".join(w["text"] for w in line_words).strip()
        if not line_text:
            continue

        lh = sorted(w["height"] for w in line_words if w["height"] > 0)
        line_h   = lh[int(len(lh) * 0.75)] if lh else avg_h
        is_short = len(line_text) < 80

        if line_h >= h1_h and is_short:
            final_lines.append(f"[H1] {line_text}")
        elif line_h >= h2_h and is_short:
            final_lines.append(f"[H2] {line_text}")
        elif line_h >= h3_h and is_short:
            final_lines.append(f"[H3] {line_text}")
        else:
            final_lines.append(line_text)

    if cur_inset:
        final_lines.append("[INSET-END]")

    merged = _inject_table_markers(final_lines)
    raw_text = "\n".join(merged)
    # Apply 1e-specific pattern annotations
    annotated = annotate_1e_patterns(raw_text)
    return {"text": annotated, "columns": columns}


def _inject_table_markers(lines: list[str]) -> list[str]:
    """Wrap runs of 3+ tab/space-separated lines with TABLE-START/END."""
    result: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("["):
            result.append(line)
            i += 1
            continue
        tokens = re.split(r"  +|\t", line.strip())
        if len(tokens) >= 2:
            run = [line]
            j = i + 1
            while j < len(lines) and not lines[j].startswith("["):
                nt = re.split(r"  +|\t", lines[j].strip())
                if len(nt) >= 2:
                    run.append(lines[j])
                    j += 1
                else:
                    break
            if len(run) >= 3:
                result.append("[TABLE-START]")
                result.extend(run)
                result.append("[TABLE-END]")
                i = j
                continue
        result.append(line)
        i += 1
    return result


# ── Digital page extraction ───────────────────────────────────────────────────

def compute_body_size(pdf_doc: fitz.Document) -> float:
    sizes: list[float] = []
    for i, page in enumerate(pdf_doc):
        if i >= 20:
            break
        for blk in page.get_text("dict")["blocks"]:
            if blk.get("type") != 0:
                continue
            for line in blk.get("lines", []):
                for span in line.get("spans", []):
                    s = span.get("size", 0)
                    if s > 0:
                        sizes.append(s)
    if not sizes:
        return 12.0
    sizes.sort()
    return sizes[len(sizes) // 2]


def extract_digital_page(page_obj: fitz.Page, body_size: float) -> str | None:
    """Extract annotated text from a digital PDF page; apply 1e markers."""
    h1_thresh = body_size * 1.40
    h2_thresh = body_size * 1.20
    h3_thresh = body_size * 1.05

    raw_blocks = page_obj.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
    lines_out: list[str] = []
    total_chars = 0

    for blk in raw_blocks:
        if blk.get("type") != 0:
            lines_out.append("[IMAGE: embedded]")
            continue
        for line in blk.get("lines", []):
            text_parts: list[str] = []
            max_size = 0.0
            is_bold = is_italic = False
            for span in line.get("spans", []):
                t = span.get("text", "").strip()
                if not t:
                    continue
                text_parts.append(t)
                sz = span.get("size", 0)
                if sz > max_size:
                    max_size = sz
                flags = span.get("flags", 0)
                if flags & (1 << 4): is_bold   = True
                if flags & (1 << 1): is_italic = True
            text = " ".join(text_parts).strip()
            if not text:
                continue
            total_chars += len(text)

            is_heading = False
            level = 0
            if max_size >= h1_thresh and (is_bold or len(text) < 80):
                level = 1; is_heading = True
            elif max_size >= h2_thresh and (is_bold or len(text) < 80):
                level = 2; is_heading = True
            elif max_size >= h3_thresh and is_bold and len(text) < 80:
                level = 3; is_heading = True

            if is_heading:
                lines_out.append(f"[H{level}] {text}")
            elif is_italic and not is_bold:
                lines_out.append(f"[italic]{text}[/italic]")
            else:
                lines_out.append(text)

    if total_chars < MIN_DIGITAL_CHARS:
        return None

    raw_text = "\n".join(lines_out)
    return annotate_1e_patterns(raw_text)


# ── Claude API ────────────────────────────────────────────────────────────────

def _parse_claude_response(raw: str, verbose: bool,
                           debug_dir: Path | None = None,
                           chunk_id: str = "") -> list[Any]:
    raw = raw.strip()
    if debug_dir:
        debug_dir.mkdir(parents=True, exist_ok=True)
        (debug_dir / f"{chunk_id}-response.txt").write_text(raw, encoding="utf-8")
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$",          "", raw)
    try:
        result = json.loads(raw)
        if not isinstance(result, list):
            result = [result]
        if debug_dir:
            (debug_dir / f"{chunk_id}-parsed.json").write_text(
                json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        return result
    except json.JSONDecodeError as e:
        print(f"    [WARN] JSON parse error in {chunk_id}: {e}", flush=True)
        if debug_dir:
            (debug_dir / f"{chunk_id}-parse-error.txt").write_text(
                f"Error: {e}\n\n{raw}", encoding="utf-8"
            )
        return []


_CHUNK_PREFIX = (
    "[CONTEXT: The following is fictional text from a published 1st Edition "
    "Advanced Dungeons & Dragons tabletop RPG module. It is being converted "
    "to a structured JSON format for digital archival and gaming use.]\n\n"
)


def _sanitize_text(text: str) -> str:
    """Remove characters that the Anthropic API rejects.

    Old scanned PDFs often produce null bytes, private-use Unicode codepoints,
    and other control characters via Tesseract that cause 400 errors.
    """
    # Strip null bytes and C0/C1 control chars except tab, newline, carriage return
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", text)
    # Strip Unicode surrogates and private-use area characters
    text = re.sub(r"[\ud800-\udfff\ue000-\uf8ff]", " ", text)
    # Collapse runs of blank lines to at most two
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


# Phrases common in TSR-era modules that trip the API output content filter.
# Replacements preserve game meaning while avoiding filter triggers.
# Order matters: more-specific patterns first.
_TRIGGER_SUBS: list[tuple[re.Pattern[str], str]] = [
    # "robbed, pillaged, enslaved, and worse" / "enslaved and worse"
    (re.compile(r'\benslave[ds]?\b',            re.IGNORECASE), "captured"),
    (re.compile(r'\benslavement\b',             re.IGNORECASE), "captivity"),
    (re.compile(r',?\s*and\s+worse\b',          re.IGNORECASE), ""),
    # Period gender/service terms
    (re.compile(r'\bwenche?s?\b',               re.IGNORECASE), "barmaid"),
    (re.compile(r'\bbuxom\b',                   re.IGNORECASE), "cheerful"),
    # "harlot" / "strumpet" / "concubine" also appear in some modules
    (re.compile(r'\bharlots?\b',                re.IGNORECASE), "commoner"),
    (re.compile(r'\bstrumpets?\b',              re.IGNORECASE), "commoner"),
    (re.compile(r'\bconcubines?\b',             re.IGNORECASE), "companion"),
    # Age + gender phrases that trip filters when combined with other content
    (re.compile(r'\byoung\s+girl\b',            re.IGNORECASE), "young person"),
    (re.compile(r'\bteen[- ]?aged?\s+(?:girl|daughter)s?\b',
                                                re.IGNORECASE), "young adult"),
    # "carousing" in context with age references
    (re.compile(r'\bcarousing\b',               re.IGNORECASE), "drinking"),
    # "lust" / "lusted" / "lusting" appear in evil-cult and demon descriptions
    (re.compile(r'\blusts?\b|\blusted\b|\blusting\b', re.IGNORECASE), "greed"),
    (re.compile(r'\blustful\b',                 re.IGNORECASE), "greedy"),
    # "Beloved" as a title for demon-queen servants (e.g. "Zuggtmoy's Beloved")
    (re.compile(r'\bBeloved\b',                 re.IGNORECASE), "Servants"),
    # High-density dark-vocabulary words common in T1-4 background / temple text
    (re.compile(r'\bmurderous\b',               re.IGNORECASE), "hostile"),
    (re.compile(r'\boppressors?\b',             re.IGNORECASE), "enemies"),
    (re.compile(r'\bslaughter\b',               re.IGNORECASE), "defeat"),
    (re.compile(r'\babominations?\b',           re.IGNORECASE), "evils"),
    (re.compile(r'\bpestilence\b',              re.IGNORECASE), "misfortune"),
    (re.compile(r'\bwickedness\b',              re.IGNORECASE), "evil"),
    (re.compile(r'\btyranny\b',                 re.IGNORECASE), "domination"),
    (re.compile(r'\bhubris\b',                  re.IGNORECASE), "pride"),
    # "demiurge" is a Gnostic term that trips output filters even in fantasy context
    (re.compile(r'\bdemiurge\b',                re.IGNORECASE), "dark power"),
    # "demon" in combination with other temple/cult language triggers output filters
    (re.compile(r'\bdemons?\b',                 re.IGNORECASE), "fiend"),
    (re.compile(r'\bdemonic\b',                 re.IGNORECASE), "fiendish"),
]


# OCR garbage patterns to strip before sending to Claude.
_OCR_GARBAGE_RE = re.compile(
    r'^\$[0-9A-Za-z]{3,}'       # fused ability-score lines, e.g. "$15112W Co16Ch11"
    r'|(?:\b(?:ce)+\b\s*)+'     # dotted leader lines OCR'd as "cece cece 36"
    r'|(?:\.{4,})',             # runs of dots from leader lines
    re.MULTILINE | re.IGNORECASE,
)


def load_trigger_config(path: Path) -> None:
    """Load extra substitution rules from a JSON config file produced by
    find_triggers.py and append them to _TRIGGER_SUBS."""
    import json as _json
    entries = _json.loads(path.read_text(encoding="utf-8"))
    flag_map = {"i": re.IGNORECASE, "m": re.MULTILINE, "s": re.DOTALL}
    for entry in entries:
        flags = 0
        for ch in entry.get("flags", ""):
            flags |= flag_map.get(ch, 0)
        _TRIGGER_SUBS.append(
            (re.compile(entry["pattern"], flags), entry.get("replacement", ""))
        )


def _strip_noise_lines(text: str) -> str:
    """Remove lines that are pure OCR noise from scanned illustrations or
    decorative title art.

    Rules:
    - Non-marker lines with no word >= 4 chars are dropped.
    - Heading marker lines ([H1]/[H2]/[H3]) are also checked: if the content
      after the marker has no word >= 3 chars it is dropped (catches garbage
      like "[H1] ne", "[H1] on i", "[H3] ds Se" from illustrated title pages).
    - Other structural markers (INSET, STAT-BLOCK, page separators, etc.) are
      always kept — they carry structural meaning independent of their content.
    """
    _HEADING_RE = re.compile(r'^\s*\[H[123]\]\s*')
    _OTHER_MARKER_RE = re.compile(
        r'^\s*(?:\[INSET-(?:START|END)\]|\[OCR\]'
        r'|\[STAT-BLOCK-(?:START|END)\]|\[1E-STAT\]'
        r'|\[WANDERING-TABLE\]|\[TABLE-(?:START|END)\]'
        r'|\[ROOM-KEY-\d+\]|---\s*(?:Page\s*\d+|\(second column\)|\(third column\))\s*---)'
    )
    clean: list[str] = []
    for line in text.split("\n"):
        if _OTHER_MARKER_RE.match(line):
            clean.append(line)
            continue
        if _HEADING_RE.match(line):
            content = _HEADING_RE.sub("", line).strip()
            content_words = re.findall(r"[A-Za-z]+", content)
            # Keep if: no alpha content (e.g. "[H3] 17."), or has a word >= 3 chars
            if not content_words or max(len(w) for w in content_words) >= 3:
                clean.append(line)
            continue
        words = re.findall(r"[A-Za-z]+", line)
        if words and max(len(w) for w in words) >= 4:
            clean.append(line)
        # else: drop — noise line
    return "\n".join(clean)


def _deinterleave_columns(text: str) -> str:
    """Fix pages where OCR read two columns simultaneously, producing text
    where every other paragraph is wrapped in a single-line [INSET-START/END].

    When more than 20 % of lines are INSET boundary markers the page is
    treated as a column-interleave artefact: all non-INSET lines are
    collected first, then all INSET-interior lines, and the two streams are
    rejoined with a separator.  Real multi-line insets (boxed text, sidebars)
    are left untouched because they contain more than two interior lines.
    """
    lines = text.split("\n")
    total = len(lines)
    inset_marker_count = sum(
        1 for l in lines
        if l.strip() in ("[INSET-START]", "[INSET-END]")
    )
    # Not a column-interleave page — leave as-is
    if total == 0 or inset_marker_count / total < 0.20:
        return text

    outside: list[str] = []
    inside:  list[str] = []
    in_block = False
    block_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped == "[INSET-START]":
            in_block = True
            block_lines = []
        elif stripped == "[INSET-END]":
            in_block = False
            if len(block_lines) <= 2:
                # Single/double line → column artefact, route to inside stream
                inside.extend(block_lines)
            else:
                # Multi-line real inset — keep in place
                outside.append("[INSET-START]")
                outside.extend(block_lines)
                outside.append("[INSET-END]")
            block_lines = []
        elif in_block:
            block_lines.append(line)
        else:
            outside.append(line)

    result = "\n".join(outside)
    if inside:
        result += "\n\n--- (second column) ---\n" + "\n".join(inside)
    return result


def _neutralize_triggers(text: str) -> str:
    """Strip OCR noise and replace TSR-era phrases that trip the API output
    content filter."""
    text = _deinterleave_columns(text)
    text = _strip_noise_lines(text)
    text = _OCR_GARBAGE_RE.sub("", text)
    for pattern, replacement in _TRIGGER_SUBS:
        text = pattern.sub(replacement, text)
    return text


def call_claude(client: anthropic.Anthropic, chunk_text: str,
                model: str, verbose: bool,
                debug_dir: Path | None = None,
                chunk_id: str = "chunk-0000") -> list[Any] | None:
    """Return parsed entries, or None if the API rejected the chunk."""
    chunk_text = _CHUNK_PREFIX + _neutralize_triggers(_sanitize_text(chunk_text))

    if verbose:
        print(f"    → Sending {len(chunk_text):,} chars to Claude...", flush=True)
    if debug_dir:
        debug_dir.mkdir(parents=True, exist_ok=True)
        (debug_dir / f"{chunk_id}-input.txt").write_text(chunk_text, encoding="utf-8")

    try:
        msg = client.messages.create(
            model=model, max_tokens=8192,
            system=SYSTEM_PROMPT_1E,
            messages=[{"role": "user", "content": chunk_text}],
        )
    except anthropic.BadRequestError as e:
        print(f"    [WARN] API rejected {chunk_id} ({e}); will retry page-by-page.", flush=True)
        if debug_dir:
            (debug_dir / f"{chunk_id}-api-error.txt").write_text(str(e), encoding="utf-8")
        return None

    return _parse_claude_response(msg.content[0].text, verbose,
                                  debug_dir=debug_dir, chunk_id=chunk_id)


def call_claude_for_monsters(client: anthropic.Anthropic, chunk_text: str,
                              model: str, source_id: str, verbose: bool,
                              no_cr_adjustment: bool = False,
                              debug_dir: Path | None = None,
                              chunk_id: str = "chunk-0000") -> list[Any] | None:
    chunk_text = _CHUNK_PREFIX + _neutralize_triggers(_sanitize_text(chunk_text))

    if verbose:
        print(f"    [monsters] Scanning {len(chunk_text):,} chars...", flush=True)

    try:
        msg = client.messages.create(
            model=model, max_tokens=8192,
            system=MONSTER_SYSTEM_PROMPT_1E,
            messages=[{"role": "user", "content": chunk_text}],
        )
    except anthropic.BadRequestError as e:
        print(f"    [WARN] API rejected {chunk_id}-monsters ({e}); skipping.", flush=True)
        return None
    raw_monsters = _parse_claude_response(
        msg.content[0].text, verbose,
        debug_dir=debug_dir, chunk_id=f"{chunk_id}-monsters",
    )

    monsters: list[Any] = []
    for m in raw_monsters:
        if not isinstance(m, dict):
            continue
        m["source"] = source_id
        m = post_process_monster_1e(m, no_cr_adjustment=no_cr_adjustment)
        monsters.append(m)

    if monsters and verbose:
        names = [m.get("name", "?") for m in monsters]
        print(f"    [monsters] Found {len(monsters)}: {', '.join(names)}", flush=True)

    return monsters


# ── ID assignment & TOC ───────────────────────────────────────────────────────

_id_counter = 0

def reset_ids() -> None:
    global _id_counter
    _id_counter = 0

def assign_ids(entries: list[Any]) -> list[Any]:
    global _id_counter
    for entry in entries:
        if isinstance(entry, dict):
            if entry.get("type") in ("section", "entries", "inset"):
                entry["id"] = f"{_id_counter:03d}"
                _id_counter += 1
            if "entries" in entry:
                assign_ids(entry["entries"])
            if "items" in entry:
                assign_ids(entry["items"])
    return entries

def build_toc(data: list[Any]) -> list[dict]:
    toc: list[dict] = []
    for entry in data:
        if not isinstance(entry, dict) or entry.get("type") != "section":
            continue
        ch: dict = {"name": entry.get("name", "Untitled"), "headers": []}
        for sub in entry.get("entries", []):
            if isinstance(sub, dict) and sub.get("type") == "entries":
                ch["headers"].append(sub.get("name", ""))
        toc.append(ch)
    return toc


# ── Dry-run (token cost estimate) ─────────────────────────────────────────────

_PRICE = {
    "haiku":  {"input": 0.80,  "output": 4.00},
    "sonnet": {"input": 3.00,  "output": 15.00},
    "opus":   {"input": 15.00, "output": 75.00},
}

def _model_tier(model: str) -> str:
    m = model.lower()
    if "haiku"  in m: return "haiku"
    if "sonnet" in m: return "sonnet"
    if "opus"   in m: return "opus"
    return "sonnet"

def dry_run(client: anthropic.Anthropic, chunk_texts: list[str],
            chunks: list, model: str, verbose: bool) -> None:
    tier   = _model_tier(model)
    prices = _PRICE.get(tier, _PRICE["sonnet"])
    print(f"\n[DRY-RUN] Token count + cost estimate")
    print(f"  Model  : {model}")
    print(f"  Pricing: ${prices['input']:.2f} / ${prices['output']:.2f} per M tokens")
    print()
    total_input = 0
    est_out_per_chunk = 1_000
    skipped = 0
    for i, chunk_text in enumerate(chunk_texts):
        if not chunk_text.strip():
            skipped += 1
            continue
        resp = client.messages.count_tokens(
            model=model, system=SYSTEM_PROMPT_1E,
            messages=[{"role": "user", "content": chunk_text}],
        )
        tok = resp.input_tokens
        total_input += tok
        if verbose or len(chunk_texts) <= 12:
            try:
                page_nums = [p for p, _ in chunks[i]]
                label = f"pages {page_nums[0]}–{page_nums[-1]}"
            except Exception:
                label = f"chunk {i}"
            print(f"  chunk-{i:04d}  ({label})  →  {tok:,} input tokens")
    total_output = est_out_per_chunk * (len(chunk_texts) - skipped)
    cost_in  = total_input  / 1_000_000 * prices["input"]
    cost_out = total_output / 1_000_000 * prices["output"]
    print()
    print(f"  Total input     : {total_input:,} tokens  →  ${cost_in:.4f}")
    print(f"  Est. output     : ~{total_output:,} tokens  →  ${cost_out:.4f}")
    print(f"  Estimated total : ${cost_in + cost_out:.4f}")
    print()
    print("  No API inference was performed. Remove --dry-run to convert.")
    print()


# ── Main conversion driver ────────────────────────────────────────────────────

def convert(
    pdf_path: Path,
    output_type: str,
    short_id: str,
    module_code: str | None,
    author: str,
    out_path: Path,
    api_key: str | None,
    chunk_size: int,
    pages: set[int],
    skip_pages: set[int],
    dpi: int,
    force_ocr: bool,
    lang: str,
    model: str,
    output_mode: str,
    dry_run_only: bool,
    extract_monsters: bool,
    monsters_only: bool,
    no_cr_adjustment: bool,
    no_retry: bool,
    debug_dir: Path | None,
    verbose: bool,
) -> None:
    mc_label = f"  Module: {module_code}" if module_code else ""
    print(f"\n{'='*62}")
    print(f"  PDF → 5etools  (1e AD&D Converter)")
    print(f"  Input :  {pdf_path}")
    print(f"  Output:  {out_path}")
    print(f"  Type  :  {output_type}   ID: {short_id}   Mode: {output_mode}")
    if mc_label: print(mc_label)
    if pages:     print(f"  Pages :  {sorted(pages)}")
    if skip_pages: print(f"  Skip  :  pages {sorted(skip_pages)}")
    print(f"  DPI   :  {dpi}   Force-OCR: {force_ocr}   Lang: {lang}")
    if debug_dir:
        debug_dir.mkdir(parents=True, exist_ok=True)
        print(f"  Debug :  {debug_dir}")
    print(f"{'='*62}\n")

    # ── 1. Open PDF & determine body size ────────────────────────────────────
    doc = fitz.open(str(pdf_path))
    total_pages = len(doc)
    print(f"[1/5] PDF opened: {total_pages} pages.", flush=True)
    body_size = compute_body_size(doc)
    if verbose:
        print(f"      Body font size: {body_size:.1f}pt")

    # ── 2. Extract pages ─────────────────────────────────────────────────────
    print("[2/5] Extracting pages ...", flush=True)
    needs_ocr:     list[int] = []
    # Build effective skip set: explicitly skipped + pages outside the requested range
    effective_skip = set(skip_pages)
    if pages:
        effective_skip |= {i for i in range(1, total_pages + 1) if i not in pages}

    digital_results: dict[int, str | None] = {}

    for page_idx in range(total_pages):
        if page_idx + 1 in effective_skip:
            digital_results[page_idx] = ""
            continue
        if force_ocr:
            needs_ocr.append(page_idx)
            digital_results[page_idx] = None
        else:
            text = extract_digital_page(doc[page_idx], body_size)
            digital_results[page_idx] = text
            if text is None:
                needs_ocr.append(page_idx)

    doc.close()

    ocr_images: dict[int, Image.Image] = {}
    if needs_ocr:
        if verbose:
            print(f"      Rendering {len(needs_ocr)} pages at {dpi} DPI ...", flush=True)
        for idx in needs_ocr:
            imgs = convert_from_path(str(pdf_path), dpi=dpi,
                                     first_page=idx + 1, last_page=idx + 1)
            if imgs:
                ocr_images[idx] = imgs[0]

    page_texts: list[str] = []
    ocr_count = digital_count = 0
    for page_idx in range(total_pages):
        if digital_results[page_idx] == "":
            page_texts.append("")                      # skipped
        elif digital_results[page_idx] is not None:
            page_texts.append(digital_results[page_idx])  # type: ignore
            digital_count += 1
        elif page_idx in ocr_images:
            result = ocr_page_image(ocr_images[page_idx], lang=lang)
            if result["text"].strip():
                ncol = result["columns"]
                flag = "[OCR]" + (f" [{ncol}-COLUMN]" if ncol > 1 else "")
                page_texts.append(f"{flag}\n{result['text']}")
            else:
                page_texts.append("")
            ocr_count += 1
        else:
            page_texts.append("")

    print(f"      Digital: {digital_count}  |  OCR: {ocr_count}  |  "
          f"Skipped/blank: {total_pages - digital_count - ocr_count}", flush=True)

    # ── 3. Chunk ─────────────────────────────────────────────────────────────
    print(f"[3/5] Chunking into groups of {chunk_size} pages ...", flush=True)
    indexed = [(i + 1, t) for i, t in enumerate(page_texts)]
    chunks: list[list[tuple[int, str]]] = [
        indexed[i:i + chunk_size] for i in range(0, len(indexed), chunk_size)
    ]
    print(f"      {len(chunks)} chunks.", flush=True)

    # Build chunk texts up front
    chunk_texts: list[str] = []
    for chunk in chunks:
        ct = ""
        for page_num, text in chunk:
            if text.strip():
                ct += f"\n--- Page {page_num} ---\n{text}\n"
        if len(ct) > MAX_CHUNK_CHARS:
            ct = ct[:MAX_CHUNK_CHARS]
            if verbose:
                print(f"    [WARN] Trimmed chunk to {MAX_CHUNK_CHARS} chars.")
        chunk_texts.append(ct)

    # ── 4. API / dry-run ─────────────────────────────────────────────────────
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        sys.exit("No Anthropic API key.  Set ANTHROPIC_API_KEY or pass --api-key.")
    client = anthropic.Anthropic(api_key=key)

    if dry_run_only:
        dry_run(client, chunk_texts, chunks, model, verbose)
        return

    all_entries: list[Any] = []
    all_monsters: list[Any] = []

    if not monsters_only:
        print(f"[4/5] Converting {len(chunks)} chunks via Claude ({model}) ...", flush=True)
        for i, (chunk, chunk_text) in enumerate(zip(chunks, chunk_texts)):
            page_nums = [p for p, _ in chunk]
            print(f"  Chunk {i+1}/{len(chunks)}  "
                  f"(pages {page_nums[0]}–{page_nums[-1]})", flush=True)
            if not chunk_text.strip():
                if verbose: print("    [SKIP] Empty chunk.")
                continue
            entries = call_claude(client, chunk_text, model, verbose,
                                  debug_dir=debug_dir, chunk_id=f"chunk-{i:04d}")
            if entries is None:
                if no_retry or chunk_size == 1:
                    print(f"    [SKIP] Chunk {i+1} rejected — skipping (no retry).", flush=True)
                    entries = []
                else:
                    # Content filter hit — retry each page individually
                    print(f"    [RETRY] Retrying chunk {i+1} page-by-page ...", flush=True)
                    entries = []
                    for page_num, page_text in chunk:
                        if not page_text.strip():
                            continue
                        single = f"\n--- Page {page_num} ---\n{page_text}\n"
                        result = call_claude(client, single, model, verbose,
                                            debug_dir=debug_dir,
                                            chunk_id=f"chunk-{i:04d}-p{page_num}")
                        if result is None:
                            print(f"    [SKIP] Page {page_num} rejected by content filter.", flush=True)
                        else:
                            entries.extend(result)
            print(f"    → {len(entries)} entries parsed"
                  + ("  ← EMPTY — check debug files" if debug_dir and not entries else ""),
                  flush=True)
            all_entries.extend(entries)
        print(f"      Total entries: {len(all_entries)}", flush=True)
    else:
        print("[4/5] Skipping adventure extraction (--monsters-only)", flush=True)

    if extract_monsters or monsters_only:
        label = "[4/5]" if monsters_only else "[4b]"
        print(f"{label} Extracting 1e monster stat blocks...", flush=True)
        for i, chunk_text in enumerate(chunk_texts):
            if not chunk_text.strip():
                continue
            monsters = call_claude_for_monsters(
                client, chunk_text, model, short_id, verbose,
                no_cr_adjustment=no_cr_adjustment,
                debug_dir=debug_dir, chunk_id=f"chunk-{i:04d}",
            )
            if monsters is not None:
                all_monsters.extend(monsters)
        print(f"      Total monsters found: {len(all_monsters)}", flush=True)

    # ── 5. Assemble output ────────────────────────────────────────────────────
    print("[5/5] Finalising output ...", flush=True)
    reset_ids()
    assign_ids(all_entries)

    title   = pdf_path.stem.replace("_", " ").replace("-", " ").title()
    today   = date.today().isoformat()
    toc     = build_toc(all_entries)

    import time as _time

    index_key = "adventure" if output_type == "adventure" else "book"
    data_key  = f"{index_key}Data"

    if output_type == "book":
        all_entries = [{"type": "section", "name": title,
                        "id": "000", "entries": all_entries}]

    index_entry: dict = {
        "name": title, "id": short_id, "source": short_id,
        "group": "homebrew", "published": today,
        "author": author, "contents": toc,
    }
    if module_code:
        index_entry["moduleCode"] = module_code

    converter_tag = "pdf_to_5etools_1e"
    meta_source: dict = {
        "json": short_id, "abbreviation": short_id[:8],
        "full": title, "version": "1.0.0",
        "authors": [author], "convertedBy": [converter_tag],
    }

    print(f"\n{'='*62}")
    print("  Done!")

    if monsters_only:
        obj: dict = {
            "_meta": {"sources": [meta_source],
                      "dateAdded": int(_time.time()),
                      "dateLastModified": int(_time.time())},
            "monster": all_monsters,
        }
        out_path.write_text(json.dumps(obj, indent="\t", ensure_ascii=False),
                            encoding="utf-8")
        print(f"  Output: {out_path}  ({len(all_monsters)} monsters)")
        print(f"{'='*62}\n")
        return

    if output_mode == "homebrew":
        obj = {
            "_meta": {"sources": [meta_source],
                      "dateAdded": int(_time.time()),
                      "dateLastModified": int(_time.time())},
            index_key: [index_entry],
            data_key:  [{"id": short_id, "source": short_id, "data": all_entries}],
            **({"monster": all_monsters} if all_monsters else {}),
        }
        out_path.write_text(json.dumps(obj, indent="\t", ensure_ascii=False),
                            encoding="utf-8")
        print(f"  Output file: {out_path}")
        print(f"{'='*62}\n")
        print("  To load: Manage Homebrew → Load from File → select the JSON.\n")
    else:
        data_obj: dict = {"data": all_entries}
        out_path.write_text(json.dumps(data_obj, indent="\t", ensure_ascii=False),
                            encoding="utf-8")
        index_path = out_path.parent / f"{index_key}s-{short_id.lower()}.json"
        index_path.write_text(
            json.dumps({index_key: [index_entry]}, indent="\t", ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"  Data file  : {out_path}")
        print(f"  Index file : {index_path}")
        if all_monsters:
            bestiary_path = out_path.parent / f"bestiary-{short_id.lower()}.json"
            bestiary_path.write_text(
                json.dumps({"monster": all_monsters}, indent="\t", ensure_ascii=False),
                encoding="utf-8",
            )
            print(f"  Bestiary   : {bestiary_path}  ({len(all_monsters)} monsters)")
        print(f"{'='*62}\n")


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_skip_pages(value: str) -> set[int]:
    """Parse a skip-pages argument like "1-3" or "127" into a set of page numbers."""
    pages: set[int] = set()
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, _, hi = part.partition("-")
            try:
                pages.update(range(int(lo), int(hi) + 1))
            except ValueError:
                pass
        else:
            try:
                pages.add(int(part))
            except ValueError:
                pass
    return pages


def main() -> None:
    parser = argparse.ArgumentParser(
        description="1st/2nd Edition AD&D module PDF → 5etools adventure/book JSON.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Examples:
          # Full T1-4 conversion including monsters
          python3 pdf_to_5etools_1e.py "T1-4.pdf" --module-code T1-4 \\
              --author "Gary Gygax & Frank Mentzer" --skip-pages 1-3,127-128 \\
              --extract-monsters --force-ocr

          # Monsters only, for building a bestiary
          python3 pdf_to_5etools_1e.py "T1-4.pdf" --module-code T1-4 \\
              --monsters-only --force-ocr

          # Dry run to estimate API cost before committing
          python3 pdf_to_5etools_1e.py "T1-4.pdf" --dry-run --module-code T1-4

          # High-resolution OCR for very faint ink
          python3 pdf_to_5etools_1e.py "S1.pdf" --module-code S1 \\
              --force-ocr --dpi 600
        """),
    )
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--type", choices=["adventure", "book"],
                        default="adventure", dest="output_type")
    parser.add_argument("--output-mode", choices=["homebrew", "server"],
                        default="homebrew", dest="output_mode")
    parser.add_argument("--id", default=None, dest="short_id",
                        help="Short uppercase ID (default: derived from filename)")
    parser.add_argument("--module-code", default=None, dest="module_code",
                        help='TSR module code, e.g. "T1-4", "B2", "S1"')
    parser.add_argument("--system", choices=["1e", "2e"], default="1e",
                        help="AD&D edition (default: 1e)")
    parser.add_argument("--author", default="Unknown")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None, dest="output_dir")
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--pages-per-chunk", type=int, default=DEFAULT_CHUNK,
                        dest="chunk_size")
    parser.add_argument("--dpi", type=int, default=DEFAULT_DPI)
    parser.add_argument("--force-ocr", action="store_true")
    parser.add_argument("--lang", default="eng")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--pages", default=None, metavar="RANGE",
                        help='Only process these pages, e.g. "10-20" or "5,10-15". '
                             'Useful for testing before running the full conversion.')
    parser.add_argument("--page", type=int, default=None, metavar="N",
                        help="Only process this single page number.")
    parser.add_argument("--skip-pages", action="append", default=[],
                        dest="skip_pages_args", metavar="RANGE",
                        help='Page(s) to skip, e.g. "1-3" or "127" (repeatable)')
    parser.add_argument("--no-cr-adjustment", action="store_true",
                        dest="no_cr_adjustment",
                        help="Disable CR bump for monsters with special abilities")
    parser.add_argument("--no-retry", action="store_true", dest="no_retry",
                        help="Skip failed chunks instead of retrying page-by-page. "
                             "Automatically active when --pages-per-chunk 1.")
    parser.add_argument("--extract-monsters", action="store_true",
                        dest="extract_monsters")
    parser.add_argument("--monsters-only", action="store_true",
                        dest="monsters_only")
    parser.add_argument("--trigger-config", type=Path, default=None,
                        dest="trigger_config",
                        help="JSON config of extra trigger substitutions produced "
                             "by find_triggers.py")
    parser.add_argument("--debug-dir", type=Path, default=None, dest="debug_dir")
    parser.add_argument("--dry-run", action="store_true", dest="dry_run_only")
    parser.add_argument("--verbose", action="store_true")

    args = parser.parse_args()

    if args.trigger_config:
        tc = normalise_path(str(args.trigger_config))
        if not tc.exists():
            sys.exit(f"Trigger config not found: {tc}")
        load_trigger_config(tc)
        print(f"Loaded trigger config: {tc}")

    pdf_path = normalise_path(str(args.pdf))
    if not pdf_path.exists():
        sys.exit(f"PDF not found: {pdf_path}")

    # Derive short_id: prefer --id, then --module-code (stripped), then filename
    if args.short_id:
        short_id = args.short_id.upper()
    elif args.module_code:
        short_id = re.sub(r"[^A-Z0-9]", "", args.module_code.upper())[:8] or "HOMEBREW"
    else:
        short_id = re.sub(r"[^A-Z0-9]", "", pdf_path.stem.upper())[:8] or "HOMEBREW"

    prefix  = "adventure" if args.output_type == "adventure" else "book"
    out_dir = (
        args.out.parent if args.out
        else (normalise_path(str(args.output_dir)) if args.output_dir
              else pdf_path.parent)
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out or out_dir / f"{prefix}-{short_id.lower()}-1e.json"

    pages: set[int] = _parse_skip_pages(args.pages) if args.pages else set()
    if args.page:
        pages.add(args.page)

    # Collect skip-page sets from all --skip-pages arguments
    skip_pages: set[int] = set()
    for arg in args.skip_pages_args:
        skip_pages |= _parse_skip_pages(arg)

    debug_dir = normalise_path(str(args.debug_dir)) if args.debug_dir else None

    convert(
        pdf_path=pdf_path,
        output_type=args.output_type,
        short_id=short_id,
        module_code=args.module_code,
        author=args.author,
        out_path=out_path,
        api_key=args.api_key,
        chunk_size=args.chunk_size,
        pages=pages,
        skip_pages=skip_pages,
        dpi=args.dpi,
        force_ocr=args.force_ocr,
        lang=args.lang,
        model=args.model,
        output_mode=args.output_mode,
        dry_run_only=args.dry_run_only,
        extract_monsters=args.extract_monsters,
        monsters_only=args.monsters_only,
        no_cr_adjustment=args.no_cr_adjustment,
        no_retry=args.no_retry,
        debug_dir=debug_dir,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
