#!/usr/bin/env python3
"""
adventure_model.py — Typed data model for 5etools adventure JSON.

Provides dataclass-based construction with built-in validation, so structural
errors are caught during construction rather than only after serialization.

Two validation modes:
    WARN   — collect issues as warnings/errors, never raise (default)
    STRICT — raise ValidationError immediately on the first error

Usage (build from scratch):
    ctx = BuildContext()
    doc = HomebrewAdventure.build(
        name="My Adventure", source="MYADV",
        sections=[Section(name="Ch1", entries=["Hello."], ctx=ctx)],
        ctx=ctx,
    )
    print(doc.to_json())

Usage (load existing JSON):
    with open("adventure.json") as f:
        raw = json.load(f)
    ctx = BuildContext()
    doc = parse_document(raw, ctx)
    print(ctx.result.summary())
    print(doc.to_json())
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Union

from validate_adventure import VALID_ENTRY_TYPES, KNOWN_TAGS, TAG_RE


# ---------------------------------------------------------------------------
# Validation infrastructure
# ---------------------------------------------------------------------------

class ValidationMode(Enum):
    WARN = "warn"
    STRICT = "strict"


class ValidationError(Exception):
    """Raised in STRICT mode on the first error."""
    pass


class ValidationResult:
    """Collects errors (must fix) and warnings (should review)."""

    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def summary(self) -> str:
        parts = []
        if self.errors:
            parts.append(f"{len(self.errors)} error(s)")
        if self.warnings:
            parts.append(f"{len(self.warnings)} warning(s)")
        return ", ".join(parts) if parts else "OK"


@dataclass
class BuildContext:
    """Threaded through all model objects during construction."""
    mode: ValidationMode = ValidationMode.WARN
    result: ValidationResult = field(default_factory=ValidationResult)
    ids_seen: dict[str, str] = field(default_factory=dict)

    def error(self, msg: str) -> None:
        self.result.error(msg)
        if self.mode == ValidationMode.STRICT:
            raise ValidationError(msg)

    def warn(self, msg: str) -> None:
        self.result.warn(msg)

    def check_id(self, entry_id: str, path: str) -> None:
        if not isinstance(entry_id, str):
            self.error(f"{path}: id must be a string, got {type(entry_id).__name__}")
            return
        if entry_id in self.ids_seen:
            self.warn(f"{path}: duplicate id '{entry_id}' (first at {self.ids_seen[entry_id]})")
        self.ids_seen[entry_id] = path


def validate_tags(text: str, path: str, ctx: BuildContext) -> None:
    """Check {@tag} references and brace balance in a string."""
    for m in TAG_RE.finditer(text):
        tag = m.group(1)
        if tag not in KNOWN_TAGS:
            ctx.error(f"{path}: unknown tag '{{@{tag}}}' in: ...{m.group(0)}...")

    depth = 0
    for ch in text:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                ctx.warn(f"{path}: unbalanced closing brace")
                break
    if depth > 0:
        ctx.warn(f"{path}: unbalanced opening brace ({depth} unclosed)")


# ---------------------------------------------------------------------------
# Entry type: the union
# ---------------------------------------------------------------------------

# Forward reference — Entry is str | any EntryBase subclass
Entry = Union[str, "EntryBase"]


# ---------------------------------------------------------------------------
# Base entry
# ---------------------------------------------------------------------------

@dataclass
class EntryBase:
    """Base for all entry objects. Not instantiated directly."""
    type: str = ""
    name: str | None = None
    id: str | None = None
    page: int | None = None
    _ctx: BuildContext = field(default_factory=BuildContext, repr=False, compare=False)
    _path: str = field(default="", repr=False, compare=False)

    def _validate_name_tags(self) -> None:
        if self.name and isinstance(self.name, str):
            validate_tags(self.name, f"{self._path}.name", self._ctx)

    def _validate_id(self) -> None:
        if self.id is not None:
            self._ctx.check_id(self.id, self._path)

    def _base_dict(self) -> dict:
        d: dict[str, Any] = {"type": self.type}
        if self.name is not None:
            d["name"] = self.name
        if self.id is not None:
            d["id"] = self.id
        if self.page is not None:
            d["page"] = self.page
        return d

    def to_dict(self) -> dict:
        return self._base_dict()


# ---------------------------------------------------------------------------
# Container entries (have entries[])
# ---------------------------------------------------------------------------

@dataclass
class SectionEntry(EntryBase):
    entries: list[Entry] = field(default_factory=list)

    def __post_init__(self):
        self.type = "section"
        if not self.name:
            self._ctx.warn(f"{self._path}: section has no name")
        self._validate_name_tags()
        self._validate_id()
        if not isinstance(self.entries, list):
            self._ctx.error(f"{self._path}.entries must be an array")
        else:
            _validate_entry_list(self.entries, f"{self._path}.entries", self._ctx)

    def to_dict(self) -> dict:
        d = self._base_dict()
        if self.entries:
            d["entries"] = _entries_to_list(self.entries)
        return d


@dataclass
class EntriesEntry(EntryBase):
    entries: list[Entry] = field(default_factory=list)

    def __post_init__(self):
        self.type = "entries"
        if not self.name:
            self._ctx.warn(f"{self._path}: entries has no name")
        self._validate_name_tags()
        self._validate_id()
        if not isinstance(self.entries, list):
            self._ctx.error(f"{self._path}.entries must be an array")
        else:
            _validate_entry_list(self.entries, f"{self._path}.entries", self._ctx)

    def to_dict(self) -> dict:
        d = self._base_dict()
        if self.entries:
            d["entries"] = _entries_to_list(self.entries)
        return d


@dataclass
class InsetEntry(EntryBase):
    entries: list[Entry] = field(default_factory=list)

    def __post_init__(self):
        self.type = "inset"
        self._validate_name_tags()
        self._validate_id()
        if not isinstance(self.entries, list):
            self._ctx.error(f"{self._path}.entries must be an array")
        else:
            _validate_entry_list(self.entries, f"{self._path}.entries", self._ctx)

    def to_dict(self) -> dict:
        d = self._base_dict()
        if self.entries:
            d["entries"] = _entries_to_list(self.entries)
        return d


@dataclass
class InsetReadaloudEntry(EntryBase):
    entries: list[Entry] = field(default_factory=list)

    def __post_init__(self):
        self.type = "insetReadaloud"
        self._validate_name_tags()
        self._validate_id()
        if not isinstance(self.entries, list):
            self._ctx.error(f"{self._path}.entries must be an array")
        else:
            _validate_entry_list(self.entries, f"{self._path}.entries", self._ctx)

    def to_dict(self) -> dict:
        d = self._base_dict()
        if self.entries:
            d["entries"] = _entries_to_list(self.entries)
        return d


@dataclass
class QuoteEntry(EntryBase):
    entries: list[Entry] = field(default_factory=list)
    by: str | None = None
    from_: str | None = None

    def __post_init__(self):
        self.type = "quote"
        self._validate_name_tags()
        self._validate_id()
        if self.by and isinstance(self.by, str):
            validate_tags(self.by, f"{self._path}.by", self._ctx)
        if self.from_ and isinstance(self.from_, str):
            validate_tags(self.from_, f"{self._path}.from", self._ctx)
        if not isinstance(self.entries, list):
            self._ctx.error(f"{self._path}.entries must be an array")
        else:
            _validate_entry_list(self.entries, f"{self._path}.entries", self._ctx)

    def to_dict(self) -> dict:
        d = self._base_dict()
        if self.entries:
            d["entries"] = _entries_to_list(self.entries)
        if self.by is not None:
            d["by"] = self.by
        if self.from_ is not None:
            d["from"] = self.from_
        return d


@dataclass
class VariantInnerEntry(EntryBase):
    entries: list[Entry] = field(default_factory=list)

    def __post_init__(self):
        self.type = "variantInner"
        self._validate_name_tags()
        self._validate_id()
        if not isinstance(self.entries, list):
            self._ctx.error(f"{self._path}.entries must be an array")
        else:
            _validate_entry_list(self.entries, f"{self._path}.entries", self._ctx)

    def to_dict(self) -> dict:
        d = self._base_dict()
        if self.entries:
            d["entries"] = _entries_to_list(self.entries)
        return d


# ---------------------------------------------------------------------------
# List / Item entries
# ---------------------------------------------------------------------------

@dataclass
class ItemEntry(EntryBase):
    entry: str | None = None
    entries: list[Entry] | None = None

    def __post_init__(self):
        self.type = "item"
        self._validate_name_tags()
        if self.entry and isinstance(self.entry, str):
            validate_tags(self.entry, f"{self._path}.entry", self._ctx)
        if self.entries is not None:
            if not isinstance(self.entries, list):
                self._ctx.error(f"{self._path}.entries must be an array")
            else:
                _validate_entry_list(self.entries, f"{self._path}.entries", self._ctx)

    def to_dict(self) -> dict:
        d = self._base_dict()
        if self.entry is not None:
            d["entry"] = self.entry
        if self.entries is not None:
            d["entries"] = _entries_to_list(self.entries)
        return d


@dataclass
class ItemSubEntry(EntryBase):
    entry: str | None = None

    def __post_init__(self):
        self.type = "itemSub"
        self._validate_name_tags()
        if self.entry and isinstance(self.entry, str):
            validate_tags(self.entry, f"{self._path}.entry", self._ctx)

    def to_dict(self) -> dict:
        d = self._base_dict()
        if self.entry is not None:
            d["entry"] = self.entry
        return d


@dataclass
class ListEntry(EntryBase):
    items: list[Entry] = field(default_factory=list)
    style: str | None = None

    def __post_init__(self):
        self.type = "list"
        self._validate_name_tags()
        if not isinstance(self.items, list):
            self._ctx.error(f"{self._path}.items must be an array")
        else:
            _validate_entry_list(self.items, f"{self._path}.items", self._ctx)

    def to_dict(self) -> dict:
        d = self._base_dict()
        if self.style is not None:
            d["style"] = self.style
        d["items"] = _entries_to_list(self.items) if self.items else []
        return d


# ---------------------------------------------------------------------------
# Table entries
# ---------------------------------------------------------------------------

@dataclass
class TableEntry(EntryBase):
    caption: str | None = None
    colLabels: list[str] = field(default_factory=list)
    colStyles: list[str] | None = None
    rows: list[list] = field(default_factory=list)

    def __post_init__(self):
        self.type = "table"
        self._validate_name_tags()
        if self.caption and isinstance(self.caption, str):
            validate_tags(self.caption, f"{self._path}.caption", self._ctx)
        if not isinstance(self.colLabels, list):
            self._ctx.error(f"{self._path}.colLabels must be an array")
        if not isinstance(self.rows, list):
            self._ctx.error(f"{self._path}.rows must be an array")
        if isinstance(self.colLabels, list) and len(self.colLabels) == 0 and isinstance(self.rows, list) and len(self.rows) > 0:
            self._ctx.warn(f"{self._path}: table has rows but no colLabels")
        # Validate tags in cells
        if isinstance(self.rows, list):
            for ri, row in enumerate(self.rows):
                if isinstance(row, list):
                    for ci, cell in enumerate(row):
                        if isinstance(cell, str):
                            validate_tags(cell, f"{self._path}.rows[{ri}][{ci}]", self._ctx)

    def to_dict(self) -> dict:
        d = self._base_dict()
        if self.caption is not None:
            d["caption"] = self.caption
        if self.colLabels:
            d["colLabels"] = list(self.colLabels)
        if self.colStyles is not None:
            d["colStyles"] = list(self.colStyles)
        d["rows"] = [list(row) if isinstance(row, list) else row for row in self.rows]
        return d


@dataclass
class TableGroupEntry(EntryBase):
    tables: list[TableEntry] = field(default_factory=list)

    def __post_init__(self):
        self.type = "tableGroup"

    def to_dict(self) -> dict:
        d = self._base_dict()
        d["tables"] = [t.to_dict() for t in self.tables]
        return d


# ---------------------------------------------------------------------------
# Image entries
# ---------------------------------------------------------------------------

@dataclass
class ImageHref:
    type: str = "internal"
    path: str | None = None
    url: str | None = None

    def to_dict(self) -> dict:
        d: dict[str, Any] = {"type": self.type}
        if self.path is not None:
            d["path"] = self.path
        if self.url is not None:
            d["url"] = self.url
        return d

    @classmethod
    def from_dict(cls, d: dict) -> ImageHref:
        return cls(type=d.get("type", "internal"), path=d.get("path"), url=d.get("url"))


@dataclass
class ImageEntry(EntryBase):
    href: ImageHref | None = None
    title: str | None = None
    maxWidth: int | None = None
    _extra: dict = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self):
        self.type = "image"
        if self.href is None:
            self._ctx.error(f"{self._path}: image has no href")
        elif isinstance(self.href, ImageHref):
            if not self.href.path and not self.href.url:
                self._ctx.warn(f"{self._path}: image href has no path or url")

    def to_dict(self) -> dict:
        d = self._base_dict()
        if self.href is not None:
            d["href"] = self.href.to_dict()
        if self.title is not None:
            d["title"] = self.title
        if self.maxWidth is not None:
            d["maxWidth"] = self.maxWidth
        # Preserve extra fields (mapRegions, etc.)
        for k, v in self._extra.items():
            if k not in d:
                d[k] = v
        return d


@dataclass
class GalleryEntry(EntryBase):
    images: list[ImageEntry] = field(default_factory=list)

    def __post_init__(self):
        self.type = "gallery"

    def to_dict(self) -> dict:
        d = self._base_dict()
        d["images"] = [img.to_dict() for img in self.images]
        return d


# ---------------------------------------------------------------------------
# Structural / leaf entries
# ---------------------------------------------------------------------------

@dataclass
class HrEntry(EntryBase):
    def __post_init__(self):
        self.type = "hr"

    def to_dict(self) -> dict:
        return {"type": "hr"}


@dataclass
class InlineEntry(EntryBase):
    entries: list[Entry] = field(default_factory=list)

    def __post_init__(self):
        self.type = "inline"
        if isinstance(self.entries, list):
            _validate_entry_list(self.entries, f"{self._path}.entries", self._ctx)

    def to_dict(self) -> dict:
        d = self._base_dict()
        if self.entries:
            d["entries"] = _entries_to_list(self.entries)
        return d


@dataclass
class InlineBlockEntry(EntryBase):
    entries: list[Entry] = field(default_factory=list)

    def __post_init__(self):
        self.type = "inlineBlock"
        if isinstance(self.entries, list):
            _validate_entry_list(self.entries, f"{self._path}.entries", self._ctx)

    def to_dict(self) -> dict:
        d = self._base_dict()
        if self.entries:
            d["entries"] = _entries_to_list(self.entries)
        return d


@dataclass
class FlowBlockEntry(EntryBase):
    entries: list[Entry] = field(default_factory=list)

    def __post_init__(self):
        self.type = "flowBlock"
        if isinstance(self.entries, list):
            _validate_entry_list(self.entries, f"{self._path}.entries", self._ctx)

    def to_dict(self) -> dict:
        d = self._base_dict()
        if self.entries:
            d["entries"] = _entries_to_list(self.entries)
        return d


@dataclass
class FlowchartEntry(EntryBase):
    blocks: list[FlowBlockEntry] = field(default_factory=list)

    def __post_init__(self):
        self.type = "flowchart"

    def to_dict(self) -> dict:
        d = self._base_dict()
        d["blocks"] = [b.to_dict() for b in self.blocks]
        return d


@dataclass
class StatblockEntry(EntryBase):
    tag: str = ""
    source: str = ""

    def __post_init__(self):
        self.type = "statblock"

    def to_dict(self) -> dict:
        d = self._base_dict()
        d["tag"] = self.tag
        if self.name:
            d["name"] = self.name
        d["source"] = self.source
        return d


@dataclass
class SpellcastingEntry(EntryBase):
    headerEntries: list[str] = field(default_factory=list)
    _raw: dict = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self):
        self.type = "spellcasting"
        self._validate_name_tags()

    def to_dict(self) -> dict:
        # Spellcasting has many variant fields — preserve the raw dict
        d = dict(self._raw) if self._raw else self._base_dict()
        d["type"] = "spellcasting"
        if self.name:
            d["name"] = self.name
        return d


# ---------------------------------------------------------------------------
# Generic entry (escape hatch for unknown types)
# ---------------------------------------------------------------------------

@dataclass
class GenericEntry(EntryBase):
    _raw: dict = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self):
        if self.type and self.type not in VALID_ENTRY_TYPES:
            self._ctx.warn(f"{self._path}: unknown entry type '{self.type}'")
        self._validate_name_tags()
        self._validate_id()

    def to_dict(self) -> dict:
        # Pass through the raw dict
        return dict(self._raw)


# ---------------------------------------------------------------------------
# Entry helpers
# ---------------------------------------------------------------------------

def _validate_entry_list(entries: list, path: str, ctx: BuildContext) -> None:
    """Validate strings in an entry list for tags."""
    for i, entry in enumerate(entries):
        if isinstance(entry, str):
            validate_tags(entry, f"{path}[{i}]", ctx)
        elif entry is None:
            ctx.error(f"{path}[{i}]: null entry")


def _entries_to_list(entries: list[Entry]) -> list:
    """Serialize a list of Entry objects to plain dicts/strings."""
    result = []
    for e in entries:
        if isinstance(e, str):
            result.append(e)
        elif isinstance(e, EntryBase):
            result.append(e.to_dict())
        else:
            result.append(e)  # pass through raw dicts etc.
    return result


# ---------------------------------------------------------------------------
# Type dispatch map
# ---------------------------------------------------------------------------

_TYPE_MAP: dict[str, type[EntryBase]] = {
    "section": SectionEntry,
    "entries": EntriesEntry,
    "inset": InsetEntry,
    "insetReadaloud": InsetReadaloudEntry,
    "quote": QuoteEntry,
    "variantInner": VariantInnerEntry,
    "list": ListEntry,
    "item": ItemEntry,
    "itemSub": ItemSubEntry,
    "table": TableEntry,
    "tableGroup": TableGroupEntry,
    "image": ImageEntry,
    "gallery": GalleryEntry,
    "hr": HrEntry,
    "inline": InlineEntry,
    "inlineBlock": InlineBlockEntry,
    "flowchart": FlowchartEntry,
    "flowBlock": FlowBlockEntry,
    "statblock": StatblockEntry,
    "spellcasting": SpellcastingEntry,
    "statblockInline": GenericEntry,
}

# Entry types that have an entries[] child array
_CONTAINER_TYPES = {"section", "entries", "inset", "insetReadaloud", "quote",
                    "variantInner", "inline", "inlineBlock", "flowBlock"}


def parse_entry(d: Any, ctx: BuildContext, path: str = "") -> Entry:
    """Parse a raw dict/string into a typed Entry object."""
    if isinstance(d, str):
        validate_tags(d, path, ctx)
        return d

    if d is None:
        ctx.error(f"{path}: null entry")
        return GenericEntry(type="null", _raw={}, _ctx=ctx, _path=path)

    if not isinstance(d, dict):
        ctx.warn(f"{path}: unexpected entry type {type(d).__name__}")
        return GenericEntry(type="unknown", _raw={"value": d}, _ctx=ctx, _path=path)

    etype = d.get("type", "")
    cls = _TYPE_MAP.get(etype)

    if cls is None:
        if etype:
            return GenericEntry(type=etype, name=d.get("name"), id=d.get("id"),
                                page=d.get("page"), _raw=d, _ctx=ctx, _path=path)
        else:
            ctx.warn(f"{path}: entry has no 'type' field")
            return GenericEntry(type="", name=d.get("name"), id=d.get("id"),
                                _raw=d, _ctx=ctx, _path=path)

    # Build kwargs for the specific class
    kwargs: dict[str, Any] = {
        "name": d.get("name"),
        "id": d.get("id"),
        "page": d.get("page"),
        "_ctx": ctx,
        "_path": path,
    }

    # Container types: recursively parse entries[]
    if etype in _CONTAINER_TYPES:
        raw_entries = d.get("entries", [])
        if isinstance(raw_entries, list):
            kwargs["entries"] = [parse_entry(e, ctx, f"{path}.entries[{i}]")
                                 for i, e in enumerate(raw_entries)]
        else:
            kwargs["entries"] = raw_entries  # will be caught by __post_init__

    # Type-specific fields
    if etype == "quote":
        kwargs["by"] = d.get("by")
        kwargs["from_"] = d.get("from")

    elif etype == "list":
        raw_items = d.get("items", [])
        kwargs["style"] = d.get("style")
        if isinstance(raw_items, list):
            kwargs["items"] = [parse_entry(item, ctx, f"{path}.items[{i}]")
                               for i, item in enumerate(raw_items)]
        else:
            kwargs["items"] = raw_items

    elif etype == "item":
        kwargs["entry"] = d.get("entry")
        raw_entries = d.get("entries")
        if isinstance(raw_entries, list):
            kwargs["entries"] = [parse_entry(e, ctx, f"{path}.entries[{i}]")
                                 for i, e in enumerate(raw_entries)]
        else:
            kwargs["entries"] = raw_entries

    elif etype == "itemSub":
        kwargs["entry"] = d.get("entry")

    elif etype == "table":
        kwargs["caption"] = d.get("caption")
        kwargs["colLabels"] = d.get("colLabels", [])
        kwargs["colStyles"] = d.get("colStyles")
        kwargs["rows"] = d.get("rows", [])

    elif etype == "tableGroup":
        raw_tables = d.get("tables", [])
        kwargs["tables"] = [parse_entry(t, ctx, f"{path}.tables[{i}]")
                            for i, t in enumerate(raw_tables)]

    elif etype == "image":
        raw_href = d.get("href")
        kwargs["href"] = ImageHref.from_dict(raw_href) if isinstance(raw_href, dict) else None
        kwargs["title"] = d.get("title")
        kwargs["maxWidth"] = d.get("maxWidth")
        # Preserve extra fields
        extra_keys = set(d.keys()) - {"type", "name", "id", "page", "href", "title", "maxWidth"}
        kwargs["_extra"] = {k: d[k] for k in extra_keys}

    elif etype == "gallery":
        raw_images = d.get("images", [])
        kwargs["images"] = [parse_entry(img, ctx, f"{path}.images[{i}]")
                            for i, img in enumerate(raw_images)]

    elif etype == "flowchart":
        raw_blocks = d.get("blocks", [])
        kwargs["blocks"] = [parse_entry(b, ctx, f"{path}.blocks[{i}]")
                            for i, b in enumerate(raw_blocks)]

    elif etype == "statblock":
        kwargs["tag"] = d.get("tag", "")
        kwargs["source"] = d.get("source", "")

    elif etype == "spellcasting":
        kwargs["headerEntries"] = d.get("headerEntries", [])
        kwargs["_raw"] = d

    elif etype == "statblockInline":
        kwargs["_raw"] = d

    return cls(**kwargs)


# ---------------------------------------------------------------------------
# Document-level: Meta, TOC, Index
# ---------------------------------------------------------------------------

@dataclass
class MetaSource:
    json: str = ""
    abbreviation: str = ""
    full: str = ""
    version: str | None = None
    authors: list[str] = field(default_factory=list)
    convertedBy: list[str] = field(default_factory=list)
    url: str | None = None
    color: str | None = None

    def __post_init__(self):
        pass  # Validation is done by Meta

    def to_dict(self) -> dict:
        d: dict[str, Any] = {"json": self.json}
        if self.abbreviation:
            d["abbreviation"] = self.abbreviation
        if self.full:
            d["full"] = self.full
        if self.version is not None:
            d["version"] = self.version
        if self.authors:
            d["authors"] = list(self.authors)
        if self.convertedBy:
            d["convertedBy"] = list(self.convertedBy)
        if self.url is not None:
            d["url"] = self.url
        if self.color is not None:
            d["color"] = self.color
        return d

    @classmethod
    def from_dict(cls, d: dict) -> MetaSource:
        return cls(
            json=d.get("json", ""),
            abbreviation=d.get("abbreviation", ""),
            full=d.get("full", ""),
            version=d.get("version"),
            authors=d.get("authors", []),
            convertedBy=d.get("convertedBy", []),
            url=d.get("url"),
            color=d.get("color"),
        )


@dataclass
class Meta:
    sources: list[MetaSource] = field(default_factory=list)
    dateAdded: int = 0
    dateLastModified: int = 0
    _ctx: BuildContext = field(default_factory=BuildContext, repr=False, compare=False)

    def __post_init__(self):
        if not self.sources:
            self._ctx.warn("_meta.sources is empty")
        for i, src in enumerate(self.sources):
            if not src.json:
                self._ctx.error(f"_meta.sources[{i}].json is required")

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "sources": [s.to_dict() for s in self.sources],
        }
        if self.dateAdded:
            d["dateAdded"] = self.dateAdded
        if self.dateLastModified:
            d["dateLastModified"] = self.dateLastModified
        return d

    @classmethod
    def from_dict(cls, d: dict, ctx: BuildContext) -> Meta:
        sources = [MetaSource.from_dict(s) for s in d.get("sources", [])]
        return cls(
            sources=sources,
            dateAdded=d.get("dateAdded", 0),
            dateLastModified=d.get("dateLastModified", 0),
            _ctx=ctx,
        )


@dataclass
class TocHeader:
    """A header entry in a TOC item. Can be a plain string or depth object."""
    header: str = ""
    depth: int = 0

    def to_dict(self) -> str | dict:
        if self.depth > 0:
            return {"header": self.header, "depth": self.depth}
        return self.header

    @classmethod
    def from_raw(cls, raw: Any) -> TocHeader:
        if isinstance(raw, str):
            return cls(header=raw, depth=0)
        if isinstance(raw, dict):
            return cls(header=raw.get("header", ""), depth=raw.get("depth", 0))
        return cls(header=str(raw), depth=0)


@dataclass
class TocEntry:
    """One entry in adventure[0].contents[]."""
    name: str = ""
    headers: list[TocHeader] = field(default_factory=list)
    ordinal: dict | None = None

    def to_dict(self) -> dict:
        d: dict[str, Any] = {"name": self.name, "headers": [h.to_dict() for h in self.headers]}
        if self.ordinal is not None:
            d["ordinal"] = self.ordinal
        return d

    @classmethod
    def from_dict(cls, d: dict) -> TocEntry:
        headers = [TocHeader.from_raw(h) for h in d.get("headers", [])]
        return cls(name=d.get("name", ""), headers=headers, ordinal=d.get("ordinal"))


@dataclass
class AdventureIndex:
    """The adventure[0] or book[0] index object."""
    name: str = ""
    id: str = ""
    source: str = ""
    contents: list[TocEntry] = field(default_factory=list)
    group: str | None = None
    published: str | None = None
    author: str | None = None
    storyline: str | None = None
    level: dict | None = None
    coverUrl: str | None = None
    _extra: dict = field(default_factory=dict, repr=False, compare=False)

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "name": self.name,
            "id": self.id,
            "source": self.source,
            "contents": [c.to_dict() for c in self.contents],
        }
        if self.group is not None:
            d["group"] = self.group
        if self.published is not None:
            d["published"] = self.published
        if self.author is not None:
            d["author"] = self.author
        if self.storyline is not None:
            d["storyline"] = self.storyline
        if self.level is not None:
            d["level"] = self.level
        if self.coverUrl is not None:
            d["coverUrl"] = self.coverUrl
        for k, v in self._extra.items():
            if k not in d:
                d[k] = v
        return d

    @classmethod
    def from_dict(cls, d: dict) -> AdventureIndex:
        known_keys = {"name", "id", "source", "contents", "group", "published",
                       "author", "storyline", "level", "coverUrl"}
        extra = {k: v for k, v in d.items() if k not in known_keys}
        return cls(
            name=d.get("name", ""),
            id=d.get("id", ""),
            source=d.get("source", ""),
            contents=[TocEntry.from_dict(c) for c in d.get("contents", [])],
            group=d.get("group"),
            published=d.get("published"),
            author=d.get("author"),
            storyline=d.get("storyline"),
            level=d.get("level"),
            coverUrl=d.get("coverUrl"),
            _extra=extra,
        )


@dataclass
class AdventureData:
    """The adventureData[0] or bookData[0] object."""
    id: str = ""
    source: str = ""
    data: list[SectionEntry] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source": self.source,
            "data": [s.to_dict() for s in self.data],
        }


# ---------------------------------------------------------------------------
# Top-level documents
# ---------------------------------------------------------------------------

@dataclass
class HomebrewAdventure:
    """Full homebrew format: {_meta, adventure[], adventureData[]}."""
    meta: Meta = field(default_factory=Meta)
    adventure: AdventureIndex = field(default_factory=AdventureIndex)
    adventure_data: AdventureData = field(default_factory=AdventureData)
    is_book: bool = False
    _ctx: BuildContext = field(default_factory=BuildContext, repr=False, compare=False)

    def __post_init__(self):
        self._validate_alignment()

    def _validate_alignment(self) -> None:
        """Check that contents[] and data[] are aligned."""
        n_contents = len(self.adventure.contents)
        n_sections = len(self.adventure_data.data)

        if n_contents != n_sections:
            self._ctx.warn(f"contents has {n_contents} entries but data has {n_sections} sections")

        for i, (toc, section) in enumerate(zip(self.adventure.contents, self.adventure_data.data)):
            if toc.name and section.name and toc.name != section.name:
                self._ctx.warn(f"contents[{i}].name '{toc.name}' != data[{i}].name '{section.name}'")

    def assign_ids(self) -> None:
        """Assign sequential IDs to all section/entries/inset nodes."""
        counter = [0]
        for section in self.adventure_data.data:
            _assign_ids_recursive(section, counter)

    def build_toc(self) -> None:
        """Rebuild contents[] from data[] sections."""
        toc: list[TocEntry] = []
        for section in self.adventure_data.data:
            headers: list[TocHeader] = []
            for sub in section.entries:
                if isinstance(sub, (SectionEntry, EntriesEntry)) and sub.name:
                    headers.append(TocHeader(header=sub.name, depth=0))
            toc.append(TocEntry(name=section.name or "Untitled", headers=headers))
        self.adventure.contents = toc

    def to_dict(self) -> dict:
        idx_key = "book" if self.is_book else "adventure"
        data_key = "bookData" if self.is_book else "adventureData"
        return {
            "_meta": self.meta.to_dict(),
            idx_key: [self.adventure.to_dict()],
            data_key: [self.adventure_data.to_dict()],
        }

    def to_json(self, indent: str = "\t") -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False) + "\n"

    @classmethod
    def build(cls, *, name: str, source: str, sections: list[SectionEntry],
              ctx: BuildContext | None = None, is_book: bool = False,
              authors: list[str] | None = None,
              convertedBy: list[str] | None = None) -> HomebrewAdventure:
        """Convenience builder: creates a complete homebrew adventure from sections."""
        if ctx is None:
            ctx = BuildContext()

        meta = Meta(
            sources=[MetaSource(json=source, abbreviation=source, full=name,
                                authors=authors or [], convertedBy=convertedBy or [])],
            _ctx=ctx,
        )
        index = AdventureIndex(name=name, id=source, source=source, contents=[])
        data = AdventureData(id=source, source=source, data=sections)

        doc = cls(meta=meta, adventure=index, adventure_data=data,
                  is_book=is_book, _ctx=ctx)
        doc.assign_ids()
        doc.build_toc()
        return doc

    @classmethod
    def from_dict(cls, raw: dict, ctx: BuildContext) -> HomebrewAdventure:
        """Load from a parsed JSON dict."""
        is_book = "book" in raw and "bookData" in raw
        idx_key = "book" if is_book else "adventure"
        data_key = "bookData" if is_book else "adventureData"

        # Meta
        meta = Meta.from_dict(raw.get("_meta", {}), ctx)

        # Index
        idx_arr = raw.get(idx_key, [])
        if not idx_arr or not isinstance(idx_arr, list):
            ctx.error(f"{idx_key} must be a non-empty array")
            index = AdventureIndex()
        else:
            index = AdventureIndex.from_dict(idx_arr[0])

        # Data
        data_arr = raw.get(data_key, [])
        if not data_arr or not isinstance(data_arr, list):
            ctx.error(f"{data_key} must be a non-empty array")
            adv_data = AdventureData()
        else:
            raw_data_obj = data_arr[0]
            raw_entries = raw_data_obj.get("data", [])

            # Parse entries — warn on non-section top-level
            sections: list[SectionEntry] = []
            for i, entry in enumerate(raw_entries):
                parsed = parse_entry(entry, ctx, f"data[{i}]")
                if isinstance(parsed, SectionEntry):
                    sections.append(parsed)
                elif isinstance(parsed, str):
                    ctx.error(f"data[{i}] is a bare string (must be wrapped in a section)")
                elif isinstance(parsed, EntryBase):
                    ctx.error(f"data[{i}] is type '{parsed.type}', must be 'section'")
                    # Wrap in a GenericEntry that we skip, or keep as-is for lossless round-trip
                    # For now, promote to section with a warning
                    promoted = SectionEntry(
                        name=getattr(parsed, 'name', None) or f"Untitled ({parsed.type})",
                        entries=getattr(parsed, 'entries', []) if hasattr(parsed, 'entries') else [],
                        id=parsed.id, page=parsed.page, _ctx=ctx, _path=f"data[{i}]",
                    )
                    sections.append(promoted)

            adv_data = AdventureData(
                id=raw_data_obj.get("id", ""),
                source=raw_data_obj.get("source", ""),
                data=sections,
            )

        return cls(meta=meta, adventure=index, adventure_data=adv_data,
                   is_book=is_book, _ctx=ctx)


@dataclass
class OfficialAdventureData:
    """Official format: {"data": [...]}."""
    data: list[SectionEntry] = field(default_factory=list)
    _ctx: BuildContext = field(default_factory=BuildContext, repr=False, compare=False)

    def __post_init__(self):
        # Official format is more lenient — non-section top-level entries are warnings
        pass

    def assign_ids(self) -> None:
        counter = [0]
        for section in self.data:
            _assign_ids_recursive(section, counter)

    def to_dict(self) -> dict:
        return {"data": [s.to_dict() for s in self.data]}

    def to_json(self, indent: str = "\t") -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False) + "\n"

    @classmethod
    def from_dict(cls, raw: dict, ctx: BuildContext) -> OfficialAdventureData:
        """Load from a parsed JSON dict."""
        raw_entries = raw.get("data", [])
        if not isinstance(raw_entries, list):
            ctx.error("data must be an array")
            return cls(data=[], _ctx=ctx)

        if len(raw_entries) == 0:
            ctx.warn("data is empty")

        sections: list[SectionEntry] = []
        for i, entry in enumerate(raw_entries):
            parsed = parse_entry(entry, ctx, f"data[{i}]")
            if isinstance(parsed, SectionEntry):
                sections.append(parsed)
            elif isinstance(parsed, str):
                ctx.warn(f"data[{i}] is a bare string (must be wrapped in a section)")
            elif isinstance(parsed, EntryBase):
                ctx.warn(f"data[{i}] is type '{parsed.type}', expected 'section'")

        return cls(data=sections, _ctx=ctx)


# ---------------------------------------------------------------------------
# Top-level dispatcher
# ---------------------------------------------------------------------------

def parse_document(raw: dict, ctx: BuildContext | None = None) -> HomebrewAdventure | OfficialAdventureData:
    """Parse a raw JSON dict into the appropriate document type."""
    if ctx is None:
        ctx = BuildContext()

    if not isinstance(raw, dict):
        ctx.error("Top level must be a JSON object")
        return OfficialAdventureData(data=[], _ctx=ctx)

    if "adventure" in raw and "adventureData" in raw:
        return HomebrewAdventure.from_dict(raw, ctx)
    elif "book" in raw and "bookData" in raw:
        return HomebrewAdventure.from_dict(raw, ctx)
    elif "data" in raw:
        return OfficialAdventureData.from_dict(raw, ctx)
    else:
        ctx.error("Unrecognised top-level structure")
        return OfficialAdventureData(data=[], _ctx=ctx)


# ---------------------------------------------------------------------------
# ID assignment helper
# ---------------------------------------------------------------------------

def _assign_ids_recursive(entry: EntryBase, counter: list[int]) -> None:
    """Assign sequential IDs to section/entries/inset nodes."""
    if entry.type in ("section", "entries", "inset"):
        entry.id = f"{counter[0]:03d}"
        counter[0] += 1

    # Recurse into entries[]
    if hasattr(entry, "entries") and isinstance(entry.entries, list):
        for child in entry.entries:
            if isinstance(child, EntryBase):
                _assign_ids_recursive(child, counter)

    # Recurse into items[]
    if hasattr(entry, "items") and isinstance(entry.items, list):
        for child in entry.items:
            if isinstance(child, EntryBase):
                _assign_ids_recursive(child, counter)
