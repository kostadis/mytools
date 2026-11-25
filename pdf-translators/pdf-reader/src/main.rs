use clap::{Parser, Subcommand};
use rpg_pdf_reader::{protocol, reader};
use serde_json::json;
use std::{
    collections::BTreeSet,
    panic::{AssertUnwindSafe, catch_unwind},
    path::PathBuf,
};
#[derive(Parser)]
#[command(version, about = "Read PDF metadata and page text as JSON Lines")]
struct Args {
    #[command(subcommand)]
    command: Command,
}
#[derive(Subcommand)]
enum Command {
    Inspect {
        input: PathBuf,
    },
    Extract {
        input: PathBuf,
        #[arg(long)]
        pages: Option<String>,
    },
}
fn selection(spec: Option<&str>, count: u32) -> Result<Vec<u32>, String> {
    let Some(spec) = spec else {
        return Ok((1..=count).collect());
    };
    let mut pages = BTreeSet::new();
    for part in spec.split(',') {
        let (start, end) = if let Some((a, b)) = part.split_once('-') {
            (a.parse::<u32>(), b.parse::<u32>())
        } else {
            let n = part.parse::<u32>();
            (n.clone(), n)
        };
        let (a, b) = (
            start.map_err(|_| "invalid page selection")?,
            end.map_err(|_| "invalid page selection")?,
        );
        if a == 0 || b < a || b > count {
            return Err("page selection out of range".into());
        }
        pages.extend(a..=b);
    }
    Ok(pages.into_iter().collect())
}
fn run(args: Args) -> std::io::Result<i32> {
    let (input, spec, inspect) = match args.command {
        Command::Inspect { input } => (input, None, true),
        Command::Extract { input, pages } => (input, pages, false),
    };
    let reader = match catch_unwind(AssertUnwindSafe(|| reader::Reader::open(&input))) {
        Ok(Ok(r)) => r,
        other => {
            let (code, message) = match other {
                Ok(Err((c, m))) => (c, m),
                _ => ("reader_failure", "PDF loader panicked".into()),
            };
            protocol::emit(json!({"type":"error","code":code,"message":message}))?;
            protocol::emit(
                json!({"type":"end","complete":false,"requested":0,"emitted":0,"failed":0}),
            )?;
            return Ok(1);
        }
    };
    let pages = if inspect {
        vec![]
    } else {
        match selection(spec.as_deref(), reader.count) {
            Ok(p) => p,
            Err(e) => {
                eprintln!("{e}");
                return Ok(2);
            }
        }
    };
    protocol::emit(
        json!({"type":"document","protocol":1,"backend":protocol::BACKEND,"build":env!("CARGO_PKG_VERSION"),"page_count":reader.count,"requested":pages,"outline":reader.outline}),
    )?;
    let (mut emitted, mut failed) = (0, 0);
    for page in &pages {
        match catch_unwind(AssertUnwindSafe(|| reader.text(*page))) {
            Ok(Ok(text)) => {
                protocol::emit(json!({"type":"page","page":page,"text":text}))?;
                emitted += 1
            }
            other => {
                let message = match other {
                    Ok(Err(e)) => e,
                    _ => "content extractor panicked".into(),
                };
                protocol::emit(
                    json!({"type":"error","code":"unsupported_content","page":page,"message":message}),
                )?;
                failed += 1
            }
        }
    }
    protocol::emit(
        json!({"type":"end","complete":failed==0,"requested":pages.len(),"emitted":emitted,"failed":failed}),
    )?;
    Ok(if failed == 0 { 0 } else { 1 })
}
fn main() {
    let args = Args::parse();
    let code = match run(args) {
        Ok(c) => c,
        Err(e) => {
            eprintln!("output error: {e}");
            1
        }
    };
    std::process::exit(code);
}
