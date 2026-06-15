"""Spell extraction framework for parsing HTML spell lists."""

from .base import Spell, SpellConfig, SpellExtractor
from .engines.html_parser import HTMLParserSpellExtractor

__all__ = ['Spell', 'SpellConfig', 'SpellExtractor', 'HTMLParserSpellExtractor']
