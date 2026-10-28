//! Splits a preview section's Markdown into the runs the preview draws
//! differently: prose that wraps to the pane, and top-level tables and code
//! blocks that keep their lines whole and scroll sideways on their own. Pure
//! core logic with no egui dependency; the source text is never changed.

use pulldown_cmark::{Event, Options, Parser, Tag};
use std::ops::Range;

/// One drawable run of a section body. The ranges of a body's chunks are in
/// order and together cover the body exactly.
#[derive(Clone, Debug, PartialEq)]
pub enum PreviewChunk {
    /// Everything that is not a top-level table or code block, including the
    /// blank lines between blocks and any table or code nested in a list or
    /// block quote.
    Prose(Range<usize>),
    /// One top-level table.
    Table(Range<usize>),
    /// One top-level fenced or indented code block: its full source range and
    /// its literal content without fences or indentation.
    Code {
        range: Range<usize>,
        content: String,
    },
}

impl PreviewChunk {
    pub fn range(&self) -> &Range<usize> {
        match self {
            PreviewChunk::Prose(range) | PreviewChunk::Table(range) => range,
            PreviewChunk::Code { range, .. } => range,
        }
    }
}

/// The extensions egui_commonmark 0.25 turns on in its `parser_options()`, so
/// what counts as a table or code block here is exactly what the preview's
/// renderer would draw as one.
const OPTIONS: Options = Options::ENABLE_TABLES
    .union(Options::ENABLE_TASKLISTS)
    .union(Options::ENABLE_STRIKETHROUGH)
    .union(Options::ENABLE_FOOTNOTES)
    .union(Options::ENABLE_DEFINITION_LIST);

/// Splits `body` into prose, top-level table and top-level code chunks. Code
/// and tables nested in a list, block quote or footnote stay in the prose.
pub fn split(body: &str) -> Vec<PreviewChunk> {
    let mut chunks = Vec::new();
    let mut prose_start = 0;
    let mut depth = 0usize;
    let mut code: Option<(Range<usize>, String)> = None;
    for (event, range) in Parser::new_ext(body, OPTIONS).into_offset_iter() {
        match event {
            Event::Start(tag) => {
                if depth == 0 {
                    match tag {
                        Tag::CodeBlock(_) => {
                            push_prose(&mut chunks, prose_start..range.start);
                            code = Some((range, String::new()));
                        }
                        Tag::Table(_) => {
                            push_prose(&mut chunks, prose_start..range.start);
                            prose_start = range.end;
                            chunks.push(PreviewChunk::Table(range));
                        }
                        _ => {}
                    }
                }
                depth += 1;
            }
            Event::End(_) => {
                depth = depth.saturating_sub(1);
                if depth == 0
                    && let Some((range, content)) = code.take()
                {
                    prose_start = range.end;
                    chunks.push(PreviewChunk::Code { range, content });
                }
            }
            Event::Text(text) => {
                if let Some((_, content)) = code.as_mut() {
                    content.push_str(&text);
                }
            }
            _ => {}
        }
    }
    push_prose(&mut chunks, prose_start..body.len());
    chunks
}

/// Adds `range` as prose, merged into a prose chunk just before it. Empty
/// ranges add nothing, so a body that starts or ends with code has no empty
/// prose chunk.
fn push_prose(chunks: &mut Vec<PreviewChunk>, range: Range<usize>) {
    if range.is_empty() {
        return;
    }
    if let Some(PreviewChunk::Prose(last)) = chunks.last_mut() {
        last.end = range.end;
    } else {
        chunks.push(PreviewChunk::Prose(range));
    }
}

/// `source` followed by the link reference definitions from `links` (one
/// `[label]: url` per line) whose label `source` mentions as `[label]`, so a
/// chunk drawn on its own resolves its reference links without the renderer
/// re-parsing every definition in the document for every chunk. Labels match
/// as CommonMark matches them: case-insensitively, with runs of whitespace
/// treated as one space.
pub fn with_used_links(source: &str, links: &str) -> String {
    let mut out = source.to_owned();
    if links.is_empty() || !source.contains('[') {
        return out;
    }
    let haystack = normalize_label(source);
    let mut first = true;
    for line in links.lines() {
        let Some(label) = line
            .trim_start()
            .strip_prefix('[')
            .and_then(|rest| rest.split_once("]:"))
            .map(|(label, _)| label)
        else {
            continue;
        };
        if haystack.contains(&format!("[{}]", normalize_label(label))) {
            if first {
                out.push_str("\n\n");
                first = false;
            }
            out.push_str(line);
            out.push('\n');
        }
    }
    out
}

