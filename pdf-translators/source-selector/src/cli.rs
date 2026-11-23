use crate::{
    Result, SelectionError,
    export::{build_snapshot, validate_work_dir, write_exports},
    models::InventoryResult,
    store::Store,
};
use clap::{Args, Parser, Subcommand, ValueEnum};
use serde::Serialize;
use serde_json::json;
use std::{
    ffi::OsString,
    fs,
    path::{Path, PathBuf},
    process::ExitCode,
};
mod inspect;
mod review;
mod scan;

#[derive(Parser)]
#[command(
    name = "rpg-source-select",
    version,
    about = "Select current, distinct RPG PDFs without changing the library"
)]
struct Cli {
    #[arg(long, global = true)]
    work_dir: Option<PathBuf>,
    #[command(subcommand)]
    command: Commands,
}
#[derive(Subcommand)]
enum Commands {
    Scan(Scan),
    Inspect(Inspect),
    Review {
        #[command(subcommand)]
        command: ReviewCommand,
    },
    Export,
    Status,
}
#[derive(Args)]
struct Scan {
    #[arg(long)]
    root: PathBuf,
    #[arg(long)]
    muse_csv: Option<PathBuf>,
    #[arg(long)]
    twins_json: Option<PathBuf>,
    #[arg(long)]
    rpglib_json: Option<PathBuf>,
    #[arg(long)]
    baseline_manifest: Option<PathBuf>,
}
#[derive(Args)]
struct Inspect {
    #[arg(long)]
    group: Option<String>,
    #[arg(long, default_value_t = 10)]
    limit: usize,
    #[arg(long)]
    pages: Option<String>,
    #[arg(long, default_value = "pdftotext")]
    pdftotext: PathBuf,
    #[arg(long, default_value_t = 120)]
    timeout_secs: u64,
}
#[derive(Subcommand)]
enum ReviewCommand {
    Export {
        #[arg(long, value_enum)]
        role: Role,
        #[arg(long, default_value_t = 10)]
        limit: usize,
        #[arg(long)]
        group: Option<String>,
        #[arg(long)]
        out: PathBuf,
    },
    Import {
        #[arg(long)]
        file: PathBuf,
    },
}
#[derive(Clone, Copy, ValueEnum)]
enum Role {
    Reader,
    Sol,
    User,
}
impl From<Role> for crate::models::ActorRole {
    fn from(role: Role) -> Self {
        match role {
            Role::Reader => Self::Reader,
            Role::Sol => Self::Sol,
            Role::User => Self::User,
        }
    }
}

pub fn run(args: impl IntoIterator<Item = OsString>) -> Result<ExitCode> {
    let cli = match Cli::try_parse_from(args) {
        Ok(v) => v,
        Err(e) => {
            if matches!(
                e.kind(),
                clap::error::ErrorKind::DisplayHelp | clap::error::ErrorKind::DisplayVersion
            ) {
                print!("{e}");
                return Ok(ExitCode::SUCCESS);
            }
            return Err(SelectionError::Usage(e.to_string()));
        }
    };
    let work = cli
        .work_dir
        .ok_or_else(|| SelectionError::Usage("--work-dir is required".into()))?;
    if let Commands::Scan(args) = cli.command {
        return scan::run(&work, args);
    }
    let dbpath = work.join("selection.db");
    refuse_symlink_database(&dbpath)?;
    let ro = Store::open_readonly(&dbpath)?;
    let inventory: InventoryResult = serde_json::from_value(
        ro.meta("inventory")?
            .ok_or_else(|| SelectionError::Invalid("scan first".into()))?,
    )?;
    validate_work_dir(&inventory.root, &work)?;
    if matches!(cli.command, Commands::Status) {
        print_json(
            &json!({"root":inventory.root.to_string_lossy(),"scan_started":inventory.started,"scan_finished":inventory.finished,"sources":inventory.sources.len(),"coverage_errors":inventory.errors,"groups":ro.count_records("groups")?,"inspected_sources":ro.count_records("evidence")?,"stored_decisions":ro.count_records("decisions")?,"note":"Stored status only; export revalidates source bytes"}),
        )?;
        return Ok(ExitCode::SUCCESS);
    }
    drop(ro);
    let mut store = Store::open(&dbpath)?;
    match cli.command {
        Commands::Inspect(args) => inspect::run(&mut store, args),
        Commands::Review { command } => review::run(&mut store, command),
        Commands::Export => {
            let snapshot = build_snapshot(&store)?;
            let files = write_exports(&snapshot, &work.join("exports"))?;
            print_json(&json!({"files":files,"counts":snapshot.counts}))?;
            Ok(ExitCode::SUCCESS)
        }
        _ => unreachable!(),
    }
}
fn print_json(value: &impl Serialize) -> Result<()> {
    println!("{}", serde_json::to_string_pretty(value)?);
    Ok(())
}
fn refuse_symlink_database(path: &Path) -> Result<()> {
    for path in [
        path.to_path_buf(),
        PathBuf::from(format!("{}-wal", path.display())),
        PathBuf::from(format!("{}-shm", path.display())),
    ] {
        if path
            .symlink_metadata()
            .is_ok_and(|m| m.file_type().is_symlink())
        {
            return Err(SelectionError::Invalid(
                "database and journal paths must not be symlinks".into(),
            ));
        }
    }
    Ok(())
}
fn read_json(path: &Path) -> Result<serde_json::Value> {
    serde_json::from_slice(&fs::read(path)?)
        .map_err(|e| SelectionError::Usage(format!("{}: {e}", path.display())))
}
