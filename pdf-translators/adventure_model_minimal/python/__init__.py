"""
Python bindings for the adventure_model_minimal Rust library.
"""

try:
    from .adventure_model_minimal import parse_entry, parse_document
except ImportError:
    # Fallback for development mode or when the extension isn't built yet
    def parse_entry(json_str):
        raise ImportError("adventure_model_minimal extension not built. Run 'pip install -e .' to build the extension.")
    
    def parse_document(json_str):
        raise ImportError("adventure_model_minimal extension not built. Run 'pip install -e .' to build the extension.")

__all__ = ["parse_entry", "parse_document"]