fn normalize_label(text: &str) -> String {
    text.split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .to_lowercase()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_the_link_definitions_a_chunk_uses_are_appended() {
        let links = "[act]: https://a.example\n[Other]: https://o.example\n[two words]: https://t.example\n";
        assert_eq!(with_used_links("plain text", links), "plain text");
        assert_eq!(
            with_used_links("see [the Act][act]", links),
            "see [the Act][act]\n\n[act]: https://a.example\n"
        );
        assert_eq!(
            with_used_links("[other][] and [Two\n  Words]", links),
            "[other][] and [Two\n  Words]\n\n[Other]: https://o.example\n[two words]: https://t.example\n"
        );
        assert_eq!(with_used_links("[act]", ""), "[act]");
    }

    fn kinds(body: &str) -> Vec<String> {
        split(body)
            .iter()
            .map(|chunk| match chunk {
                PreviewChunk::Prose(r) => format!("prose:{}", &body[r.clone()]),
                PreviewChunk::Table(r) => format!("table:{}", &body[r.clone()]),
                PreviewChunk::Code { content, .. } => format!("code:{content}"),
            })
            .collect()
    }

    /// The chunks tile the body: in order, no gaps, no overlap.
    fn assert_tiles(body: &str) {
        let chunks = split(body);
        let mut at = 0;
        for chunk in &chunks {
            assert_eq!(
                chunk.range().start,
                at,
                "gap or overlap in {body:?}: {chunks:?}"
            );
            at = chunk.range().end;
        }
        assert_eq!(at, body.len(), "chunks of {body:?} stop short: {chunks:?}");
        let prose_pairs = chunks.windows(2).filter(|w| {
            matches!(w[0], PreviewChunk::Prose(_)) && matches!(w[1], PreviewChunk::Prose(_))
        });
        assert_eq!(
            prose_pairs.count(),
            0,
            "two prose chunks in a row: {chunks:?}"
        );
    }

    #[test]
    fn a_paragraph_is_one_prose_chunk() {
        let body = "Some text that\nwraps over lines.\n";
        assert_eq!(split(body), vec![PreviewChunk::Prose(0..body.len())]);
    }

    #[test]
    fn a_fenced_block_splits_the_prose_around_it() {
        let body = "Before.\n\n```\nlet x = 1;\n  indented  \n```\n\nAfter.\n";
        let got = kinds(body);
        assert_eq!(got.len(), 3, "{got:?}");
        assert!(got[0].starts_with("prose:Before."), "{got:?}");
        assert_eq!(got[1], "code:let x = 1;\n  indented  \n");
        assert!(
            got[2].starts_with("prose:") && got[2].contains("After."),
            "{got:?}"
        );
        assert_tiles(body);
    }

    #[test]
    fn a_top_level_table_is_its_own_chunk() {
        let table = "| a | b |\n|---|---|\n| 1 | 2 |\n";
        let body = format!("Intro.\n\n{table}\nOutro.\n");
        let chunks = split(&body);
        let tables: Vec<&str> = chunks
            .iter()
            .filter_map(|c| match c {
                PreviewChunk::Table(r) => Some(&body[r.clone()]),
                _ => None,
            })
            .collect();
        assert_eq!(tables.len(), 1, "{chunks:?}");
        assert_eq!(tables[0].trim_end(), table.trim_end());
        assert_tiles(&body);
    }

    #[test]
    fn an_indented_code_block_is_code() {
        let body = "Para.\n\n    indented code\n    more\n\nPara.\n";
        let got = kinds(body);
        assert!(
            got.contains(&"code:indented code\nmore\n".to_owned()),
            "{got:?}"
        );
        assert_tiles(body);
    }

    #[test]
    fn code_and_tables_inside_lists_and_quotes_stay_in_prose() {
        for body in [
            "- item\n\n  ```\n  code\n  ```\n",
            "> quote\n>\n> ```\n> code\n> ```\n",
            "- item\n\n  | a | b |\n  |---|---|\n  | 1 | 2 |\n",
            "> | a | b |\n> |---|---|\n> | 1 | 2 |\n",
        ] {
            assert_eq!(
                split(body),
                vec![PreviewChunk::Prose(0..body.len())],
                "{body:?}"
            );
        }
    }

    #[test]
    fn consecutive_paragraphs_merge_into_one_prose_chunk() {
        let body = "One.\n\n\nTwo.\n\n# Not a heading here\n\n- list\n";
        assert_eq!(split(body), vec![PreviewChunk::Prose(0..body.len())]);
    }

    #[test]
    fn tilde_fences_and_info_strings_are_code_without_the_info() {
        // The trailing newline after a closing fence is a blank prose chunk,
        // which the preview skips.
        let code = |body| -> Vec<String> {
            kinds(body)
                .into_iter()
                .filter(|k| !k.starts_with("prose:") || !k[6..].trim().is_empty())
                .collect()
        };
        assert_eq!(code("~~~\ntilde\n~~~\n"), vec!["code:tilde\n".to_owned()]);
        assert_eq!(
            code("```rust\nfn main() {}\n```\n"),
            vec!["code:fn main() {}\n".to_owned()]
        );
    }

    #[test]
    fn mixed_bodies_tile_exactly() {
        for body in [
            "",
            "\n\n",
            "text",
            "```\nunclosed fence\nstill code",
            "|",
            "| a |\n",
            "| a | b |\r\n|---|---|\r\n| 1 | 2 |\r\n\r\nafter\r\n",
            "```\r\ncrlf\r\n```\r\n",
            "Ünïcödé ✓ text\n\n```\n— ✓ ü\n```\nü after\n\n| ü | ✓ |\n|---|---|\n| — | é |\nü",
            "Para\n```\nno blank line before fence\n```\nPara\n",
            "    code first\n\ntext\n\n    code last",
            "[^1]: footnote\n\n    ```\n    in footnote\n    ```\n",
        ] {
            assert_tiles(body);
        }
    }

    #[test]
    fn an_unclosed_fence_runs_to_the_end_as_code() {
        let body = "Before.\n\n```\nunclosed\nstill code";
        let got = kinds(body);
        assert_eq!(
            got.last().map(String::as_str),
            Some("code:unclosed\nstill code")
        );
        assert_tiles(body);
    }
}
