"""Tests for converters/layout_table_merge.py — synthetic pdftotext -layout pages only
(no book text: this repo is public)."""
from collections import Counter

import pytest

from converters.layout_table_merge import (
    apply_patches, body_lines, build_index_page, build_option_page, find_gutter,
    join_lines, parse_column, render_entry, words,
)

L, R = 0, 46  # left / right column start


def page(rows):
    """rows: list of (left_text, right_text) -> pdftotext-style lines."""
    return [(l.ljust(R) + r).rstrip() for l, r in rows]


OPTION_PAGE = page([
    ("        Alpha", "        Gamma"),
    ("  A short blurb for alpha.", "  A blurb for gamma."),
    ("", ""),
    ("  1     First. Text one goes", "  1     Sun. Bright and"),
    ("        on here.", "        warm."),
    ("", "  2     Moon. Pale."),
    ("  2     Second. Text two.", ""),
    ("        Beta", "  3     Star. Far."),
    ("  Beta blurb.", "        Delta"),            # heading at the entry-text column
    ("", "        Epsilon"),                        # two-line heading, part 2
    ("  1     Third. Spans a", "  Delta blurb."),
    ("", "  1     Rain. Wet."),                     # blank line inside an entry
    ("        long line.", ""),
])


def test_find_gutter_splits_columns():
    g = find_gutter(OPTION_PAGE)
    assert g is not None and 28 <= g <= R


def test_option_page_structure():
    subs, md = build_option_page(OPTION_PAGE)
    assert [s["title"] for s in subs] == ["Alpha", "Beta", "Gamma", "Delta Epsilon"]
    assert [[e[0] for e in s["entries"]] for s in subs] == [[1, 2], [1], [1, 2, 3], [1]]
    beta = subs[1]
    assert join_lines(beta["entries"][0][1]) == "Third. Spans a long line."  # blank line didn't end it
    assert "| 1 | **Third.** Spans a long line. |" in md
    assert "| d3 | Option |" in md  # die size = largest table


def test_heading_aligned_with_entry_text_is_not_a_continuation():
    lines = ["        Alpha", "  1     Foo. Done.", "        Beta", "  Blurb.", "  1     Bar. Ok."]
    subs = parse_column(lines)
    assert [s["title"] for s in subs] == ["Alpha", "Beta"]
    assert subs[0]["entries"][0][1] == ["Foo. Done."]


def test_unfinished_sentence_keeps_short_line_as_continuation():
    lines = ["  Alpha", "  1     Foo. Ends with", "        a dog", "  2     Bar. Ok."]
    subs = parse_column(lines)
    assert join_lines(subs[0]["entries"][0][1]) == "Foo. Ends with a dog"


def test_index_page():
    lines = ["d6        Kind       Page", " 1        Alpha       6", " 2     Beta Gamma     7"]
    die, col, rows, md = build_index_page(lines)
    assert (die, col) == (6, "Kind")
    assert rows == [(1, "Alpha", 6), (2, "Beta Gamma", 7)]
    assert "| d6 | Kind | Page |" in md and "| 2 | Beta Gamma | 7 |" in md


def test_join_lines_hyphen_and_render_pipe():
    assert join_lines(["city-", "states and", "more"]) == "city-states and more"
    assert render_entry("Name. a | b") == "**Name.** a \\| b"
    assert render_entry("no period here") == "no period here"


def test_apply_patches():
    md = "## Contents\n\n<table><tr><td>x</td></tr></table>\n\nJunk\n\nkeep"
    out = apply_patches(1, md, {"replace_first_table": "## Contents\n\n| a |",
                                "replace": [["Junk\n\n", ""]]})
    assert out == "## Contents\n\n| a |\n\nkeep"
    with pytest.raises(ValueError):
        apply_patches(1, "a a", {"replace": [["a", "b"]]})  # must match exactly once


def test_known_titles_ignores_ragged_indent_and_wrapped_clause_headings():
    lines = [
        "    but the hero is",          # a heading wrapped over three lines
        "  protected by a",
        "      power.",
        " Some blurb.",
        "  1     Sun. Bright and",
        "            warm, ragged",       # continuation NOT aligned with the entry text
        "     indent.",
        "  2     Moon. Pale.",
        "        Mayhem",                 # known heading, no period
        "  1     Rain. A line that ends",
        "        mayhem.",                # body word equal to a heading: period must agree
    ]
    subs = parse_column(lines, known_titles=["but the hero is protected by a power.", "Mayhem"])
    assert [s["title"] for s in subs] == ["but the hero is protected by a power.", "Mayhem"]
    assert join_lines(subs[0]["entries"][0][1]) == "Sun. Bright and warm, ragged indent."
    assert join_lines(subs[1]["entries"][0][1]) == "Rain. A line that ends mayhem."


def test_known_titles_matches_ellipsis_variants():
    subs = parse_column(["   A leader…", "  1     Mayor. Runs a town."], known_titles=["A leader..."])
    assert [s["title"] for s in subs] == ["A leader…"]


def test_index_row_wrapped_onto_next_line():
    lines = ["d12      Development      Page",
             " 1    but the hero is protected by a    22",
             "              higher power.",
             " 2    but it rains.                     22"]
    _, _, rows, _ = build_index_page(lines)
    assert rows == [(1, "but the hero is protected by a higher power.", 22), (2, "but it rains.", 22)]


def test_body_lines_drops_footer_and_purchase_watermark():
    text = "real text\n      -5-\nsomeone (Order #12345)\nmore\f"
    assert body_lines(text) == ["real text", "more"]


def test_words_ignores_markup():
    assert words("**Foo.** <td>bar</td> Heroes &amp; x") == Counter(
        {"Foo": 1, "bar": 1, "Heroes": 1, "x": 1})
