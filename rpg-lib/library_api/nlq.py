"""
NLQ (Natural Language Query) support for the RPG Library API.

Sends a user's free-text query to Claude Haiku, which extracts structured
search intent (game_system, product_type, tags, keywords), then runs an
FTS5 + structured SQL query against the database.
"""

import json
import os
import re
import sys

# claudelib lives in mytools/lib/; two levels up from library_api/
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from lib.claudelib import make_client, call_api  # noqa: E402

MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """You are a search assistant for a personal RPG PDF library. Parse the user's search query and extract structured search intent.

Known game systems (use exact values): D&D 5e, Pathfinder 1e, Pathfinder 2e, OSR, Call of Cthulhu, Dungeon Crawl Classics, Year Zero Engine, System Neutral, Universal, D&D 3.5e, D&D 4e, AD&D, GURPS, Savage Worlds, FATE, Powered by the Apocalypse, Blades in the Dark, Mothership, Alien RPG, Vampire: the Masquerade, Cypher System, 13th Age, Dragonbane

Known product types (use exact lowercase values): adventure, sourcebook, bestiary, magic_items, character_options, gm_aid, map_pack, character_sheet, setting, anthology, non_rpg

Known tags (use these exact snake_case values): monsters, encounters, combat, traps, dragons, spells, subclasses, feats, races, classes, backgrounds, skills, equipment, weapons, vehicles, npc, factions, lore, worldbuilding, treasure, random_tables, rules, crafting, character_creation, names, locations, undead, lair, dungeon, wilderness, urban, naval, planar, maps, battlemaps, hexcrawl, sandbox, mega_dungeon, handouts, one_shot, campaign, solo_play, horror, sci_fi, cyberpunk, steampunk, historical, mystery, dark_fantasy, humor, 5e, 5e_2024, 3_5e, osr, pf1e, pf2e, forgotten_realms, greyhawk, eberron, ravenloft, spelljammer, planescape, dragonlance, icewind_dale, underdark, waterdeep

Return ONLY valid JSON with no extra text:
{
  "game_system": "exact game system name or null",
  "product_type": "product type or null",
  "tags": ["tag1", "tag2"],
  "keywords": "key search terms as space-separated words (nouns and adjectives only)",
  "char_level": integer or null
}

char_level: the character level the user's party is at or the adventure should target.
Examples: "for level 5" → 5, "level 3-5 adventure" → 4 (midpoint), "tier 2" → 7, "high level" → null."""

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = make_client()
    return _client


def _fts_safe(text: str) -> str:
    """Sanitize text for use in an FTS5 MATCH query."""
    words = re.sub(r"[^\w\s]", " ", text).split()
    return " ".join(words[:12])


def parse_query(query: str) -> dict:
    """
    Send the query to Claude Haiku and parse the structured response.
    Returns dict with keys: game_system, product_type, tags, keywords.
    Falls back to keyword-only search on any error.
    """
    try:
        client = _get_client()
        response = call_api(client, SYSTEM_PROMPT, query, model=MODEL, max_tokens=256)
        # Strip any markdown code fences Claude might add
        text = response.strip()
        if text.startswith("```"):
            text = re.sub(r"```(?:json)?\n?", "", text).strip()
        parsed = json.loads(text)
        raw_level = parsed.get("char_level")
        char_level = None
        if isinstance(raw_level, (int, float)) and 1 <= int(raw_level) <= 30:
            char_level = int(raw_level)
        pt = parsed.get("product_type") or None
        if pt:
            pt = pt.lower().replace(" ", "_")
        return {
            "game_system": parsed.get("game_system") or None,
            "product_type": pt,
            "tags": [t for t in (parsed.get("tags") or []) if isinstance(t, str)],
            "keywords": _fts_safe(parsed.get("keywords") or query),
            "char_level": char_level,
        }
    except Exception:
        # Fallback: treat the whole query as keywords
        return {
            "game_system": None,
            "product_type": None,
            "tags": [],
            "keywords": _fts_safe(query),
            "char_level": None,
        }
