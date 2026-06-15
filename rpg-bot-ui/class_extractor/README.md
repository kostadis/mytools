# Class Extractor Framework

A refactored, reusable framework for parsing character class data from RPGBOT text files.

## Overview

The `class_extractor` module provides a clean, extensible architecture for extracting character class data from parsed RPGBOT articles. It follows the same pattern as the `spell_extractor` framework.

## Structure

```
class_extractor/
├── __init__.py          # Package exports
├── base.py              # Core data classes and abstract base
├── utils.py             # Utility functions
└── engines/
    └── text_parser.py   # Text-based parser implementation
```

## Quick Start

### 1. Create a Configuration File

Create a JSON config in `class_extractor/config/`:

```json
{
  "engine": "text",
  "class_name": "Cleric",
  "edition": "2024",
  "ui_defaults": {
    "skillPicks": 2,
    "hasExpertise": false,
    "optionalTitle": "Divine Order Options"
  }
}
```

### 2. Use the Parser

```python
from class_extractor import ClassConfig, TextClassExtractor
import json

# Load config
with open('class_extractor/config/cleric.json') as f:
    config_data = json.load(f)

config = ClassConfig(**config_data)

# Parse the text file
with open('cleric.txt') as f:
    content = f.read()

extractor = TextClassExtractor(config)
data = extractor.extract(content)

# Convert to dictionary
result = extractor.to_dict()

# Save to JSON
with open('data/cleric-2024.json', 'w') as f:
    json.dump(result, f, indent=2)
```

### 3. Use the Command-Line Tool

```bash
python3 parse_class.py cleric.txt class_extractor/config/cleric.json data/cleric-2024.json
```

## Adding a New Class

To add support for a new character class:

### For HTML Files (e.g., barbarian-2024.html)

#### Step 1: Create the Config

Create `class_extractor/config/{class_name}.json`:

```json
{
  "engine": "html",
  "class_name": "Barbarian",
  "edition": "2024",
  "ui_defaults": {
    "skillPicks": 2,
    "hasExpertise": false,
    "subclassDesc": "Choose your Primal Path at level 3."
  }
}
```

#### Step 2: Run the Parser

```bash
python3 parse_class.py barbarian-2024.html class_extractor/config/barbarian.json data/barbarian-2024.json
```

### For Text Files (e.g., cleric.txt)

#### Step 1: Create the Config

Create `class_extractor/config/{class_name}.json`:

```json
{
  "engine": "text",
  "class_name": "Cleric",
  "edition": "2024",
  "ui_defaults": {
    "skillPicks": 2,
    "hasExpertise": false,
    "optionalTitle": "Divine Order Options"
  }
}
```

#### Step 2: Run the Parser

```bash
python3 parse_class.py cleric.txt class_extractor/config/cleric.json data/cleric-2024.json
```

### Step 3: Review and Adjust

Check the output and adjust the parser if needed. The `TextClassExtractor` has built-in methods for common sections:

- `_extract_subclasses()` - Extracts subclass/divine order data
- `_extract_class_features()` - Extracts level-based features
- `_extract_backgrounds()` - Extracts background recommendations
- `_extract_species()` - Extracts species/race recommendations
- `_extract_ability_scores()` - Extracts ability score breakdowns
- `_extract_skills()` - Extracts skill recommendations
- `_extract_feats()` - Extracts feat recommendations
- `_extract_epic_boons()` - Extracts epic boon data
- `_extract_weapons()` - Extracts weapon recommendations
- `_extract_armor()` - Extracts armor recommendations

If your class has unique sections, you can override these methods in a custom extractor class.

## Data Structure

The extracted data follows this schema:

```python
{
  "name": "Cleric",
  "edition": "2024",
  "ui": {
    "skillPicks": 2,
    "hasExpertise": false,
    ...
  },
  "subclasses": [
    {"name": "Protector", "r": "green", "d": "..."},
    ...
  ],
  "species": [
    {"n": "Dwarf", "src": "PHB", "r": "blue", "d": "..."},
    ...
  ],
  "abilityNotes": [
    {"s": "Wis", "r": "blue", "n": "Your primary ability score."},
    ...
  ],
  "skills": [
    {"n": "History", "r": "green", "d": "..."},
    ...
  ],
  "backgrounds": [
    {"n": "Sage", "r": "blue", "d": "..."},
    ...
  ],
  "feats": [
    {"n": "Alert", "r": "green", "cat": "general", "d": "..."},
    ...
  ],
  "epicBoons": [...],
  "classFeatures": [
    {"lv": 1, "n": "Spellcasting", "r": "blue", "d": "..."},
    ...
  ],
  "weapons": [...],
  "armor": [...]
}
```

## Rating System

The framework uses the standard RPGBOT color coding:

- **blue**: Fantastic/essential options
- **green**: Good options, useful often
- **orange**: OK options, situational
- **red**: Bad/useless options

The `get_rating()` method automatically determines ratings from text keywords.

## Engines

The framework includes two extraction engines:

### HTMLClassExtractor

Parses RPGBOT HTML articles using Python's `HTMLParser` (no regex on HTML!).

**Features:**
- Proper HTML parsing with state tracking
- Extracts subclasses from `<ul class="wp-block-list">` elements
- Extracts class features from numbered paragraphs
- Extracts ability scores and skills from paragraph text
- Skips script/style tags (ads, analytics)
- Cleans descriptions and normalizes whitespace

**Use when:** You have HTML files from RPGBOT (e.g., `barbarian-2024.html`)

### TextClassExtractor

Parses pre-extracted text files (like `cleric.txt`).

**Features:**
- Finds sections by looking for 2nd occurrence of headers
- Extracts subclasses, backgrounds, species, ability scores
- Extracts skills, feats, epic boons, weapons, armor
- Handles multi-line descriptions

**Use when:** You have text files extracted from HTML (older workflow)

## Extending the Framework

### Custom Extractor

For classes with unique structures, create a custom extractor:

```python
from class_extractor.engines.html_parser import HTMLClassExtractor

class WizardExtractor(HTMLClassExtractor):
    def _process_subclass_li(self):
        # Custom logic for Wizard's Arcane Traditions
        pass
    
    def _process_paragraph(self, text):
        # Add custom paragraph handling
        pass
```

### Custom Engine

For different source formats (Markdown, JSON, etc.), create a new engine:

```python
from class_extractor.base import ClassExtractor

class MarkdownClassExtractor(ClassExtractor):
    def extract(self, content):
        # Parse Markdown instead of HTML
        pass
```

## Migration from parse_cleric.py

The old `parse_cleric.py` script is now deprecated. To migrate:

1. Create a config file: `class_extractor/config/cleric.json`
2. Run: `python3 parse_class.py cleric.txt class_extractor/config/cleric.json data/cleric-2024.json`
3. The output format is compatible with the existing build system

## Troubleshooting

### Sections Not Being Extracted

Check that:
- The section header appears at least twice in the file (TOC + content)
- The header text matches exactly (case-sensitive)
- There are no typos in the section name

### Wrong Data Being Extracted

Adjust the `next_sections` list in the extraction method to properly bound the section.

### Rating Not Working

The `get_rating()` method looks for keywords in the description. Add more keywords to the method if needed.
