//! drow-names: generate drow names from the Dragon #267 name-element table.
//!
//! The table is third-party content. It is never stored in this (public) repo:
//! `import` reads `source.txt` and writes `tables.json`, both under
//! `$DROW_NAMES_DATA_DIR/dragon-267-drow-names/` (default `~/src/homebrew-private/book`).

mod table;

use clap::{Parser, Subcommand, ValueEnum};
use rand::rngs::StdRng;
use rand::seq::SliceRandom;
use rand::SeedableRng;
use serde::Serialize;
use std::path::{Path, PathBuf};
use std::process::ExitCode;
use table::{Element, Sex, Tables};

const SLUG: &str = "dragon-267-drow-names";

#[derive(Parser)]
#[command(about = "Drow name generator (Dragon #267 name elements)")]
struct Cli {
    #[command(subcommand)]
    cmd: Option<Cmd>,
    /// How many names
    #[arg(short = 'n', default_value_t = 1, global = true)]
    count: usize,
    /// female | male (default: random)
    #[arg(long, value_enum, global = true)]
    sex: Option<SexArg>,
    /// House option: a female may also draw male elements (the reverse is never allowed)
    #[arg(long, global = true)]
    cross: bool,
    /// Seed for reproducible rolls
    #[arg(long, global = true)]
    seed: Option<u64>,
    /// Machine-readable output
    #[arg(long, global = true)]
    json: bool,
    /// Path to tables.json (default: $DROW_NAMES_DATA_DIR/<slug>/tables.json)
    #[arg(long, global = true)]
    data: Option<PathBuf>,
}

#[derive(Subcommand)]
enum Cmd {
    /// Full name: first name + house (default)
    Full,
    /// First name only
    First,
    /// House name only
    House,
    /// List every element in one table
    List {
        #[arg(value_enum)]
        table: ListTable,
    },
    /// Parse source.txt into tables.json (in homebrew-private, never in this repo)
    Import {
        #[arg(long)]
        src: Option<PathBuf>,
        #[arg(long)]
        out: Option<PathBuf>,
    },
}

#[derive(Clone, Copy, ValueEnum)]
enum SexArg {
    Female,
    Male,
}

#[derive(Clone, Copy, ValueEnum)]
enum ListTable {
    Prefixes,
    Suffixes,
    HousePrefixes,
    HouseSuffixes,
}

fn data_dir() -> PathBuf {
    if let Some(d) = std::env::var_os("DROW_NAMES_DATA_DIR") {
        return PathBuf::from(d).join(SLUG);
    }
    let home = std::env::var_os("HOME")
        .map(PathBuf::from)
        .unwrap_or_default();
    home.join("src/homebrew-private/book").join(SLUG)
}

fn repo_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .map(Path::to_path_buf)
        .unwrap_or_else(|| PathBuf::from(env!("CARGO_MANIFEST_DIR")))
}

fn import(src: Option<PathBuf>, out: Option<PathBuf>) -> Result<(), String> {
    let src = src.unwrap_or_else(|| data_dir().join("source.txt"));
    let out = out.unwrap_or_else(|| data_dir().join("tables.json"));
    let out_abs = std::path::absolute(&out).map_err(|e| e.to_string())?;
    let repo = std::fs::canonicalize(repo_dir()).unwrap_or_else(|_| repo_dir());
    let out_parent = out_abs.parent().unwrap_or(Path::new("/"));
    let out_parent = std::fs::canonicalize(out_parent).unwrap_or(out_parent.to_path_buf());
    if out_parent.starts_with(&repo) {
        return Err(format!(
            "refusing to write {} inside the public repo {}; third-party data belongs in homebrew-private",
            out.display(),
            repo.display()
        ));
    }
    let text = std::fs::read_to_string(&src).map_err(|e| format!("{}: {e}", src.display()))?;
    let t = table::parse(
        &text,
        "Dragon Magazine #267 (January 2000), drow name elements",
    )?;
    let json = serde_json::to_string_pretty(&t).map_err(|e| e.to_string())? + "\n";
    if let Some(p) = out.parent() {
        std::fs::create_dir_all(p).map_err(|e| e.to_string())?;
    }
    std::fs::write(&out, json).map_err(|e| e.to_string())?;
    eprintln!(
        "wrote {}: {} prefixes, {} suffixes, {} house prefixes, {} house suffixes",
        out.display(),
        t.prefixes.len(),
        t.suffixes.len(),
        t.house_prefixes.len(),
        t.house_suffixes.len()
    );
    eprintln!(
        "single-form rows (usable by either sex): {}",
        t.single_form_rows.join(", ")
    );
    Ok(())
}

