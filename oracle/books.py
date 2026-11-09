"""The three Nord Games Oracle generators: where the PDFs and extracted tables live.

Every book has the same shape: themes (environments, for monsters), each opened
by a one-line title page; five sections per theme; each section is a d12 index
page (result -> page) followed by pages of d4 option tables.

Tables are the books' own content, so they live OUTSIDE this public repo:
    $ORACLE_DATA_DIR/<slug>/tables.json   (default ~/src/homebrew-private/book)
"""
from __future__ import annotations

import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("ORACLE_DATA_DIR", Path.home() / "src/homebrew-private/book"))

BOOKS: dict[str, dict] = {
    "npc": {
        "title": "The Oracle Character Generator",
        "slug": "oracle-character-generator",
        "rpg_lib_id": 1168,  # the InDesign 18.5 build; 1167/1169/14435 are an older one (issue #106)
        "pdf": "/mnt/g/My Drive/Kickstarter/NordGames/Oracle Character Generator PDF/"
               "The_Oracle_Character_Generator.pdf",
        "theme_label": "theme",
        "themes": 5,
        "sections": ["Role", "Personality", "Motivation", "Flaw", "Intrigue"],
    },
    "monster": {
        "title": "The Oracle Monster Generator",
        "slug": "oracle-monster-generator",
        "rpg_lib_id": 1170,
        "pdf": "/mnt/g/My Drive/Kickstarter/NordGames/Oracle Generator Monster PDF/"
               "The_Oracle_Monster_Generator_PDF.pdf",
        "theme_label": "environment",
        "themes": 7,
        "sections": ["Monster Type", "Behavior", "Archetype", "Special Ability", "Intrigue"],
    },
    "story": {
        "title": "The Oracle Story Generator",
        "slug": "oracle-story-generator",
        "rpg_lib_id": 10342,
        "pdf": "/mnt/g/My Drive/DriveThru/Nord Games/Oracle Story Generator (System Neutral)/"
               "The_Oracle_Story_Generator.pdf",
        "theme_label": "theme",
        "themes": 5,
        "sections": ["Actor", "Action", "Subject", "Intent", "Development"],
    },
}


def tables_path(book: str) -> Path:
    return DATA_DIR / BOOKS[book]["slug"] / "tables.json"
