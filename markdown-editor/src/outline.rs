//! Heading-outline model: a Markdown document as a flat list of sections, one
//! per heading, plus the tree operations the outline panel performs on them.
//!
//! Ported from pdf-translators' `frontend/src/lib/tree.ts`, with these
//! differences: `#` lines inside fenced code blocks are not headings, parsing
//! and serializing round-trip byte for byte (preamble whitespace, the spacing
//! after the hashes, CRLF and a missing final newline are all kept), and the
//! preamble's section is just the preamble rather than the whole document.

use std::collections::BTreeSet;

#[derive(Clone, Debug, PartialEq)]
pub struct Block {
    /// Index of this block when it was parsed. Operations reorder blocks, so
    /// callers use it to carry per-block UI state across a change.
    pub id: usize,
    /// Byte offset of the block in the parsed text.
    pub start: usize,
    /// 0 for the preamble before the first heading, 1..=6 for `#`..`######`.
    pub level: u8,
    /// Heading text, without the hashes, the spacing after them, or the line end.
    pub text: String,
    sep: String,
    eol: String,
    body: String,
}

pub fn parse(md: &str) -> Vec<Block> {
    let mut blocks: Vec<Block> = Vec::new();
    let mut preamble = String::new();
    let mut fence: Option<(char, usize)> = None;
    let mut offset = 0;

    for raw in md.split_inclusive('\n') {
        let start = offset;
        offset += raw.len();
        let eol_len = if raw.ends_with("\r\n") {
            2
        } else if raw.ends_with('\n') {
            1
        } else {
            0
        };
        let line = &raw[..raw.len() - eol_len];

        let heading = if fence.is_none() { parse_heading(line) } else { None };
        update_fence(&mut fence, line);

        if let Some((level, sep, text)) = heading {
            blocks.push(Block {
                id: blocks.len(),
                start,
                level,
                text: text.to_owned(),
                sep: sep.to_owned(),
                eol: raw[line.len()..].to_owned(),
                body: String::new(),
            });
        } else if let Some(current) = blocks.last_mut() {
            current.body.push_str(raw);
        } else {
            preamble.push_str(raw);
        }
    }

    if !preamble.is_empty() {
        blocks.insert(
            0,
            Block {
                id: 0,
                start: 0,
                level: 0,
                text: String::new(),
                sep: String::new(),
                eol: String::new(),
                body: preamble,
            },
        );
    }
    renumber(&mut blocks);
    blocks
}

/// `#{1,6}` followed by at least one whitespace character, as in tree.ts.
fn parse_heading(line: &str) -> Option<(u8, &str, &str)> {
    let hashes = line.len() - line.trim_start_matches('#').len();
    if !(1..=6).contains(&hashes) {
        return None;
    }
    let rest = &line[hashes..];
    let text = rest.trim_start();
    if text.len() == rest.len() {
        return None;
    }
    Some((hashes as u8, &rest[..rest.len() - text.len()], text))
}

fn update_fence(fence: &mut Option<(char, usize)>, line: &str) {
    let indent = line.len() - line.trim_start_matches(' ').len();
    if indent > 3 {
        return;
    }
    let marker = &line[indent..];
    let Some(ch) = marker.chars().next().filter(|c| *c == '`' || *c == '~') else {
        return;
    };
    let run = marker.len() - marker.trim_start_matches(ch).len();
    if run < 3 {
        return;
    }
    match *fence {
        None => *fence = Some((ch, run)),
        Some((open, len)) if open == ch && run >= len && marker[run..].trim().is_empty() => {
            *fence = None
        }
        Some(_) => {}
    }
}

pub fn serialize(blocks: &[Block]) -> String {
    let mut out = String::new();
    for block in blocks {
        // A block moved away from the end of the file may lack a final newline.
        if !out.is_empty() && !out.ends_with('\n') {
            out.push('\n');
        }
        if block.level > 0 {
            out.extend(std::iter::repeat_n('#', block.level as usize));
            out.push_str(&block.sep);
            out.push_str(&block.text);
            out.push_str(&block.eol);
        }
        out.push_str(&block.body);
    }
    out
}

pub fn renumber(blocks: &mut [Block]) {
    for (i, block) in blocks.iter_mut().enumerate() {
        block.id = i;
    }
}

/// Index of the block containing byte offset `pos`.
pub fn block_at(blocks: &[Block], pos: usize) -> Option<usize> {
    blocks.partition_point(|b| b.start <= pos).checked_sub(1)
}

