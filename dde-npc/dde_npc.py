#!/usr/bin/env python3
"""Roll an NPC with the Castle Oldskull DDE1 tables (Kent David Kelly).

Reads tables extracted by extract.py from YOUR copy of the PDF. The data
lives outside this repo (default ~/src/homebrew-private/book/dde1-castle-oldskull/
tables.json, override with $DDE_DATA).

Examples:
    dde_npc.py                         # one quick NPC, everything random
    dde_npc.py -n 5                    # five of them
    dde_npc.py --race dwarf --sex f --class fighter --full
    dde_npc.py --culture norse --alignment CE
    dde_npc.py --table step-35-speech-patterns   # roll one table
    dde_npc.py --list                  # list table keys
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import textwrap
from pathlib import Path

DATA = Path(os.environ.get(
    "DDE_DATA", Path.home() / "src/homebrew-private/book/dde1-castle-oldskull/tables.json"))

RACES = ["human", "dwarf", "elf", "half-elf", "gnome", "halfling", "half-orc"]
RACE_WEIGHTS = [60, 8, 8, 8, 5, 6, 5]
CLASSES = ["assassin", "barbarian", "bard", "cleric", "druid", "fighter", "illusionist",
           "mage", "monk", "paladin", "ranger", "thief"]
ABILITIES = ["Strength", "Intelligence", "Wisdom", "Dexterity", "Constitution", "Charisma"]
ABBR = dict(zip(["str", "int", "wis", "dex", "con", "cha"], ABILITIES))
ALIGNMENTS = ["LG", "NG", "CG", "LN", "N", "CN", "LE", "NE", "CE"]

# culture -> (female given, male given, family)
CULTURES = {
    "english": ("english-names-for-female-characters", "english-names-for-male-characters", "english-family-names"),
    "french": ("french-names-for-female-characters", "french-names-for-male-characters", "french-family-names"),
    "gaelic": ("gaelic-names-for-female-characters", "gaelic-names-for-male-characters", "gaelic-and-elven-bloodline-names"),
    "german": ("german-names-for-female-characters", "german-names-for-male-characters", "german-family-names"),
    "greek": ("greek-names-for-female-characters", "greek-names-for-male-characters", "greek-family-names"),
    "italian": ("italian-names-for-female-characters", "italian-names-for-male-characters", "italian-family-names"),
    "norse": ("norse-and-scandinavian-names-for-female-characters", "norse-and-scandinavian-names-for-male-characters", "norse-and-dwarven-clan-names"),
    "pastoral": ("pastoral-names-for-female-characters", "pastoral-names-for-male-characters", "pastoral-and-shire-bred-lineage-names"),
    "roman": ("roman-names-for-female-characters", "roman-names-for-male-characters", "roman-family-names"),
    "swiss": ("latinized-swiss-names-for-female-characters", "latinized-swiss-names-for-male-characters", "latinized-swiss-and-gnomish-clan-names"),
}
RACE_CULTURE = {"dwarf": "norse", "elf": "gaelic", "gnome": "swiss", "halfling": "pastoral", "half-orc": "tribal"}

# race -> key fragment used by each per-race table family
RACE_KEYS = {
    "trades": {"dwarf": "dwarven-trades", "elf": "elven-trades", "half-elf": "elven-trades",
               "gnome": "gnomish-trades", "half-orc": "half-orcish-trades", "halfling": "halfling-trades"},
    "skills": {"human": "skills-for-humans", "dwarf": "skills-for-dwarves", "elf": "skills-for-elves-and-half-elves",
               "half-elf": "skills-for-elves-and-half-elves", "gnome": "skills-for-gnomes",
               "half-orc": "skills-for-half-orcs", "halfling": "skills-for-halflings"},
    "lore": {"dwarf": "dwarven-racial-lore", "elf": "elven-and-half-elven-racial-lore",
             "half-elf": "elven-and-half-elven-racial-lore", "gnome": "gnomish-racial-lore",
             "half-orc": "half-orc-racial-lore", "halfling": "halfling-racial-lore"},
    "eyes": {"human": "half-elven-and-human-eye-colors", "half-elf": "half-elven-and-human-eye-colors",
             "dwarf": "dwarven-eye-colors", "elf": "elven-eye-colors", "gnome": "gnomish-eye-colors",
             "half-orc": "half-orc-eye-colors", "halfling": "halfling-eye-colors"},
    "hair": {"human": "half-elf-and-human-hair-color", "half-elf": "half-elf-and-human-hair-color",
             "dwarf": "dwarven-hair-color", "elf": "elven-hair-color", "gnome": "gnomish-hair-color",
             "half-orc": "half-orc-hair-color", "halfling": "halfling-hair-color"},
    "skin": {"human": "half-elf-and-human-skin-color", "half-elf": "half-elf-and-human-skin-color",
             "dwarf": "dwarven-skin-color", "elf": "elven-skin-color", "gnome": "gnomish-skin-color",
             "half-orc": "half-orc-skin-color", "halfling": "halfling-skin-color"},
}
SPELLS = {"cleric": "step-11-a-initial-spells-for-clerics", "druid": "step-11-b-initial-spells-for-druids",
          "illusionist": "step-11-c-initial-spells-for-illusionists", "mage": "step-11-d-initial-spells-for-mages"}
BACKGROUND_SUB = {"Common": "common-character-backgrounds", "Uncommon": "uncommon-character-backgrounds",
                  "Rare": "rare-character-backgrounds", "Very Rare": "very-rare-character-backgrounds"}
LANGUAGE_SUB = {"Common": "common-languages", "Uncommon": "uncommon-languages",
                "Rare": "rare-languages", "Very Rare": "very-rare-languages"}
HERALDRY_SUB = {"Beast": "heraldic-beasts-and-figures", "Charge": "heraldic-charges-shapes-and-symbols",
                "Ordinary": "heraldic-ordinaries-geometric-symbols"}
SHORT_RACES = {"dwarf", "gnome", "halfling"}


class Book:
    def __init__(self, path: Path, rng: random.Random):
        if not path.exists():
            sys.exit(f"No table data at {path}.\nRun extract.py against your DDE1 PDF first "
                     f"(or set $DDE_DATA).")
        d = json.loads(path.read_text())
        self.t, self.desc, self.social, self.wealth = d["tables"], d["descriptors"], d["social"], d["wealth"]
        self.rng = rng

    def roll(self, key: str, reroll_if: str | None = r"^Reroll", follow: bool = True) -> str:
        """Roll the table's die; reroll on book gaps and on 'Reroll …' entries.
        Entries that say 'roll twice' are followed: two more rolls, joined with ' + '."""
        t = self.t[key]
        for _ in range(200):
            n = self.rng.randint(1, t["die"])
            hit = next((e for e in t["entries"] if e["lo"] <= n <= e["hi"]), None)
            if not hit or (reroll_if and re.match(reroll_if, hit["text"])):
                continue
            if follow and re.search(r"roll twice", hit["text"], re.I):
                skip = r"(?i).*roll twice|^Reroll|^No "
                a = self.roll(key, skip, follow=False)
                b = self.roll(key, skip, follow=False)
                head = re.split(r"[;(.]", hit["text"])[0].strip()
                return f"{head}: {a} + {b}" if head and not head.lower().startswith("roll twice") else f"{a} + {b}"
            return hit["text"]
        raise RuntimeError(f"could not roll {key}")


def pick_or(text: str, rng: random.Random) -> str:
    """'Acte or Adeia' -> one of them. Leaves descriptive text alone."""
    parts = [p.strip() for p in re.split(r"\s+or\s+", text)]
    if 1 < len(parts) <= 3 and all(len(p.split()) <= 2 for p in parts):
        return rng.choice(parts)
    return text


def d6(n: int, rng: random.Random) -> int:
    return sum(rng.randint(1, 6) for _ in range(n))


def title_case_fragment(s: str) -> str:
    return s.replace("–", "-").strip()


class NPC:
    def __init__(self, book: Book, args):
        self.b, self.rng, self.a = book, book.rng, args
        self.lines: list[tuple[str, str]] = []

    def add(self, label: str, value: str):
        if value:
            self.lines.append((label, value))

    # ---- core identity ---------------------------------------------------
    def build(self):
        a, rng = self.a, self.rng
        self.race = a.race or rng.choices(RACES, RACE_WEIGHTS)[0]
        self.sex = {"f": "female", "m": "male"}.get((a.sex or rng.choice("fm"))[0].lower())
        if a.cls == "random":
            self.cls = rng.choice(CLASSES)
        elif a.cls is None:
            self.cls = rng.choice(CLASSES) if rng.random() < 0.5 else "commoner"
        else:
            self.cls = a.cls
        self.align = a.alignment or rng.choice(ALIGNMENTS)
        self.stats = self.roll_stats(a.stats)

        self.name()
        self.add("Race / Sex", f"{self.race.title()} {self.sex}")
        self.add("Class", self.cls.title() if self.cls != "commoner" else "None (commoner)")
        self.add("Alignment", self.align)
        self.abilities()
        self.add("Handedness", self.handedness())

        if self.cls != "commoner":
            self.add("Theme", self.b.roll(f"themes-and-level-titles-for-{self.plural(self.cls)}"))
        self.appearance()
        self.personality()
        self.background()
        self.standing()
        if a.full:
            self.full()
        return self

    @staticmethod
    def plural(c: str) -> str:
        return "thieves" if c == "thief" else c + "s"

    def roll_stats(self, given: str | None) -> dict:
        if given:
            vals = [int(x) for x in re.split(r"[,/ ]+", given.strip())]
            if len(vals) != 6:
                sys.exit("--stats needs six numbers: STR INT WIS DEX CON CHA")
            return dict(zip(ABILITIES, vals))
        return {ab: d6(3, self.rng) for ab in ABILITIES}

    # ---- steps 1-4: name and epithet -------------------------------------
    def name(self):
        b, rng = self.b, self.rng
        culture = self.a.culture
        if not culture:
            if self.race == "half-elf":
                culture = "gaelic" if rng.random() < 0.5 else None
            else:
                culture = RACE_CULTURE.get(self.race)
        if not culture:
            pick = b.roll("step-1-selecting-a-given-name")
            if pick.startswith("No name"):
                culture = "epithet-only"
            else:
                culture = pick.split(";")[0].replace(" Name", "").split()[0].lower()
                culture = {"tribal": "tribal", "norse": "norse"}.get(culture, culture)

        if culture == "epithet-only":
            given, family = "", ""
        elif culture == "tribal":
            given = b.roll("orcish-names-for-male-characters").rstrip("-") + \
                pick_or(b.roll("orcish-names-for-male-characters-2"), rng).lstrip("-–")
            given = given.capitalize()
            if self.sex == "female":
                given += b.roll("orcish-names-for-female-characters").lstrip("-")
            frag = b.roll("names-of-vengeance-for-orcish-clans").replace("The ", "")
            noun = b.roll("names-of-vengeance-for-orcish-clans-2")
            family = f"of the {frag}{noun.lower() if frag.endswith('-') is False else noun}"
            family = family.replace("--", "-")
        else:
            f_key, m_key, fam_key = CULTURES[culture]
            given = pick_or(b.roll(f_key if self.sex == "female" else m_key), rng)
            family = pick_or(b.roll(fam_key), rng)
        epithet = self.epithet()
        full = " ".join(x for x in [given, family] if x)
        full = f"{full} {epithet}".strip() if full else epithet.replace("the ", "The ", 1)
        self.culture = culture
        self.add("Name", full)
        self.add("Name culture", culture.title())

    def epithet(self) -> str:
        st, rng = self.stats, self.rng
        hi = max(st.values())
        lo = min(st.values())
        if hi > 15:
            ab = rng.choice([k for k, v in st.items() if v == hi])
            key = f"epithets-of-high-{ab.lower()}"
        elif lo < 8:
            ab = rng.choice([k for k, v in st.items() if v == lo])
            key = f"epithets-of-low-{ab.lower()}"
        else:
            law, good = self.align[0], self.align[-1]
            if self.align == "N":
                law = good = "N"
            if rng.random() < 0.6:
                key = {"G": "epithets-of-good", "E": "epithets-of-evil"}.get(good, "epithets-of-neutrality")
            else:
                key = {"L": "epithets-of-law", "C": "epithets-of-chaos"}.get(law, "epithets-of-neutrality")
        return pick_or(self.b.roll(key), rng)

    # ---- steps 5-6 ---------------------------------------------------------
    def abilities(self):
        parts = []
        for ab, v in self.stats.items():
            score = min(max(v, 3), 20)
            if ab == "Strength" and v >= 18 and self.race in SHORT_RACES:
                score = 18
            words = self.b.desc[ab].get(str(score)) or ["—"]
            parts.append(f"{ab[:3].upper()} {v:>2} {self.rng.choice(words)}")
        self.add("Abilities", "\n".join(parts))

    def handedness(self) -> str:
        r = self.b.roll("step-6-determining-handedness")
        m = re.match(r"If Dexterity 15\+, Ambidextrous Otherwise, (.*)", r)
        if m:
            return "Ambidextrous" if self.stats["Dexterity"] >= 15 else m.group(1)
        return r

    # ---- steps 26-35 -------------------------------------------------------
    def appearance(self):
        b, rk = self.b, RACE_KEYS
        self.add("Eyes", b.roll(rk["eyes"][self.race]))
        self.add("Hair", b.roll(rk["hair"][self.race]))
        self.add("Skin", b.roll(rk["skin"][self.race]))
        self.add("Grooming", b.roll("step-26-cleanliness-and-fashion"))
        self.add("Physical trait", b.roll("step-30-unusual-physical-traits"))

    def personality(self):
        b = self.b
        self.add("Demeanor", f"{b.roll('demeanor-table-1')}; {b.roll('demeanor-table-2')}")
        self.add("Likes", f"{b.roll('likes-and-dislikes-table-1')}; {b.roll('likes-and-dislikes-table-2')}")
        self.add("Dislikes", f"{b.roll('likes-and-dislikes-table-1')}; {b.roll('likes-and-dislikes-table-2')}")
        self.add("Speech", b.roll("step-35-speech-patterns"))
        self.add("Company", b.roll("step-34-preferred-culture-and-company"))

    def background(self):
        b = self.b
        tier = b.roll("step-18-determining-character-background")
        sub = next(v for k, v in sorted(BACKGROUND_SUB.items(), key=lambda kv: -len(kv[0]))
                   if tier.startswith(k))
        self.add("Background", f"{b.roll(sub)}  ({tier.split(' Background')[0].lower()})")
        if self.race != "human":
            trade = RACE_KEYS["trades"].get(self.race)
            if trade:
                self.add("Clan trade", b.roll(trade))
        self.add("Secondary skill", b.roll(RACE_KEYS["skills"][self.race]))

    # ---- steps 23 and 25 ---------------------------------------------------
    def standing(self):
        start = {("thief" if k == "thieve" else k): v for k, v in self.b.social["start_rank_by_class"].items()}
        if self.a.rank:
            rank = self.a.rank
        elif self.cls == "commoner":
            rank = self.rng.randint(68, 112)
        else:
            rank = start.get(self.cls, start.get("mage"))  # illusionists aren't listed; use mages
        peer = self.b.social["peerage"]
        near = min(peer, key=lambda k: abs(int(k) - rank))
        p = peer[near]
        caste = re.sub(r"\b([A-Z])([A-Z]+)\b", lambda m: m.group(0) if len(m.group(0)) <= 3 else
                       m.group(1) + m.group(2).lower(), p["caste"].split(" — ")[-1])
        self.add("Social standing", f"{rank} ({caste}) — peers: {', '.join(p['personages'][:3])}")
        band = next((w for w in self.b.wealth if w["from"] <= rank <= w["to"]), None)
        if band:
            m = re.match(r"(\d+)d6(?:\+(\d+))?", band["dice"])
            gp = (d6(int(m.group(1)), self.rng) + int(m.group(2) or 0)) * band["mult"]
            self.add("Purse", f"{gp} gp")
        elif rank < 42:
            self.add("Purse", "wealthy (above the starting-wealth tables)")

    # ---- the rest of the 40 steps, for --full -----------------------------
    def full(self):
        b, c, r = self.b, self.cls, self.race
        if c == "druid":
            self.add("Druidic clan", b.roll("step-8-selecting-a-druidic-clan-background"))
            self.add("Spirit companion", b.roll("step-21-druid-spirit-companions"))
        if c == "barbarian" or r == "half-orc":
            self.add("Tribal land", b.roll("step-9-tribal-themes-for-barbarians-and-half-orcs"))
            self.add("Tribal calling", b.roll("step-9-tribal-themes-for-barbarians-and-half-orcs-2"))
        if c in SPELLS:
            self.add("Spell preference", b.roll(SPELLS[c]))
        if c in ("illusionist", "mage"):
            self.add("Familiar", b.roll("step-22-familiars-for-illusionists-and-mages"))
        if c in ("monk", "thief"):
            self.add("Rogue talent", b.roll("step-15-specialized-rogue-talents-for-characters-with-thieving-skills"))
        if c == "bard":
            self.add("Bardic trickery", b.roll("step-20-bardic-trickery-and-sideshows"))
        if c != "commoner":
            self.add("Fighting style", b.roll(f"fighting-styles-for-{self.plural(c)}"))
        if r in RACE_KEYS["lore"]:
            self.add("Racial lore", b.roll(RACE_KEYS["lore"][r]))
        extra = max(0, (self.stats["Intelligence"] - 8) // 2) if self.stats["Intelligence"] > 9 else 0
        langs = []
        for _ in range(min(extra, 3)):
            tier = b.roll("step-14-random-additional-language-determination")
            sub = next(v for k, v in sorted(LANGUAGE_SUB.items(), key=lambda kv: -len(kv[0]))
                       if tier.startswith(k))
            langs.append(b.roll(sub))
        self.add("Extra languages", ", ".join(langs))
        self.add("Famous ancestor", b.roll("step-19-consideration-of-famous-historical-ancestors"))
        kind = b.roll("step-24-envisioning-coats-of-arms-and-blazons")
        sub = next(v for k, v in HERALDRY_SUB.items() if k in kind)
        self.add("Coat of arms", f"{pick_or(b.roll(sub), self.rng)} — {b.roll('heraldic-tinctures')} on "
                                 f"{b.roll('heraldic-tinctures')}")
        adj = pick_or(b.roll("party-names-table-1-adjectives"), self.rng)
        noun = pick_or(b.roll("party-names-table-2-nouns"), self.rng)
        self.add("Company / party name", f"{adj if adj.startswith('The ') else 'The ' + adj} {noun}")

    # ---- output ------------------------------------------------------------
    def render(self, width: int = 100) -> str:
        w = max(len(k) for k, _ in self.lines) + 2
        out = []
        for k, v in self.lines:
            wrapped = []
            for para in v.split("\n"):
                wrapped += textwrap.wrap(para, max(40, width - w)) or [""]
            out.append(f"{k + ':':<{w}}{wrapped[0]}")
            out += [" " * w + x for x in wrapped[1:]]
        return "\n".join(out)

    def as_dict(self) -> dict:
        return {k: v for k, v in self.lines}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-n", type=int, default=1, help="how many NPCs")
    ap.add_argument("--race", choices=RACES)
    ap.add_argument("--sex", choices=["f", "m", "female", "male"])
    ap.add_argument("--class", dest="cls", choices=CLASSES + ["commoner", "random"],
                    help="default: 50%% commoner, 50%% random class")
    ap.add_argument("--culture", choices=list(CULTURES) + ["tribal"], help="name culture (humans roll it by default)")
    ap.add_argument("--alignment", choices=ALIGNMENTS)
    ap.add_argument("--stats", help="six scores, STR INT WIS DEX CON CHA (default 3d6 each)")
    ap.add_argument("--rank", type=int, help="social standing rank 1-117 (lower is higher status)")
    ap.add_argument("--full", action="store_true", help="also roll spells, styles, heraldry, lore, etc.")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--table", help="roll a single table by key")
    ap.add_argument("--list", action="store_true", help="list table keys")
    a = ap.parse_args()

    rng = random.Random(a.seed)
    book = Book(DATA, rng)
    if a.list:
        for k, t in book.t.items():
            print(f"{k:<70} d{t['die']}  ({len(t['entries'])} entries)")
        return
    if a.table:
        if a.table not in book.t:
            close = [k for k in book.t if a.table in k]
            sys.exit(f"no table {a.table!r}" + (f"; did you mean: {', '.join(close[:8])}" if close else ""))
        for _ in range(a.n):
            print(book.roll(a.table, reroll_if=None))
        return

    npcs = [NPC(book, a).build() for _ in range(a.n)]
    if a.json:
        print(json.dumps([n.as_dict() for n in npcs], indent=2, ensure_ascii=False))
    else:
        print("\n\n".join(n.render() for n in npcs))


if __name__ == "__main__":
    main()
