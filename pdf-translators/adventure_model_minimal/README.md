# adventure-model-minimal

A Rust library for parsing 5etools adventure JSON format with Python bindings.

## Installation

```bash
pip install adventure-model-minimal
```

## Usage

```python
import adventure_model_minimal

# Parse a single entry
entry = adventure_model_minimal.parse_entry('{"type": "section", "name": "The Dungeon", "id": "dungeon-1", "page": 1}')

# Parse a complete document
adventure = adventure_model_minimal.parse_document('{"_meta": {"sources": [{"id": "TOWORLDS", "name": "Tales of the World"}]}, "data": [{"type": "section", "name": "The Dungeon", "id": "dungeon-1", "page": 1, "entries": [{"type": "table", "name": "Monsters", "headers": ["Name", "AC", "HP"], "rows": [["Orc", "13", "15"]]}]}]}')

# Access the TOC
print(adventure.toc)
```

## Error Handling

The parser raises `ValueError` for invalid input:

```python
try:
    entry = adventure_model_minimal.parse_entry('{"type": "invalid"}')
except ValueError as e:
    print(f"Error: {e}")
```

## Development

To build from source:

```bash
cd adventure_model_minimal
pip install -e .
```

## License

MIT License
