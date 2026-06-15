"""HTML-based class extractor for RPGBOT HTML articles.

This module provides a proper HTML parser (using Python's HTMLParser, no regex)
for extracting character class data from RPGBOT HTML articles.
"""

import re
from html.parser import HTMLParser
from typing import Dict, List, Optional, Any

from class_extractor.base import ClassExtractor, ClassConfig, ClassData
from class_extractor.utils import clean_description


class HTMLClassExtractor(ClassExtractor):
    """Extracts class data from HTML content using proper HTML parsing.
    
    This extractor uses Python's HTMLParser class to parse HTML structure,
    avoiding regex which is unreliable for HTML parsing.
    """
    
    def __init__(self, config: ClassConfig):
        super().__init__(config)
        self._parser = _HTMLClassParser(self)
    
    def extract(self, content: str) -> ClassData:
        """Extract class data from HTML content."""
        self._parser.feed(content)
        return self.data


class _HTMLClassParser(HTMLParser):
    """HTML parser for extracting class data from RPGBOT articles."""
    
    def __init__(self, extractor: HTMLClassExtractor):
        super().__init__()
        self.extractor = extractor
        self.data = extractor.data
        self.config = extractor.config
        
        # State tracking
        self.in_subclass_list = False
        self.in_subclass_li = False
        self.in_p = False
        self.current_text: List[str] = []
        self.in_script = False
        self.in_style = False
    
    def handle_starttag(self, tag: str, attrs: List[tuple]) -> None:
        attrs_dict = dict(attrs)
        class_attr = attrs_dict.get('class', '')
        
        # Skip script and style tags
        if tag == 'script':
            self.in_script = True
            return
        if tag == 'style':
            self.in_style = True
            return
        
        # Check for subclass lists (wp-block-list ul)
        if tag == 'ul' and 'wp-block-list' in str(class_attr):
            self.in_subclass_list = True
        
        if tag == 'li' and self.in_subclass_list:
            self.in_subclass_li = True
            self.current_text = []
        
        # Track paragraph tags for class features
        if tag == 'p':
            self.in_p = True
            self.current_text = []
    
    def handle_endtag(self, tag: str) -> None:
        if tag == 'script':
            self.in_script = False
            return
        if tag == 'style':
            self.in_style = False
            return
        
        if tag == 'ul':
            self.in_subclass_list = False
        
        if tag == 'li' and self.in_subclass_li:
            self._process_subclass_li()
            self.in_subclass_li = False
        
        if tag == 'p' and self.in_p:
            text = ''.join(self.current_text).strip()
            if text:
                self._process_paragraph(text)
            self.in_p = False
            self.current_text = []
    
    def handle_data(self, data: str) -> None:
        if self.in_script or self.in_style:
            return
        
        if self.in_subclass_li or self.in_p:
            self.current_text.append(data)
    
    def _process_subclass_li(self) -> None:
        """Process extracted subclass from li element."""
        text = ''.join(self.current_text).strip()
        
        # Check if this is a "Path of the X" entry
        if 'Path of the' in text and ':' in text:
            # Split on first colon
            colon_idx = text.index(':')
            full_name = text[:colon_idx].strip()
            desc = text[colon_idx + 1:].strip()
            
            # Extract subclass name (remove "Path of the")
            if full_name.startswith('Path of the '):
                name = full_name[12:].strip()
            else:
                name = full_name
            
            # Clean description
            desc = re.sub(r'\s+', ' ', desc)
            desc = clean_description(desc, max_length=250)
            
            # Determine rating
            rating = self.extractor.get_rating(desc)
            
            self.data.subclasses.append({
                "name": name,
                "r": rating,
                "d": desc
            })
    
    def _process_paragraph(self, text: str) -> None:
        """Process a paragraph that might contain class features or other data."""
        # Check for numbered class features: "N. FeatureName: Description"
        match = re.match(r'^(\d+)\.\s+([A-Z][a-zA-Z\s]+):\s*(.+)$', text, re.DOTALL)
        
        if match:
            level = int(match.group(1))
            name = match.group(2).strip()
            desc = match.group(3).strip()
            
            # Clean description
            desc = re.sub(r'\s+', ' ', desc).strip()
            desc = clean_description(desc, max_length=300)
            
            # Determine rating
            rating = self.extractor.get_rating(desc)
            
            # Avoid duplicates
            if not any(feat['n'] == name and feat['lv'] == level for feat in self.data.class_features):
                self.data.class_features.append({
                    "lv": level,
                    "n": name,
                    "r": rating,
                    "d": desc
                })
            return
        
        # Check for ability score patterns: "Str: Description" or "Strength: Description"
        ab_match = re.match(r'^(Str|Dex|Con|Int|Wis|Cha|Strength|Dexterity|Constitution|Intelligence|Wisdom|Charisma):\s*(.+)$', text)
        if ab_match:
            stat = ab_match.group(1)
            # Normalize stat names
            stat_map = {
                'Strength': 'Str', 'Dexterity': 'Dex', 'Constitution': 'Con',
                'Intelligence': 'Int', 'Wisdom': 'Wis', 'Charisma': 'Cha'
            }
            stat = stat_map.get(stat, stat)
            
            desc = ab_match.group(2).strip()
            desc = clean_description(desc, max_length=200)
            
            rating = self.extractor.get_rating(desc)
            
            # Avoid duplicates
            if not any(note['s'] == stat and note['n'] == desc for note in self.data.ability_notes):
                self.data.ability_notes.append({
                    "s": stat,
                    "r": rating,
                    "n": desc
                })
            return
        
        # Check for skill patterns: "SkillName (Abbrev): Description"
        skill_match = re.match(r'^([A-Z][a-z]+)\s+\([A-Z][a-z]{2}\):\s*(.+)$', text)
        if skill_match:
            name = skill_match.group(1).strip()
            desc = skill_match.group(2).strip()
            desc = clean_description(desc, max_length=200)
            
            rating = self.extractor.get_rating(desc)
            
            # Avoid duplicates
            if not any(skill['n'] == name for skill in self.data.skills):
                self.data.skills.append({
                    "n": name,
                    "r": rating,
                    "d": desc
                })
            return
