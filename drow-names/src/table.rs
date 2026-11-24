//! Parse the pasted name-element table into structured data.
//!
//! The source text is third-party content and lives in homebrew-private; this module only
//! knows its *shape*. Parsing is deterministic and all-or-nothing: any line that does not fit
//! is an error, and section sizes must match `EXPECTED`.

use serde::{Deserialize, Serialize};

/// Which sex an element may be used for.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Sex {
    Female,
    Male,
    /// The source gives a single form, not a female/male pair.
    Either,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Element {
    pub text: String,
    pub sex: Sex,
    pub meanings: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Tables {
    pub source: String,
    pub prefixes: Vec<Element>,
    pub suffixes: Vec<Element>,
    pub house_prefixes: Vec<Element>,
    pub house_suffixes: Vec<Element>,
    /// Source rows printed with a single form rather than a female/male pair.
    pub single_form_rows: Vec<String>,
}

#[derive(Clone, Copy)]
enum Section {
    Prefix,
    Suffix,
    HousePrefix,
    HouseSuffix,
}

const HEADERS: [(&str, Section); 4] = [
    ("Prefix (Female/Male) - Meaning", Section::Prefix),
    ("Suffixes (Female/Male) - Meaning", Section::Suffix),
    ("House Name Prefixes - Meaning", Section::HousePrefix),
    ("House Name Suffixes - Meaning", Section::HouseSuffix),
];

/// Row counts per section: prefixes, suffixes, house prefixes, house suffixes.
pub const EXPECTED: [usize; 4] = [100, 100, 30, 30];

/// Split a row into (name column, meaning column). Columns are separated by a run of 2+
/// whitespace; one source row ("vyll punishment, ...") uses a single space, so fall back to
/// the first whitespace.
fn split_row(line: &str) -> Option<(&str, &str)> {
    let bytes = line.as_bytes();
    let mut i = 0;
    while i + 1 < bytes.len() {
        if bytes[i].is_ascii_whitespace() && bytes[i + 1].is_ascii_whitespace() {
            return Some((line[..i].trim(), line[i..].trim()));
        }
        i += 1;
    }
    line.split_once(char::is_whitespace)
        .map(|(a, b)| (a.trim(), b.trim()))
}

pub fn parse(src: &str, source_label: &str) -> Result<Tables, String> {
    let mut rows: [Vec<(String, Vec<String>, usize)>; 4] = Default::default();
    let mut section: Option<usize> = None;

    for (lineno, raw) in src.lines().enumerate() {
        let line = raw.trim();
        if line.is_empty() {
            continue;
        }
        if let Some(idx) = HEADERS.iter().position(|(h, _)| *h == line) {
            section = Some(idx);
            continue;
        }
        let Some(s) = section else { continue }; // preamble before the first header
        let (names, meanings) = split_row(line)
            .ok_or_else(|| format!("line {}: cannot split: {line:?}", lineno + 1))?;
        if names.is_empty() || meanings.is_empty() || names.contains(char::is_whitespace) {
            return Err(format!("line {}: malformed row: {line:?}", lineno + 1));
        }
        let meanings: Vec<String> = meanings
            .split(',')
            .map(|m| m.trim().to_string())
            .filter(|m| !m.is_empty())
            .collect();
        let forms: Vec<String> = names.split('/').map(str::to_string).collect();
        if forms.is_empty() || forms.len() > 2 || forms.iter().any(|f| f.is_empty()) {
            return Err(format!("line {}: bad name column {names:?}", lineno + 1));
        }
        rows[s].push((names.to_string(), meanings, lineno + 1));
    }

    for (i, (h, _)) in HEADERS.iter().enumerate() {
        if rows[i].len() != EXPECTED[i] {
            return Err(format!(
                "section {h:?}: expected {} rows, found {}",
                EXPECTED[i],
                rows[i].len()
            ));
        }
    }

    let mut single_form_rows = Vec::new();
    let mut build = |s: usize, gendered: bool| -> Vec<Element> {
        let mut out = Vec::new();
        for (names, meanings, _) in &rows[s] {
            let forms: Vec<&str> = names.split('/').collect();
            match (gendered, forms.as_slice()) {
                (true, [f, m]) => {
                    out.push(Element {
                        text: f.to_string(),
                        sex: Sex::Female,
                        meanings: meanings.clone(),
                    });
                    out.push(Element {
                        text: m.to_string(),
                        sex: Sex::Male,
                        meanings: meanings.clone(),
                    });
                }
                (_, [one]) => {
                    if gendered {
                        single_form_rows.push(one.to_string());
                    }
                    out.push(Element {
                        text: one.to_string(),
                        sex: Sex::Either,
                        meanings: meanings.clone(),
                    });
                }
                _ => unreachable!("validated above"),
            }
        }
        out
    };
    let prefixes = build(0, true);
    let suffixes = build(1, true);
    let house_prefixes = build(2, false);
    let house_suffixes = build(3, false);
    if house_prefixes
        .iter()
        .chain(&house_suffixes)
        .any(|e| e.text.contains('/'))
    {
        return Err("house names must not have female/male forms".into());
    }

    Ok(Tables {
        source: source_label.to_string(),
        prefixes,
        suffixes,
        house_prefixes,
        house_suffixes,
        single_form_rows,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Synthetic fixture (invented elements, not from the source) with tiny section sizes.
    fn fixture() -> String {
        let mut s = String::from("chatter before the table\n\n");
        s += "Prefix (Female/Male) - Meaning\n";
        for i in 0..EXPECTED[0] {
            if i == 0 {
                s += "Qoz      lonely, test\n";
            } else {
                s += &format!("Fa{i}/Ma{i}      word{i}, other\n");
            }
        }
        s += "Suffixes (Female/Male) - Meaning\n";
        for i in 0..EXPECTED[1] {
            if i == 0 {
                s += "zz single, space\n";
            } else {
                s += &format!("fs{i}/ms{i}      thing{i}\n");
            }
        }
        s += "House Name Prefixes - Meaning\n";
        for i in 0..EXPECTED[2] {
            s += &format!("Hp{i}     friends of\n");
        }
        s += "House Name Suffixes - Meaning\n";
        for i in 0..EXPECTED[3] {
            s += &format!("hs{i}     the test\n");
        }
        s
    }

    #[test]
    fn parses_fixture() {
        let t = parse(&fixture(), "fixture").unwrap();
        assert_eq!(t.prefixes.len(), 1 + 2 * (EXPECTED[0] - 1));
        assert_eq!(t.prefixes[0].sex, Sex::Either);
        assert_eq!(
            t.prefixes[1],
            Element {
                text: "Fa1".into(),
                sex: Sex::Female,
                meanings: vec!["word1".into(), "other".into()]
            }
        );
        assert_eq!(t.suffixes[0].text, "zz");
        assert_eq!(t.suffixes[0].meanings, vec!["single", "space"]);
        assert_eq!(t.single_form_rows, vec!["Qoz", "zz"]);
        assert_eq!(t.house_suffixes[0].meanings, vec!["the test"]);
    }

    #[test]
    fn rejects_wrong_count() {
        let src = fixture().replacen("Fa1/Ma1      word1, other\n", "", 1);
        assert!(parse(&src, "x").unwrap_err().contains("expected"));
    }

    #[test]
    fn deterministic() {
        let a = serde_json::to_string(&parse(&fixture(), "f").unwrap()).unwrap();
        let b = serde_json::to_string(&parse(&fixture(), "f").unwrap()).unwrap();
        assert_eq!(a, b);
    }
}
