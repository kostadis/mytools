pub mod scan;
pub mod dupes;
pub mod move_file;
pub mod trash;

use anyhow::Result;
use crate::GoogleCommands;

pub async fn handle(command: GoogleCommands) -> Result<()> {
    match command {
        GoogleCommands::Scan { out, all_drives, include_trashed } => {
            scan::run(&out, all_drives, include_trashed).await
        }
        GoogleCommands::Dupes { jsonl, exclude, min_group } => {
            dupes::run(&jsonl, &exclude, min_group)
        }
        GoogleCommands::Move { file_ids, to, create_folder, execute } => {
            move_file::run(file_ids, &to, create_folder, execute).await
        }
        GoogleCommands::Trash { file_ids, execute } => {
            trash::run(file_ids, execute).await
        }
    }
}