pub mod scan;
pub mod dupes;
pub mod move_file;
pub mod trash;
pub mod export;
pub mod cat;
pub mod tag;
pub mod get;

use anyhow::Result;
use super::GoogleCommands;

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
        GoogleCommands::Export { file_id, out, mime } => {
            export::run(&file_id, out.as_deref(), &mime).await
        }
        GoogleCommands::Cat { file_id, out } => {
            cat::run(&file_id, out.as_deref()).await
        }
        GoogleCommands::Tag { file_id, set, execute } => {
            tag::run(&file_id, &set, execute).await
        }
        GoogleCommands::Get { file_id } => {
            get::run(&file_id).await
        }
    }
}