mod auth;
mod google;
mod onedrive;

use anyhow::Result;
use clap::{Parser, Subcommand};

#[derive(Parser)]
#[command(author, version, about = "Unified CLI for Google Drive and OneDrive")]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    Google(GoogleArgs),
    Onedrive(OnedriveArgs),
}

#[derive(Parser)]
struct GoogleArgs {
    #[command(subcommand)]
    command: GoogleCommands,
}

#[derive(Subcommand)]
enum GoogleCommands {
    /// List all files and output as JSONL
    Scan {
        /// Output path for JSONL file
        #[arg(long, default_value = "drive-scan.jsonl")]
        out: String,
        /// Include files from all drives (not just My Drive)
        #[arg(long, short)]
        all_drives: bool,
        /// Include trashed files
        #[arg(long, short)]
        include_trashed: bool,
    },
    /// Find duplicate files in a scan
    Dupes {
        /// Input JSONL scan file
        jsonl: String,
        /// Patterns to exclude
        #[arg(long, short)]
        exclude: Vec<String>,
        /// Minimum group size (default: 2)
        #[arg(long, short, default_value = "2")]
        min_group: usize,
    },
    /// Move files to a folder
    Move {
        /// File IDs to move (space-separated)
        #[arg(num_args = 1..)]
        file_ids: Vec<String>,
        /// Destination folder name or ID
        #[arg(long, short)]
        to: String,
        /// Create destination folder if it doesn't exist
        #[arg(long, short)]
        create_folder: bool,
        /// Actually execute (dry-run by default)
        #[arg(long, short)]
        execute: bool,
    },
    /// Trash files
    Trash {
        /// File IDs to trash (space-separated)
        #[arg(num_args = 1..)]
        file_ids: Vec<String>,
        /// Actually execute (dry-run by default)
        #[arg(long, short)]
        execute: bool,
    },
}

#[derive(Parser)]
struct OnedriveArgs {
    #[command(subcommand)]
    command: OnedriveCommands,
}

#[derive(Subcommand)]
enum OnedriveCommands {
    /// List all files and output as JSONL
    Scan {
        /// Output path for JSONL file
        #[arg(long, default_value = "onedrive-scan.jsonl")]
        out: String,
        /// Include trashed files
        #[arg(long, short)]
        include_trashed: bool,
    },
}

#[tokio::main]
async fn main() -> Result<()> {
    let cli = Cli::parse();

    match cli.command {
        Commands::Google(args) => {
            google::handle(args.command).await?;
        }
        Commands::Onedrive(args) => {
            onedrive::handle(args.command).await?;
        }
    }

    Ok(())
}