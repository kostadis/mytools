"""Load the optional Rust heading parser once, retaining Python on load failure."""
from functools import partial
import importlib.util
import os
from pathlib import Path

MODULE = "fa_converters_pdf_to_5etools_v2_py_parse_markdown_headings"
LIBRARY = (Path(__file__).resolve().parents[1] / "native-heading-parser"
           / "target" / "python" / f"{MODULE}.abi3.so")


def _load_extension():
    if not LIBRARY.is_file():
        return None
    spec = importlib.util.spec_from_file_location(MODULE, LIBRARY)
    if spec is None or spec.loader is None:
        return None
    extension = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(extension)
    return extension


def load_parser(heading_type):
    if os.environ.get("FAST_ANYTHING_DISABLE"):
        return None
    try:
        extension = _load_extension()
    except (ImportError, OSError):
        return None
    if extension is None:
        return None
    return partial(extension.parse_markdown_headings, heading_type=heading_type)
