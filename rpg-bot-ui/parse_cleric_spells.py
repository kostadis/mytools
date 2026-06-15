#!/usr/bin/env python3
"""Parse the Cleric spells HTML file and generate JSON for the spell builder."""

import json
import os
import sys

# Add parent directory to path for imports
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from spell_extractor.base import SpellConfig
from spell_extractor.engines.html_parser import HTMLParserSpellExtractor

CONFIG_FILE = os.path.join(SCRIPT_DIR, 'spell_extractor', 'config', 'cleric.json')
HTML_FILE = os.path.join(SCRIPT_DIR, 'cleric-spells-2024.html')
OUTPUT_FILE = os.path.join(SCRIPT_DIR, 'data', 'cleric-spells-2024.json')


def main():
    # Load config
    with open(CONFIG_FILE, 'r') as f:
        config_data = json.load(f)
    
    config = SpellConfig(**config_data)
    
    # Create extractor and parse
    extractor = HTMLParserSpellExtractor(config)
    
    with open(HTML_FILE, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    spells = extractor.extract_spells(html_content)
    
    # Build output
    data = {
        'cantrip': spells['cantrip'],
        'level1': spells['level1'],
        'level2': spells['level2'],
        'level3': spells['level3'],
        'level4': spells['level4'],
        'level5': spells['level5'],
        'level6': spells['level6'],
        'level7': spells['level7'],
        'level8': spells['level8'],
        'level9': spells['level9'],
        'meta': {
            'name': 'Cleric',
            'edition': '2024'
        },
        'ui': {
            'knownPerLevel': {
                'cantrip': 2, 'level1': 2, 'level2': 2, 'level3': 2,
                'level4': 2, 'level5': 2, 'level6': 2, 'level7': 2,
                'level8': 2, 'level9': 2
            }
        },
        'slots': {
            '1': 2, '2': 3, '3': 4, '4': 4, '5': 4,
            '6': 3, '7': 3, '8': 3, '9': 3
        }
    }
    
    # Write JSON
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(data, f, indent=2)
    
    # Print summary
    print("=== Cleric Spells Parsed ===")
    total = sum(len(spells[k]) for k in spells)
    for level, spell_list in spells.items():
        print(f"{level}: {len(spell_list)} spells")
    print(f"\nTotal: {total} spells")
    print(f"\nWritten to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
