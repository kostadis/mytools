"""Base classes and data structures for spell extractors."""

from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from abc import ABC, abstractmethod


@dataclass
class Spell:
    """Represents a single spell entry."""
    n: str   # name
    r: str   # rating: blue/green/orange/red
    d: str   # description


@dataclass  
class LevelSection:
    """Configuration for a spell level section."""
    header_text: str
    header_id: Optional[str]
    json_key: str
    ul_id: Optional[str]


@dataclass
class SpellConfig:
    """Configuration for a spell extractor."""
    engine: str
    rating_map: Dict[str, str]
    rating_class_prefix: str
    skip_names: List[str]
    level_sections: List[LevelSection]
    description_cleanup: Dict[str, Any]


class SpellExtractor(ABC):
    """Base class for spell extractors."""
    
    def __init__(self, config: SpellConfig):
        self.config = config
    
    @abstractmethod
    def extract_spells(self, html_content: str) -> Dict[str, List[Spell]]:
        """Extract spells from HTML content."""
        pass
    
    def filter_spells(self, spells: List[Spell]) -> List[Spell]:
        """Remove non-spell entries (like rating color names)."""
        return [s for s in spells if s.n not in self.config.skip_names]
    
    def build_output(self, spells_by_level: Dict[str, List[Spell]], 
                     meta: Dict, ui: Dict, slots: Dict) -> Dict:
        """Build final JSON output structure."""
        data = {'meta': meta, 'ui': ui, 'slots': slots}
        for level, spells in spells_by_level.items():
            data[level] = self.filter_spells(spells)
        return data
