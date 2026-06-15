#!/usr/bin/env python3
"""Extract wizard spell data from wizard-spells-2024.html and convert to JSON."""

import json
import os
import sys

# Add parent directory to path for imports
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from spell_extractor.base import SpellConfig
from spell_extractor.engines.html_parser import HTMLParserSpellExtractor

CONFIG_FILE = os.path.join(SCRIPT_DIR, 'spell_extractor', 'config', 'wizard.json')
HTML_FILE = os.path.join(SCRIPT_DIR, 'wizard-spells-2024.html')
OUTPUT_FILE = os.path.join(SCRIPT_DIR, 'data', 'wizard-spells-2024.json')


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
    
    # Create the JSON structure
    data = {
        'meta': {
            'id': 'wizard-spells-2024',
            'name': 'Wizard',
            'edition': '2024'
        },
        'ui': {
            'knownPerLevel': {
                'cantrip': 3,  # Wizard knows 3 cantrips at level 1
                'level1': 6,   # Wizard knows 6 level 1 spells at level 1
                'level2': 4,   # Wizard knows 4 level 2 spells at level 3
                'level3': 4,   # Wizard knows 4 level 3 spells at level 5
                'level4': 4    # Wizard knows 4 level 4 spells at level 7
            }
        },
        'slots': {
            1: 2, 2: 3, 3: 4, 4: 4, 5: 4, 6: 4, 7: 4, 8: 4, 9: 4, 10: 4,
            11: 4, 12: 4, 13: 4, 14: 4, 15: 4, 16: 4, 17: 4, 18: 4, 19: 4, 20: 4
        }
    }
    
    # Add spells to data
    for level, spells_list in spells.items():
        data[level] = spells_list
    
    # Write output
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    total = sum(len(spells.get(k, [])) for k in ['cantrip', 'level1', 'level2', 'level3', 'level4'])
    print(f"Done! Total spells extracted: {total}")
    
    # Show first spell as sample
    if spells.get('cantrip'):
        print(f"\nSample spell: {spells['cantrip'][0]}")


if __name__ == '__main__':
    main()
