"""Shared utilities for spell extraction."""

import re
from typing import Union, List, Dict


def extract_rating(class_attrs: Union[str, List[str]], 
                   rating_map: Dict[str, str],
                   prefix: str) -> str:
    """Extract rating from CSS class attributes."""
    classes = class_attrs if isinstance(class_attrs, list) else [class_attrs]
    for cls in classes:
        if isinstance(cls, str) and cls.startswith(prefix):
            return rating_map.get(cls, 'orange')
    return 'orange'


def clean_description(text: str, remove_citations: bool = True) -> str:
    """Normalize whitespace, remove citations, clean HTML entities."""
    if remove_citations:
        text = re.sub(r'\s*\([^)]+\)\s*$', '', text).strip()
    
    text = ' '.join(text.split())
    
    # HTML entities
    entities = {
        '&#8217;': "'", '&#8216;': "'", '&#8220;': '"',
        '&#8221;': '"', '&#8212;': '-', '&#8230;': '...'
    }
    for entity, char in entities.items():
        text = text.replace(entity, char)
    
    # Remove leading ": " or ":"
    text = text.lstrip(': ').strip()
    
    return ' '.join(text.split())
