//! Rewrites raw HTML `<table>` blocks as GitHub-style pipe tables for the
//! preview. egui_commonmark draws no HTML, so such tables would otherwise
//! show as loose text. The source text itself is never changed.

use crate::outline::update_fence;
use std::borrow::Cow;

/// Replaces every HTML table that starts a line outside fenced code with a
/// pipe table. A table with no closing `</table>` is left as written.
pub fn tables_to_markdown(md: &str) -> Cow<'_, str> {
    if !md.to_ascii_lowercase().contains("<table") {
        return Cow::Borrowed(md);
    }
    let lines: Vec<&str> = md.split_inclusive('\n').collect();
    let mut out = String::with_capacity(md.len());
    let mut fence = None;
    let mut i = 0;
    while i < lines.len() {
        let line = lines[i];
        if fence.is_none() && starts_with_tag(line.trim_start(), "table") {
            let mut html = String::new();
            let close = lines[i..].iter().position(|l| {
                html.push_str(l);
                l.to_ascii_lowercase().contains("</table>")
            });
            if let Some(n) = close {
                let end = html.to_ascii_lowercase().rfind("</table>").unwrap() + "</table>".len();
                // Blank lines around the table so it neither joins a paragraph
                // nor absorbs the text after `</table>` as another row.
                out.push('\n');
                out.push_str(&pipe_table(&parse_rows(&html[..end])));
                out.push('\n');
                let after = html[end..].trim_start();
                if !after.is_empty() {
                    out.push_str(after);
                    if !after.ends_with('\n') {
                        out.push('\n');
                    }
                }
                i += n + 1;
                continue;
            }
        }
        update_fence(&mut fence, line);
        out.push_str(line);
        i += 1;
    }
    Cow::Owned(out)
}

/// A cell's text and the number of columns it spans.
type Cell = (String, usize);

fn parse_rows(html: &str) -> Vec<Vec<Cell>> {
    let mut rows: Vec<Vec<Cell>> = Vec::new();
    let mut cell: Option<Cell> = None;
    let mut rest = html;
    while let Some(lt) = rest.find('<') {
        if let Some((text, _)) = cell.as_mut() {
            text.push_str(&rest[..lt]);
        }
        let Some(gt) = rest[lt..].find('>') else {
            break;
        };
        let tag = &rest[lt + 1..lt + gt];
        rest = &rest[lt + gt + 1..];
        let closing = tag.starts_with('/');
        let name: String = tag
            .trim_start_matches('/')
            .chars()
            .take_while(|c| c.is_ascii_alphanumeric())
            .collect::<String>()
            .to_ascii_lowercase();
        match (name.as_str(), closing) {
            ("tr", false) => {
                finish_cell(&mut rows, &mut cell);
                rows.push(Vec::new());
            }
            ("td" | "th", false) => {
                finish_cell(&mut rows, &mut cell);
                cell = Some((String::new(), colspan(tag)));
            }
            ("td" | "th" | "tr", true) => finish_cell(&mut rows, &mut cell),
            ("br" | "p", _) => {
                if let Some((text, _)) = cell.as_mut() {
                    text.push(' ');
                }
            }
            _ => {}
        }
    }
    finish_cell(&mut rows, &mut cell);
    rows
}

fn finish_cell(rows: &mut Vec<Vec<Cell>>, cell: &mut Option<Cell>) {
    if let Some((text, span)) = cell.take() {
        if rows.is_empty() {
            rows.push(Vec::new());
        }
        rows.last_mut().unwrap().push((cell_text(&text), span));
    }
}

fn colspan(tag: &str) -> usize {
    let lower = tag.to_ascii_lowercase();
    let Some(at) = lower.find("colspan") else {
        return 1;
    };
    let value = lower[at + "colspan".len()..]
        .trim_start()
        .trim_start_matches('=')
        .trim_start()
        .trim_start_matches(['"', '\'']);
    let digits: String = value.chars().take_while(char::is_ascii_digit).collect();
    digits.parse().unwrap_or(1).clamp(1, 64)
}

/// Decodes the common entities, collapses whitespace and escapes what would
/// otherwise be read as Markdown or as a column break.
fn cell_text(raw: &str) -> String {
    let decoded = raw
        .replace("&nbsp;", " ")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", "\"")
        .replace("&#39;", "'")
        .replace("&amp;", "&");
    let mut out = String::new();
    for word in decoded.split_whitespace() {
        if !out.is_empty() {
            out.push(' ');
        }
        for c in word.chars() {
            if matches!(c, '\\' | '|' | '*' | '_' | '`' | '[' | ']' | '<') {
                out.push('\\');
            }
            out.push(c);
        }
    }
    out
}

/// A column-spanning cell keeps its text in its first column and leaves the
/// rest blank, since pipe tables cannot merge cells.
fn pipe_table(rows: &[Vec<Cell>]) -> String {
    let width = rows
        .iter()
        .map(|row| row.iter().map(|(_, span)| span).sum::<usize>())
        .max()
        .unwrap_or(0)
        .max(1);
    let line = |row: &[Cell]| {
        let mut cells: Vec<&str> = Vec::new();
        for (text, span) in row {
            cells.push(text);
            cells.extend(std::iter::repeat_n("", span - 1));
        }
        cells.resize(width, "");
        format!("| {} |\n", cells.join(" | "))
    };
    let mut out = String::new();
    let (head, body) = rows
        .split_first()
        .map_or((&[][..], &[][..]), |(h, b)| (&h[..], b));
    out.push_str(&line(head));
    out.push_str(&format!("|{}\n", " --- |".repeat(width)));
    for row in body {
        out.push_str(&line(row));
    }
    out
}

fn starts_with_tag(s: &str, name: &str) -> bool {
    s.len() > name.len()
        && s.as_bytes()[0] == b'<'
        && s[1..].to_ascii_lowercase().starts_with(name)
        && s[1 + name.len()..]
            .chars()
            .next()
            .is_some_and(|c| c == '>' || c.is_whitespace() || c == '/')
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn converts_a_table_with_spans() {
        let md = "Before\n<table>\n<tr><th>A</th><th>B</th><th>C</th></tr>\n\
                  <tr><td colspan=\"2\">1 Yes</td><td>x</td></tr>\n\
                  <tr><td>6 Oppose </td><td colspan=\"2\">secret/mystic</td></tr>\n\
                  </table>\nAfter\n";
        assert_eq!(
            tables_to_markdown(md),
            "Before\n\n| A | B | C |\n| --- | --- | --- |\n| 1 Yes |  | x |\n\
             | 6 Oppose | secret/mystic |  |\n\nAfter\n"
        );
    }

    #[test]
    fn pads_short_rows_and_escapes_markdown() {
        let md = "<TABLE><tr><td>a|b</td><td>*x* &amp; y</td></tr><tr><td>c</td></tr></TABLE>\n";
        assert_eq!(
            tables_to_markdown(md),
            "\n| a\\|b | \\*x\\* & y |\n| --- | --- |\n| c |  |\n\n"
        );
    }

    #[test]
    fn leaves_code_and_unclosed_tables_alone() {
        let fenced = "```\n<table><tr><td>a</td></tr></table>\n```\n";
        assert_eq!(tables_to_markdown(fenced), fenced);
        let open = "<table><tr><td>a</td></tr>\n";
        assert_eq!(tables_to_markdown(open), open);
        assert!(matches!(tables_to_markdown("plain"), Cow::Borrowed(_)));
    }
}