fn load(path: Option<PathBuf>) -> Result<Tables, String> {
    let path = path.unwrap_or_else(|| data_dir().join("tables.json"));
    let text = std::fs::read_to_string(&path).map_err(|e| {
        format!(
            "{}: {e}\nRun `drow-names import` first (reads source.txt from the same directory).",
            path.display()
        )
    })?;
    serde_json::from_str(&text).map_err(|e| format!("{}: {e}", path.display()))
}

fn allowed(e: &Element, sex: Sex, cross: bool) -> bool {
    e.sex == Sex::Either || e.sex == sex || (cross && sex == Sex::Female && e.sex == Sex::Male)
}

#[derive(Serialize)]
struct Part {
    text: String,
    meaning: String,
    meanings: Vec<String>,
}

#[derive(Serialize)]
struct Name {
    #[serde(skip_serializing_if = "Option::is_none")]
    sex: Option<Sex>,
    #[serde(skip_serializing_if = "Option::is_none")]
    first: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    first_gloss: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    house: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    house_gloss: Option<String>,
    parts: Vec<Part>,
}

fn pick(rng: &mut StdRng, pool: &[&Element]) -> Part {
    let e = pool.choose(rng).expect("non-empty pool");
    Part {
        text: e.text.clone(),
        meaning: e.meanings.choose(rng).cloned().unwrap_or_default(),
        meanings: e.meanings.clone(),
    }
}

fn capitalize(s: &str) -> String {
    let mut c = s.chars();
    match c.next() {
        Some(f) => f.to_uppercase().collect::<String>() + c.as_str(),
        None => String::new(),
    }
}

fn generate(t: &Tables, rng: &mut StdRng, sex: Sex, cross: bool, first: bool, house: bool) -> Name {
    let mut name = Name {
        sex: None,
        first: None,
        first_gloss: None,
        house: None,
        house_gloss: None,
        parts: vec![],
    };
    if first {
        let pre: Vec<&Element> = t
            .prefixes
            .iter()
            .filter(|e| allowed(e, sex, cross))
            .collect();
        let suf: Vec<&Element> = t
            .suffixes
            .iter()
            .filter(|e| allowed(e, sex, cross))
            .collect();
        let p = pick(rng, &pre);
        let s = pick(rng, &suf);
        name.sex = Some(sex);
        name.first = Some(capitalize(&format!("{}{}", p.text, s.text)));
        name.first_gloss = Some(format!("{} {}", p.meaning, s.meaning));
        name.parts.extend([p, s]);
    }
    if house {
        let pre: Vec<&Element> = t.house_prefixes.iter().collect();
        let suf: Vec<&Element> = t.house_suffixes.iter().collect();
        let p = pick(rng, &pre);
        let s = pick(rng, &suf);
        name.house = Some(capitalize(&format!("{}{}", p.text, s.text)));
        name.house_gloss = Some(format!("{} {}", p.meaning, s.meaning));
        name.parts.extend([p, s]);
    }
    name
}

