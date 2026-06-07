pub mod scan;

use anyhow::Result;
use crate::OnedriveCommands;

pub async fn handle(command: OnedriveCommands) -> Result<()> {
    match command {
        OnedriveCommands::Scan { out, include_trashed } => {
            scan::run(&out, include_trashed).await
        }
    }
}