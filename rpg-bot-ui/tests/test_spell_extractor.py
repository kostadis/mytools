"""Tests for the spell extractor framework."""

import json
import os
import pytest
from spell_extractor.base import SpellConfig
from spell_extractor.engines.html_parser import HTMLParserSpellExtractor

# Load test fixtures
FIXTURES_DIR = os.path.join(os.path.dirname(__file__), 'fixtures')


@pytest.fixture
def cleric_config():
    config_path = os.path.join(os.path.dirname(__file__), '..', 'spell_extractor', 'config', 'cleric.json')
    with open(config_path) as f:
        return SpellConfig(**json.load(f))


@pytest.fixture
def wizard_config():
    config_path = os.path.join(os.path.dirname(__file__), '..', 'spell_extractor', 'config', 'wizard.json')
    with open(config_path) as f:
        return SpellConfig(**json.load(f))


@pytest.fixture
def cleric_html():
    with open(os.path.join(FIXTURES_DIR, 'cleric-spells-sample.html')) as f:
        return f.read()


@pytest.fixture
def wizard_html():
    with open(os.path.join(FIXTURES_DIR, 'wizard-spells-sample.html')) as f:
        return f.read()


def test_cleric_extraction(cleric_config, cleric_html):
    """Test Cleric spell extraction."""
    extractor = HTMLParserSpellExtractor(cleric_config)
    spells = extractor.extract_spells(cleric_html)
    
    assert 'cantrip' in spells
    assert 'level1' in spells
    assert len(spells['cantrip']) > 0
    
    # Check spell structure
    spell = spells['cantrip'][0]
    assert 'n' in spell
    assert 'r' in spell
    assert 'd' in spell
    assert spell['r'] in ['blue', 'green', 'orange', 'red']


def test_wizard_extraction(wizard_config, wizard_html):
    """Test Wizard spell extraction."""
    extractor = HTMLParserSpellExtractor(wizard_config)
    spells = extractor.extract_spells(wizard_html)
    
    assert 'cantrip' in spells
    assert len(spells['cantrip']) > 0


def test_rating_extraction(cleric_config):
    """Test rating map configuration."""
    extractor = HTMLParserSpellExtractor(cleric_config)
    config = extractor.config
    
    assert config.rating_map['rating-blue'] == 'blue'
    assert config.rating_map['rating-green'] == 'green'


def test_description_cleaning():
    """Test description cleaning utilities."""
    from spell_extractor.utils import clean_description
    
    # Test citation removal
    text = "Some description (source)"
    assert clean_description(text) == "Some description"
    
    # Test whitespace normalization
    text = "  Multiple   spaces   here  "
    assert clean_description(text) == "Multiple spaces here"
    
    # Test HTML entities
    text = "It&#8217;s a test"
    assert clean_description(text) == "It's a test"


def test_skip_names_filtering(cleric_config, cleric_html):
    """Test that skip_names filtering works."""
    extractor = HTMLParserSpellExtractor(cleric_config)
    spells = extractor.extract_spells(cleric_html)
    
    # Check that skip names are not in the results
    for level, spell_list in spells.items():
        for spell in spell_list:
            assert spell['n'] not in cleric_config.skip_names
