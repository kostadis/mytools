"""Base classes and data structures for class extractors."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from abc import ABC, abstractmethod


@dataclass
class ClassData:
    """Represents extracted character class data."""
    name: str
    edition: str
    ui: Dict[str, Any] = field(default_factory=dict)
    subclasses: List[Dict] = field(default_factory=list)
    species: List[Dict] = field(default_factory=list)
    arrays: List[Dict] = field(default_factory=list)
    ability_notes: List[Dict] = field(default_factory=list)
    skills: List[Dict] = field(default_factory=list)
    backgrounds: List[Dict] = field(default_factory=list)
    feats: List[Dict] = field(default_factory=list)
    epic_boons: List[Dict] = field(default_factory=list)
    class_features: List[Dict] = field(default_factory=list)
    weapons: List[Dict] = field(default_factory=list)
    armor: List[Dict] = field(default_factory=list)


@dataclass
class SectionConfig:
    """Configuration for a class section."""
    header_text: str
    header_id: Optional[str] = None
    parser: str = "text"  # text, html, etc.


@dataclass
class ClassConfig:
    """Configuration for a class extractor."""
    engine: str
    class_name: str
    edition: str
    sections: List[SectionConfig] = field(default_factory=list)
    rating_map: Dict[str, str] = field(default_factory=dict)
    ui_defaults: Dict[str, Any] = field(default_factory=dict)


class ClassExtractor(ABC):
    """Base class for character class extractors."""
    
    def __init__(self, config: ClassConfig):
        self.config = config
        self.data = ClassData(
            name=config.class_name,
            edition=config.edition,
            ui=config.ui_defaults.copy()
        )
    
    @abstractmethod
    def extract(self, content: str) -> ClassData:
        """Extract class data from content."""
        pass
    
    def get_rating(self, desc: str) -> str:
        """Determine rating based on description text."""
        desc_lower = desc.lower()
        if any(word in desc_lower for word in ['fantastic', 'absolutely', 'essential', 'amazing', 'best']):
            return 'blue'
        elif any(word in desc_lower for word in ['good', 'great', 'useful', 'important']):
            return 'green'
        elif any(word in desc_lower for word in ['bad', 'useless', 'terrible', 'skip']):
            return 'red'
        elif any(word in desc_lower for word in ['decent', 'some', 'ok']):
            return 'orange'
        return 'orange'
    
    def to_dict(self) -> Dict:
        """Convert ClassData to dictionary for JSON serialization."""
        return {
            "name": self.data.name,
            "edition": self.data.edition,
            "ui": self.data.ui,
            "subclasses": self.data.subclasses,
            "species": self.data.species,
            "arrays": self.data.arrays,
            "abilityNotes": self.data.ability_notes,
            "skills": self.data.skills,
            "backgrounds": self.data.backgrounds,
            "feats": self.data.feats,
            "epicBoons": self.data.epic_boons,
            "classFeatures": self.data.class_features,
            "weapons": self.data.weapons,
            "armor": self.data.armor
        }