fn run() -> Result<(), String> {
    let cli = Cli::parse();
    let cmd = cli.cmd.unwrap_or(Cmd::Full);
    let (first, house) = match cmd {
        Cmd::Import { src, out } => return import(src, out),
        Cmd::List { table } => {
            let t = load(cli.data)?;
            let list = match table {
                ListTable::Prefixes => &t.prefixes,
                ListTable::Suffixes => &t.suffixes,
                ListTable::HousePrefixes => &t.house_prefixes,
                ListTable::HouseSuffixes => &t.house_suffixes,
            };
            if cli.json {
                println!(
                    "{}",
                    serde_json::to_string_pretty(list).map_err(|e| e.to_string())?
                );
            } else {
                for e in list {
                    let sex = match e.sex {
                        Sex::Female => "f",
                        Sex::Male => "m",
                        Sex::Either => "-",
                    };
                    println!("{:<10} {sex}  {}", e.text, e.meanings.join(", "));
                }
            }
            return Ok(());
        }
        Cmd::Full => (true, true),
        Cmd::First => (true, false),
        Cmd::House => (false, true),
    };
    let t = load(cli.data)?;
    let mut rng = match cli.seed {
        Some(s) => StdRng::seed_from_u64(s),
        None => StdRng::from_entropy(),
    };
    let mut out = Vec::new();
    for _ in 0..cli.count {
        let sex = match cli.sex {
            Some(SexArg::Female) => Sex::Female,
            Some(SexArg::Male) => Sex::Male,
            None => *[Sex::Female, Sex::Male].choose(&mut rng).unwrap(),
        };
        out.push(generate(&t, &mut rng, sex, cli.cross, first, house));
    }
    if cli.json {
        println!(
            "{}",
            serde_json::to_string_pretty(&out).map_err(|e| e.to_string())?
        );
        return Ok(());
    }
    for n in &out {
        let mut line = String::new();
        if let Some(f) = &n.first {
            let s = if n.sex == Some(Sex::Female) { "f" } else { "m" };
            line += &format!("{f} ({s}) — \"{}\"", n.first_gloss.as_deref().unwrap_or(""));
        }
        if let Some(h) = &n.house {
            if !line.is_empty() {
                line += "  of  ";
            }
            line += &format!("House {h} — \"{}\"", n.house_gloss.as_deref().unwrap_or(""));
        }
        println!("{line}");
    }
    Ok(())
}

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("drow-names: {e}");
            ExitCode::FAILURE
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn el(text: &str, sex: Sex) -> Element {
        Element {
            text: text.into(),
            sex,
            meanings: vec!["m".into()],
        }
    }

    #[test]
    fn male_never_gets_female_elements() {
        let f = el("x", Sex::Female);
        assert!(!allowed(&f, Sex::Male, true));
        assert!(!allowed(&f, Sex::Male, false));
    }

    #[test]
    fn cross_lets_female_take_male() {
        let m = el("x", Sex::Male);
        assert!(!allowed(&m, Sex::Female, false));
        assert!(allowed(&m, Sex::Female, true));
        assert!(allowed(&el("x", Sex::Either), Sex::Male, false));
    }

    #[test]
    fn seeded_is_reproducible() {
        let t = Tables {
            source: "fixture".into(),
            prefixes: vec![
                el("Qa", Sex::Female),
                el("Zo", Sex::Male),
                el("Vu", Sex::Female),
            ],
            suffixes: vec![el("rin", Sex::Male), el("la", Sex::Female)],
            house_prefixes: vec![el("Hy", Sex::Either), el("Tu", Sex::Either)],
            house_suffixes: vec![el("mek", Sex::Either)],
            single_form_rows: vec![],
        };
        let a = generate(
            &t,
            &mut StdRng::seed_from_u64(3),
            Sex::Female,
            false,
            true,
            true,
        );
        let b = generate(
            &t,
            &mut StdRng::seed_from_u64(3),
            Sex::Female,
            false,
            true,
            true,
        );
        assert_eq!(a.first, b.first);
        assert_eq!(a.house, b.house);
        assert!(a.first.unwrap().ends_with("la"));
    }
}
