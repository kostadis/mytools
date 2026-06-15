#!/usr/bin/env python3
"""Parse character class text or HTML files using the class_extractor framework."""

import json
import sys
from pathlib import Path

from class_extractor import ClassConfig, TextClassExtractor, HTMLClassExtractor
from class_extractor.base import SectionConfig


def load_config(config_path: str) -> ClassConfig:
    """Load class configuration from JSON file."""
    with open(config_path) as f:
        data = json.load(f)
    
    sections = [SectionConfig(**s) for s in data.get('sections', [])]
    
    return ClassConfig(
        engine=data['engine'],
        class_name=data['class_name'],
        edition=data['edition'],
        sections=sections,
        ui_defaults=data.get('ui_defaults', {})
    )


def parse_class(input_file: str, config_path: str, output_file: str | None = None):
    """Parse a class text or HTML file and optionally write JSON output."""
    # Load config
    config = load_config(config_path)
    
    # Read input file
    with open(input_file, 'r') as f:
        content = f.read()
    
    # Choose extractor based on config engine
    if config.engine == 'html':
        extractor = HTMLClassExtractor(config)
    else:
        extractor = TextClassExtractor(config)
    
    # Extract data
    data = extractor.extract(content)
    
    # Convert to dict
    result = extractor.to_dict()
    
    # Print summary
    print(f"\n=== {data.name} {data.edition} ===")
    print(f"Subclasses: {len(data.subclasses)}")
    for sub in data.subclasses:
        print(f"  - {sub['name']} ({sub['r']})")
    
    print(f"Class Features: {len(data.class_features)}")
    for feat in data.class_features[:10]:
        print(f"  Lv{feat['lv']}: {feat['n']} ({feat['r']})")
    if len(data.class_features) > 10:
        print(f"  ... and {len(data.class_features) - 10} more")
    
    print(f"Ability Notes: {len(data.ability_notes)}")
    print(f"Skills: {len(data.skills)}")
    print(f"Backgrounds: {len(data.backgrounds)}")
    print(f"Feats: {len(data.feats)}")
    print(f"Epic Boons: {len(data.epic_boons)}")
    print(f"Weapons: {len(data.weapons)}")
    print(f"Armor: {len(data.armor)}")
    
    # Write output if specified
    if output_file:
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)
        print(f"\nWritten to: {output_file}")
    
    return result


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python parse_class.py <input_file> <config_file> [output_file]")
        print("Example (HTML): python parse_class.py barbarian-2024.html class_extractor/config/barbarian.json data/barbarian-2024.json")
        print("Example (Text): python parse_class.py cleric.txt class_extractor/config/cleric.json data/cleric-2024.json")
        sys.exit(1)
    
    input_file = sys.argv[1]
    config_file = sys.argv[2]
    output_file = sys.argv[3] if len(sys.argv) > 3 else None
    
    parse_class(input_file, config_file, output_file)
