"""HTMLParser-based spell extractor."""

from html.parser import HTMLParser
from typing import Dict, List, Any

from spell_extractor.base import SpellExtractor, SpellConfig, Spell, LevelSection
from spell_extractor.utils import clean_description


class HTMLParserSpellExtractor(SpellExtractor):
    """HTMLParser-based spell extractor."""
    
    def __init__(self, config: SpellConfig):
        super().__init__(config)
        self._init_state()
    
    def _init_state(self):
        """Reset parser state."""
        self.spells = {sec['json_key']: [] for sec in self.config.level_sections}
        self.current_level = None
        self.current_spell_name = None
        self.current_rating = None
        self.current_desc = []
        self.in_li = False
        self.in_span = False
        self.in_sup = False
        self.in_p = False
        self.in_h3 = False
        self.in_h2 = False
        self.in_spell_section = False
        self.in_spell_ul = False
    
    def extract_spells(self, html_content: str) -> Dict[str, List[Spell]]:
        """Parse HTML and extract spells."""
        self._init_state()
        
        parser = _HTMLParserAdapter(self)
        parser.feed(html_content)
        
        return self.spells


class _HTMLParserAdapter(HTMLParser):
    """Adapter between HTMLParser and our extractor."""
    
    def __init__(self, extractor: HTMLParserSpellExtractor):
        super().__init__()
        self.extractor = extractor
        self.config = self.extractor.config
        self.rating_map = self.config.rating_map
    
    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        class_name = attrs_dict.get('class', '')
        
        # Check for section headers
        if isinstance(class_name, str):
            if tag == 'h3' and class_name.startswith('wp-block-heading'):
                self.extractor.in_h3 = True
            if tag == 'h2' and class_name.startswith('wp-block-heading'):
                self.extractor.in_h2 = True
        
        # Track ul elements
        if tag == 'ul':
            ul_id = attrs_dict.get('id', '')
            # Check if this is a spell UL
            for sec in self.config.level_sections:
                if sec['ul_id'] and ul_id == sec['ul_id']:
                    self.extractor.in_spell_ul = True
                    break
                elif not sec['ul_id'] and self.extractor.in_spell_section:
                    self.extractor.in_spell_ul = True
                    break
        
        # Track li elements
        if tag == 'li' and self.extractor.in_spell_ul:
            self.extractor.in_li = True
            self.extractor.current_desc = []
        
        # Track span for spell name and rating
        if tag == 'span' and self.extractor.in_li:
            if isinstance(class_name, str) and class_name.startswith('rating-'):
                self.extractor.in_span = True
                self.extractor.current_rating = self.rating_map.get(class_name, 'orange')
        
        # Track sup for sources
        if tag == 'sup' and self.extractor.in_li:
            self.extractor.in_sup = True
        
        # Track paragraphs
        if tag == 'p' and self.extractor.in_li:
            self.extractor.in_p = True
    
    def handle_endtag(self, tag):
        if tag == 'h3':
            self.extractor.in_h3 = False
        elif tag == 'h2':
            self.extractor.in_h2 = False
        elif tag == 'ul':
            self.extractor.in_spell_ul = False
        elif tag == 'li':
            if self.extractor.current_spell_name and self.extractor.current_rating:
                desc_text = ' '.join(self.extractor.current_desc).strip()
                desc_text = clean_description(desc_text)
                if desc_text.startswith(':'):
                    desc_text = desc_text[1:].strip()
                
                level = self.extractor.current_level or 'level1'
                if level in self.extractor.spells:
                    self.extractor.spells[level].append({
                        'n': self.extractor.current_spell_name,
                        'r': self.extractor.current_rating,
                        'd': desc_text[:500]
                    })
            self.extractor.in_li = False
            self.extractor.current_spell_name = None
            self.extractor.current_rating = None
            self.extractor.current_desc = []
        elif tag == 'span':
            self.extractor.in_span = False
        elif tag == 'sup':
            self.extractor.in_sup = False
        elif tag == 'p':
            self.extractor.in_p = False
    
    def handle_data(self, data):
        # Check for section headers
        if self.extractor.in_h3 or self.extractor.in_h2:
            text = data.strip().lower()
            for sec in self.config.level_sections:
                # Compare lowercase versions
                if sec['header_text'].lower() in text:
                    self.extractor.current_level = sec['json_key']
                    self.extractor.in_spell_section = True
                    break
            return
        
        # Skip if not in a spell li
        if not self.extractor.in_li:
            return
        
        # Extract spell name
        if self.extractor.in_span and self.extractor.current_spell_name is None:
            name = data.strip()
            if name:
                self.extractor.current_spell_name = name
            return
        
        # Skip source citations
        if self.extractor.in_sup:
            return
        
        # Collect description
        self.extractor.current_desc.append(data.strip())
