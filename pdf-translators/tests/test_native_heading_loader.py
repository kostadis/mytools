"""Optional native acceleration never makes Rust mandatory for conversion."""
import importlib
import os
from pathlib import Path
import sys
import subprocess

import pytest

from converters import pdf_to_5etools_v2 as converter
from lib import native_heading_parser as loader


def test_missing_extension_uses_python(tmp_path, monkeypatch):
    monkeypatch.setattr(loader, "LIBRARY", tmp_path / "missing.so")
    assert loader.load_parser(converter.MdHeading) is None


def test_disabled_extension_is_not_loaded(monkeypatch):
    monkeypatch.setenv("FAST_ANYTHING_DISABLE", "1")
    monkeypatch.setattr(loader, "_load_extension", lambda: pytest.fail("must not load"))
    assert loader.load_parser(converter.MdHeading) is None


@pytest.mark.parametrize("error", [ImportError("incompatible ABI"), OSError("missing dependency")])
def test_unavailable_binary_uses_python(monkeypatch, error):
    monkeypatch.delenv("FAST_ANYTHING_DISABLE", raising=False)
    def fail():
        raise error
    monkeypatch.setattr(loader, "_load_extension", fail)
    assert loader.load_parser(converter.MdHeading) is None


def test_parser_errors_are_not_hidden(monkeypatch):
    monkeypatch.delenv("FAST_ANYTHING_DISABLE", raising=False)
    class Extension:
        @staticmethod
        def parse_markdown_headings(text, *, heading_type):
            raise ValueError("parse failure")
    monkeypatch.setattr(loader, "_load_extension", lambda: Extension)
    parser = loader.load_parser(converter.MdHeading)
    with pytest.raises(ValueError, match="parse failure"):
        parser("# text")


def test_loaded_native_uses_callers_heading_class(monkeypatch):
    directory = os.environ.get("PDF_HEADING_NATIVE_DIR")
    if not directory:
        pytest.skip("optional native experiment")
    monkeypatch.delenv("FAST_ANYTHING_DISABLE", raising=False)
    sys.path.insert(0, str(Path(directory).resolve()))
    extension = importlib.import_module(loader.MODULE)
    monkeypatch.setattr(loader, "_load_extension", lambda: extension)
    monkeypatch.setattr(sys.modules["__main__"], "MdHeading", object, raising=False)
    parser = loader.load_parser(converter.MdHeading)
    assert parser("# **Dragon**")[0] == [converter.MdHeading(1, "Dragon", 0)]


@pytest.mark.parametrize("disabled", [False, True])
def test_converter_selects_native_or_python_at_startup(disabled):
    if not loader.LIBRARY.is_file():
        pytest.skip("build the durable extension to test startup selection")
    project = Path(__file__).resolve().parents[1]
    code = """
from functools import partial
from converters import pdf_to_5etools_v2 as c
assert isinstance(c.parse_markdown_headings, partial) == EXPECT_NATIVE
assert c.parse_markdown_headings('# **Dragon**')[0] == [c.MdHeading(1, 'Dragon', 0)]
""".replace("EXPECT_NATIVE", repr(not disabled))
    env = dict(os.environ, PYTHONPATH=str(project))
    env.pop("FAST_ANYTHING_DISABLE", None)
    if disabled:
        env["FAST_ANYTHING_DISABLE"] = "1"
    subprocess.run([sys.executable, "-c", code], env=env, check=True, capture_output=True)
