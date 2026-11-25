"""Differential contract for the optional, memory-gated Rust experiment."""
import importlib
import os
from pathlib import Path
import random
import sys

import pytest

from converters import pdf_to_5etools_v2 as converter

MODULE = "fa_converters_pdf_to_5etools_v2_py_parse_markdown_headings"


@pytest.fixture(scope="module")
def native():
    directory = os.environ.get("PDF_HEADING_NATIVE_DIR")
    if not directory:
        pytest.skip("optional native experiment; set PDF_HEADING_NATIVE_DIR to test")
    sys.path.insert(0, str(Path(directory).resolve()))
    return importlib.import_module(MODULE).parse_markdown_headings


def test_explicit_heading_class_avoids_main_module_name_collision(native, monkeypatch):
    monkeypatch.setattr(sys.modules["__main__"], "MdHeading", object, raising=False)
    headings, lines = native("# Dragon", heading_type=converter.MdHeading)
    assert headings == [converter.MdHeading(1, "Dragon", 0)]
    assert lines == ["# Dragon"]


@pytest.mark.parametrize("text", [
    "", "plain text", "\n", "# title\n", "# **bold** ***title***\nprose",
    "#\n##\t\n###   \n#  *  \n#  a  b  \n# a ###  ",
    " # indented\n#no space\n" + "#" * 100 + " title",
    "# é 🐉 漢字\n##\u00a0**café**\u2003\n# \ud800 title\n",
    "# a\r\n## b\r### c\v# d\f# e\x1c# f\x1d# g\x1e# h\x85# i\u2028# j\u2029",
    "#\x1f**control**\x1f\n#\u200bnot-whitespace\n# x\x00y",
])
def test_native_matches_python(native, text):
    expected = converter._python_parse_markdown_headings(text)
    actual = native(text)
    assert actual == expected
    assert all(type(h) is converter.MdHeading for h in actual[0])
    if actual[0]:
        actual[0][0].title = "still mutable"
        assert actual[0][0].title == "still mutable"


def test_unicode_whitespace_and_random_lines(native):
    whitespace = "\t\n\v\f\r\x1c\x1d\x1e\x1f \x85\xa0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000"
    rng = random.Random(42)
    alphabet = "# *abé漢🐉\x00\udfff" + whitespace
    text = "\n".join("#" * rng.randrange(6) + "".join(rng.choices(alphabet, k=60)) for _ in range(500))
    assert native(text) == converter._python_parse_markdown_headings(text)
    for char in whitespace:
        text = f"###{char}**title**{char}"
        assert native(text) == converter._python_parse_markdown_headings(text)


@pytest.mark.parametrize("value", [None, 3, 1.5, [], {}])
def test_invalid_input_errors_match(native, value):
    with pytest.raises(Exception) as expected:
        converter._python_parse_markdown_headings(value)
    with pytest.raises(type(expected.value)):
        native(value)