/// Byte range of block `i` alone, without its subsections.
pub fn block_span(blocks: &[Block], i: usize, text_len: usize) -> std::ops::Range<usize> {
    blocks[i].start..blocks.get(i + 1).map_or(text_len, |next| next.start)
}

/// The document's reference-style link definitions (`[name]: url`), so a
/// section rendered on its own can still resolve links defined elsewhere.
pub fn link_definitions(md: &str) -> String {
    md.lines()
        .filter(|line| {
            let line = line.trim_start_matches(' ');
            line.starts_with('[')
                && !line.starts_with("[^")
                && line.find("]:").is_some_and(|end| end > 1)
        })
        .map(|line| format!("{line}\n"))
        .collect()
}

// ── Tree helpers ───────────────────────────────────────────────────────────

pub fn has_children(blocks: &[Block], i: usize) -> bool {
    blocks[i].level > 0 && blocks.get(i + 1).is_some_and(|next| next.level > blocks[i].level)
}

/// Exclusive end index of the section that starts at `i`.
pub fn section_end(blocks: &[Block], i: usize) -> usize {
    let level = blocks[i].level;
    if level == 0 {
        return i + 1;
    }
    let mut j = i + 1;
    while j < blocks.len() && blocks[j].level > level {
        j += 1;
    }
    j
}

/// Indices of the blocks not hidden inside a collapsed section.
pub fn visible_indices(blocks: &[Block], collapsed: &BTreeSet<usize>) -> Vec<usize> {
    let mut visible = Vec::new();
    let mut hidden_below: Option<u8> = None;
    for (i, block) in blocks.iter().enumerate() {
        if hidden_below.is_some_and(|level| block.level > level) {
            continue;
        }
        hidden_below = None;
        visible.push(i);
        if collapsed.contains(&i) && has_children(blocks, i) {
            hidden_below = Some(block.level);
        }
    }
    visible
}

pub fn prev_sibling(blocks: &[Block], i: usize) -> Option<usize> {
    let level = blocks[i].level;
    if level == 0 {
        return None;
    }
    let j = blocks[..i].iter().rposition(|b| b.level <= level)?;
    (blocks[j].level == level).then_some(j)
}

pub fn next_sibling(blocks: &[Block], i: usize) -> Option<usize> {
    let end = section_end(blocks, i);
    (blocks[i].level > 0 && blocks.get(end).is_some_and(|b| b.level == blocks[i].level))
        .then_some(end)
}

// ── Mutations (return whether anything changed) ────────────────────────────

/// Swap the section at `i`, subtree included, with its previous sibling.
pub fn move_up(blocks: &mut [Block], i: usize) -> bool {
    let Some(prev) = prev_sibling(blocks, i) else {
        return false;
    };
    let end = section_end(blocks, i);
    blocks[prev..end].rotate_left(i - prev);
    true
}

/// Swap the section at `i`, subtree included, with its next sibling.
pub fn move_down(blocks: &mut [Block], i: usize) -> bool {
    let Some(next) = next_sibling(blocks, i) else {
        return false;
    };
    let end = section_end(blocks, next);
    blocks[i..end].rotate_left(next - i);
    true
}

/// Add `delta` to the level of every listed heading, clamped to 1..=6.
pub fn change_level(blocks: &mut [Block], indices: &BTreeSet<usize>, delta: i8) -> bool {
    let mut changed = false;
    for &i in indices {
        let block = &mut blocks[i];
        if block.level == 0 {
            continue;
        }
        let level = (block.level as i8 + delta).clamp(1, 6) as u8;
        changed |= level != block.level;
        block.level = level;
    }
    changed
}

/// Delete every listed section with its subtree; nested selections are fine.
pub fn delete_sections(blocks: &mut Vec<Block>, indices: &BTreeSet<usize>) -> bool {
    let mut remove = vec![false; blocks.len()];
    for &i in indices {
        for flag in &mut remove[i..section_end(blocks, i)] {
            *flag = true;
        }
    }
    let mut flags = remove.iter();
    blocks.retain(|_| !flags.next().copied().unwrap_or(false));
    !indices.is_empty()
}

pub fn rename(blocks: &mut [Block], i: usize, text: &str) -> bool {
    let text = text.replace(['\r', '\n'], " ");
    let text = text.trim();
    let block = &mut blocks[i];
    if block.level == 0 || text.is_empty() || text == block.text {
        return false;
    }
    block.text = text.to_owned();
    true
}

