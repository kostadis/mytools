#!/usr/bin/env python3
"""
Integration tests for Rust adventure_model implementation.

Tests the full pipeline: JSON parsing, validation, ID assignment, TOC building,
and serialization. Compares Rust output against expected Python behavior.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Test data fixtures
FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def simple_adventure():
    """A simple valid adventure."""
    return {
        "_meta": {
            "sources": [
                {"json": "TEST", "abbreviation": "T", "full": "Test Adventure"}
            ]
        },
        "adventure": [
            {
                "name": "Test Adventure",
                "id": "TEST",
                "source": "TEST",
                "contents": []
            }
        ],
        "adventureData": [
            {
                "id": "TEST",
                "source": "TEST",
                "data": [
                    {
                        "type": "section",
                        "name": "Chapter 1",
                        "entries": ["Hello world."]
                    }
                ]
            }
        ]
    }


@pytest.fixture
def complex_adventure():
    """A more complex adventure with nested structure."""
    return {
        "_meta": {
            "sources": [
                {"json": "COMPLEX", "abbreviation": "C", "full": "Complex Adventure"}
            ]
        },
        "adventure": [
            {
                "name": "Complex Adventure",
                "id": "COMPLEX",
                "source": "COMPLEX",
                "contents": []
            }
        ],
        "adventureData": [
            {
                "id": "COMPLEX",
                "source": "COMPLEX",
                "data": [
                    {
                        "type": "section",
                        "name": "Part 1",
                        "entries": [
                            {
                                "type": "entries",
                                "name": "Chapter 1",
                                "entries": [
                                    {"type": "inset", "name": "Sidebar", "entries": ["Info."]}
                                ]
                            }
                        ]
                    },
                    {
                        "type": "section",
                        "name": "Part 2",
                        "entries": [
                            {"type": "hr"}
                        ]
                    }
                ]
            }
        ]
    }


# ---------------------------------------------------------------------------
# Rust CLI integration tests
# ---------------------------------------------------------------------------

class TestRustCLI:
    """Tests for the Rust CLI."""

    def test_cli_simple_validate(self, simple_adventure, tmp_path):
        """Test CLI validation of simple adventure."""
        input_file = tmp_path / "input.json"
        output_file = tmp_path / "output.json"
        
        input_file.write_text(json.dumps(simple_adventure))
        
        result = subprocess.run(
            ["./target/debug/adventure_model", 
             "--input", str(input_file),
             "--output", str(output_file),
             "--validate"],
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        assert "OK" in result.stdout

    def test_cli_assigns_ids(self, simple_adventure, tmp_path):
        """Test CLI assigns sequential IDs."""
        input_file = tmp_path / "input.json"
        output_file = tmp_path / "output.json"
        
        input_file.write_text(json.dumps(simple_adventure))
        
        result = subprocess.run(
            ["./target/debug/adventure_model",
             "--input", str(input_file),
             "--output", str(output_file)],
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        
        output = json.loads(output_file.read_text())
        
        # Check IDs are assigned
        adventure_data = output.get("adventureData", [{}])[0]
        data = adventure_data.get("data", [])
        assert len(data) >= 1
        assert data[0].get("id") == "000"

    def test_cli_builds_toc(self, simple_adventure, tmp_path):
        """Test CLI builds TOC from data."""
        input_file = tmp_path / "input.json"
        output_file = tmp_path / "output.json"
        
        input_file.write_text(json.dumps(simple_adventure))
        
        result = subprocess.run(
            ["./target/debug/adventure_model",
             "--input", str(input_file),
             "--output", str(output_file)],
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        
        output = json.loads(output_file.read_text())
        
        # Check TOC is built
        adventure = output.get("adventure", [{}])[0]
        contents = adventure.get("contents", [])
        assert len(contents) >= 1
        assert contents[0].get("name") == "Chapter 1"

    def test_cli_complex_structure(self, complex_adventure, tmp_path):
        """Test CLI handles complex nested structure."""
        input_file = tmp_path / "input.json"
        output_file = tmp_path / "output.json"
        
        input_file.write_text(json.dumps(complex_adventure))
        
        result = subprocess.run(
            ["./target/debug/adventure_model",
             "--input", str(input_file),
             "--output", str(output_file)],
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        
        output = json.loads(output_file.read_text())
        
        # Verify structure
        adventure_data = output.get("adventureData", [{}])[0]
        data = adventure_data.get("data", [])
        assert len(data) == 2
        assert data[0].get("name") == "Part 1"
        assert data[1].get("name") == "Part 2"

    def test_cli_invalid_json(self, tmp_path):
        """Test CLI handles invalid JSON gracefully."""
        input_file = tmp_path / "invalid.json"
        input_file.write_text("{ invalid json }")
        
        result = subprocess.run(
            ["./target/debug/adventure_model",
             "--input", str(input_file),
             "--output", str(tmp_path / "output.json")],
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True
        )
        
        # Should exit with error code (2 for JSON parse error)
        assert result.returncode == 2


# ---------------------------------------------------------------------------
# Python integration tests
# ---------------------------------------------------------------------------

class TestPythonIntegration:
    """Tests for Python integration with Rust backend."""

    def test_python_imports_rust(self):
        """Test Python can import Rust types."""
        sys.path.insert(0, str(Path(__file__).parent / "target" / "debug"))
        
        try:
            import adventure_model_rust
            
            assert hasattr(adventure_model_rust, 'HomebrewAdventure')
            assert hasattr(adventure_model_rust, 'OfficialAdventureData')
            assert hasattr(adventure_model_rust, 'BuildContext')
            assert hasattr(adventure_model_rust, 'ValidationResult')
        except ImportError:
            pytest.skip("Rust module not available")

    def test_python_homebrew_round_trip(self, simple_adventure):
        """Test Python HomebrewAdventure round-trip."""
        sys.path.insert(0, str(Path(__file__).parent / "target" / "debug"))
        import adventure_model_rust
        
        # Create from JSON
        json_str = json.dumps(simple_adventure)
        adv = adventure_model_rust.HomebrewAdventure.from_json(json_str)
        
        # Validate
        result = adv.validate()
        assert result.errors == []
        
        # Assign IDs
        adv.assign_ids()
        
        # Build TOC
        adv.build_toc()
        
        # Round-trip
        output_json = adv.to_json()
        output = json.loads(output_json)
        
        assert "_meta" in output
        assert "adventure" in output
        assert "adventureData" in output

    def test_python_official_round_trip(self):
        """Test Python OfficialAdventureData round-trip."""
        sys.path.insert(0, str(Path(__file__).parent / "target" / "debug"))
        import adventure_model_rust
        
        raw = {
            "id": "TEST",
            "source": "TEST",
            "data": [
                {"type": "section", "name": "Test", "entries": []}
            ]
        }
        
        # Create from JSON
        json_str = json.dumps(raw)
        adv = adventure_model_rust.OfficialAdventureData.from_json(json_str)
        
        # Validate
        result = adv.validate()
        
        # Round-trip
        output_json = adv.to_json()
        output = json.loads(output_json)
        
        assert output["id"] == "TEST"
        assert output["source"] == "TEST"


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------

class TestValidation:
    """Tests for validation behavior."""

    def test_unknown_tag_error(self, tmp_path):
        """Test unknown tags are detected."""
        adventure = {
            "_meta": {"sources": [{"json": "TEST", "abbreviation": "T", "full": "Test"}]},
            "adventure": [{"name": "Test", "id": "TEST", "source": "TEST", "contents": []}],
            "adventureData": [{
                "id": "TEST",
                "source": "TEST",
                "data": [{
                    "type": "section",
                    "name": "Test",
                    "entries": ["Text with {@unknownTag} tag."]
                }]
            }]
        }
        
        input_file = tmp_path / "input.json"
        input_file.write_text(json.dumps(adventure))
        
        result = subprocess.run(
            ["./target/debug/adventure_model",
             "--input", str(input_file),
             "--output", str(tmp_path / "output.json"),
             "--validate"],
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0  # CLI doesn't fail on validation errors
        # Should detect the unknown tag
        assert "ERROR" in result.stdout or "error" in result.stdout.lower()

    def test_duplicate_id_warning(self, tmp_path):
        """Test duplicate IDs generate warnings."""
        adventure = {
            "_meta": {"sources": [{"json": "TEST", "abbreviation": "T", "full": "Test"}]},
            "adventure": [{"name": "Test", "id": "TEST", "source": "TEST", "contents": []}],
            "adventureData": [{
                "id": "TEST",
                "source": "TEST",
                "data": [
                    {"type": "section", "name": "A", "id": "DUP", "entries": []},
                    {"type": "section", "name": "B", "id": "DUP", "entries": []}
                ]
            }]
        }
        
        input_file = tmp_path / "input.json"
        input_file.write_text(json.dumps(adventure))
        
        result = subprocess.run(
            ["./target/debug/adventure_model",
             "--input", str(input_file),
             "--output", str(tmp_path / "output.json"),
             "--validate"],
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0
        # Should detect duplicate ID
        assert "WARN" in result.stdout or "warning" in result.stdout.lower()


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_adventure(self, tmp_path):
        """Test empty adventure is handled."""
        adventure = {
            "_meta": {"sources": [{"json": "TEST", "abbreviation": "T", "full": "Test"}]},
            "adventure": [{"name": "Test", "id": "TEST", "source": "TEST", "contents": []}],
            "adventureData": [{
                "id": "TEST",
                "source": "TEST",
                "data": []
            }]
        }
        
        input_file = tmp_path / "input.json"
        input_file.write_text(json.dumps(adventure))
        
        result = subprocess.run(
            ["./target/debug/adventure_model",
             "--input", str(input_file),
             "--output", str(tmp_path / "output.json")],
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0, f"CLI failed: {result.stderr}"

    def test_missing_meta(self, tmp_path):
        """Test adventure without meta is handled."""
        adventure = {
            "adventure": [{"name": "Test", "id": "TEST", "source": "TEST", "contents": []}],
            "adventureData": [{
                "id": "TEST",
                "source": "TEST",
                "data": []
            }]
        }
        
        input_file = tmp_path / "input.json"
        input_file.write_text(json.dumps(adventure))
        
        result = subprocess.run(
            ["./target/debug/adventure_model",
             "--input", str(input_file),
             "--output", str(tmp_path / "output.json")],
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True
        )
        
        # Should fail with JSON parse error (exit code 2)
        assert result.returncode == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
