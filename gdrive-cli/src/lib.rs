//! gdrive-cli - A unified CLI for Google Drive and OneDrive
//!
//! This crate provides the core functionality for the gdrive-cli tool.

use clap::{Parser, Subcommand};

pub mod auth;
pub mod google;
pub mod onedrive;

#[derive(Parser)]
#[command(version, about, long_about = None)]
pub struct Cli {
    #[command(subcommand)]
    pub command: Commands,
}

#[derive(Subcommand)]
pub enum Commands {
    Google(GoogleArgs),
    Onedrive(OnedriveArgs),
}

#[derive(Parser)]
pub struct GoogleArgs {
    #[command(subcommand)]
    pub command: GoogleCommands,
}

#[derive(Subcommand)]
pub enum GoogleCommands {
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
    /// Export a native Google Doc/Sheet/Slide as text (files.export)
    Export {
        /// File ID to export
        file_id: String,
        /// Output path (default: stdout)
        #[arg(long)]
        out: Option<String>,
        /// Export MIME type
        #[arg(long, default_value = "text/plain")]
        mime: String,
    },
    /// Download raw file content (binary-safe) to a file or stdout (alt=media)
    Cat {
        /// File ID to download
        file_id: String,
        /// Output path (default: stdout)
        #[arg(long)]
        out: Option<String>,
    },
    /// Set app-private appProperties (tags) on a file (files.update)
    Tag {
        /// File ID to tag
        file_id: String,
        /// key=value pair to set; repeat for multiple (e.g. --set a=b --set c=d)
        #[arg(long = "set", value_name = "KEY=VALUE")]
        set: Vec<String>,
        /// Actually execute (dry-run by default)
        #[arg(long, short)]
        execute: bool,
    },
    /// Read a file's metadata + appProperties as JSON (files.get)
    Get {
        /// File ID
        file_id: String,
    },
}

#[derive(Parser)]
pub struct OnedriveArgs {
    #[command(subcommand)]
    pub command: OnedriveCommands,
}

#[derive(Subcommand)]
pub enum OnedriveCommands {
    /// List all files and output as JSONL
    Scan {
        /// Output path for JSONL file
        #[arg(long, default_value = "onedrive-scan.jsonl")]
        out: String,
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