#[cfg(test)]
mod tests {
    use super::*;

    const DOC: &str = "intro\n# A\na body\n## A1\n## A2\n# B\nb body\n";

    fn levels(blocks: &[Block]) -> Vec<(u8, &str)> {
        blocks.iter().map(|b| (b.level, b.text.as_str())).collect()
    }

    fn set(items: &[usize]) -> BTreeSet<usize> {
        items.iter().copied().collect()
    }

    #[test]
    fn parses_preamble_and_headings() {
        let blocks = parse(DOC);
        assert_eq!(
            levels(&blocks),
            [(0, ""), (1, "A"), (2, "A1"), (2, "A2"), (1, "B")]
        );
    }

    #[test]
    fn round_trips_exactly() {
        for doc in [
            DOC,
            "",
            "\n\n# Leading blank lines\n",
            "#   Extra spacing\ttab\n",
            "# Windows\r\nbody\r\n",
            "# No final newline",
            "#hashtag is not a heading\n####### neither is this\n",
            "```\n# shell comment\n```\n# Real\n",
        ] {
            assert_eq!(serialize(&parse(doc)), doc, "{doc:?}");
        }
    }

    #[test]
    fn ignores_headings_in_fenced_code() {
        let doc = "# Real\n```bash\n# comment\n~~~\n```\n~~~~\n## also code\n~~~~\n## Real 2\n";
        assert_eq!(levels(&parse(doc)), [(1, "Real"), (2, "Real 2")]);
    }

    #[test]
    fn moves_whole_sections() {
        let mut blocks = parse(DOC);
        assert!(move_up(&mut blocks, 4));
        assert_eq!(
            serialize(&blocks),
            "intro\n# B\nb body\n# A\na body\n## A1\n## A2\n"
        );
        assert!(move_down(&mut blocks, 1));
        assert_eq!(serialize(&blocks), DOC);
        assert!(!move_up(&mut blocks, 1), "no previous sibling");
        assert!(!move_up(&mut blocks, 0), "preamble never moves");
    }

    #[test]
    fn moving_the_last_section_keeps_lines_apart() {
        let mut blocks = parse("# A\n# B");
        assert!(move_up(&mut blocks, 1));
        assert_eq!(serialize(&blocks), "# B\n# A\n");
    }

    #[test]
    fn changes_levels_with_clamping() {
        let mut blocks = parse(DOC);
        assert!(change_level(&mut blocks, &set(&[0, 1, 2]), -1));
        assert_eq!(
            levels(&blocks)[..3],
            [(0, ""), (1, "A"), (1, "A1")]
        );
        assert!(!change_level(&mut blocks, &set(&[1]), -1));
    }

    #[test]
    fn deletes_nested_selections_and_only_the_preamble() {
        let mut blocks = parse(DOC);
        assert!(delete_sections(&mut blocks, &set(&[0, 1, 2])));
        assert_eq!(serialize(&blocks), "# B\nb body\n");
    }

    #[test]
    fn locates_blocks_by_offset() {
        let blocks = parse(DOC);
        assert_eq!(block_at(&blocks, 0), Some(0));
        let a1 = DOC.find("## A1").unwrap();
        assert_eq!(block_at(&blocks, a1), Some(2));
        assert_eq!(block_at(&blocks, a1 - 1), Some(1));
        assert_eq!(&DOC[block_span(&blocks, 2, DOC.len())], "## A1\n");
        assert_eq!(&DOC[block_span(&blocks, 4, DOC.len())], "# B\nb body\n");
    }

    #[test]
    fn collects_link_definitions() {
        let doc = "# A\nsee [x]\n# B\n[x]: https://example.com\n[^1]: footnote\n[]: no\n";
        assert_eq!(link_definitions(doc), "[x]: https://example.com\n");
    }

    #[test]
    fn collapsing_hides_the_subtree() {
        let blocks = parse(DOC);
        assert_eq!(visible_indices(&blocks, &set(&[1])), [0, 1, 4]);
        assert_eq!(visible_indices(&blocks, &set(&[0])), [0, 1, 2, 3, 4]);
    }

    #[test]
    fn renames_keep_the_heading_line_shape() {
        let mut blocks = parse("##  Old\r\n");
        assert!(rename(&mut blocks, 0, " New\n"));
        assert!(!rename(&mut blocks, 0, "   "));
        assert_eq!(serialize(&blocks), "##  New\r\n");
    }
}
