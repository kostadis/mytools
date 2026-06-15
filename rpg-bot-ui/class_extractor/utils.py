"""Utility functions for class extractors."""

import re
from typing import List, Optional


def clean_description(text: str, max_length: int = 500, remove_citations: bool = True) -> str:
    """Clean up description text."""
    # Remove citations like (PHB), (EFotA), etc.
    if remove_citations:
        text = re.sub(r'\s*\([^)]*\)\s*', ' ', text)
    
    # Replace newlines with spaces
    text = re.sub(r'\s+', ' ', text)
    
    # Truncate to max length
    if len(text) > max_length:
        text = text[:max_length].rsplit(' ', 1)[0] + '...'
    
    return text.strip()


def find_section(text: str, section_name: str, next_sections: Optional[List[str]] = None) -> Optional[str]:
    """Find a section in text starting from the 2nd occurrence of section_name."""
    positions = [m.start() for m in re.finditer(re.escape(section_name), text, re.IGNORECASE)]
    
    if len(positions) < 2:
        return None
    
    start = positions[1]
    end = len(text)
    
    if next_sections:
        for next_sec in next_sections:
            pos = text.find(next_sec, start)
            if pos != -1 and pos < end:
                end = pos
    
    return text[start:end].strip()


def parse_rating_from_text(text: str) -> str:
    """Extract rating from text based on keywords."""
    text_lower = text.lower()
    if any(word in text_lower for word in ['fantastic', 'absolutely', 'essential', 'amazing', 'best']):
        return 'blue'
    elif any(word in text_lower for word in ['good', 'great', 'useful', 'important']):
        return 'green'
    elif any(word in text_lower for word in ['bad', 'useless', 'terrible', 'skip']):
        return 'red'
    return 'orange'
