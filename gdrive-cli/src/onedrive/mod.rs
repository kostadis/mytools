pub mod scan;
pub mod dupes;
pub mod move_file;
pub mod trash;

use anyhow::Result;
use super::OnedriveCommands;

pub async fn handle(command: OnedriveCommands) -> Result<()> {
    match command {
        OnedriveCommands::Scan { out, include_trashed } => {
            scan::run(&out, include_trashed).await
        }
        OnedriveCommands::Dupes { jsonl, exclude, min_group } => {
            dupes::run(&jsonl, &exclude, min_group)
        }
        OnedriveCommands::Move { file_ids, to, create_folder, execute } => {
            move_file::run(file_ids, &to, create_folder, execute).await
        }
        OnedriveCommands::Trash { file_ids, execute } => {
            trash::run(file_ids, execute).await
        }
    }
}