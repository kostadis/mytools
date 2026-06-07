use gdrive_cli::{Cli, google, onedrive};
use anyhow::Result;
use clap::Parser;

#[tokio::main]
async fn main() -> Result<()> {
    let cli = Cli::parse();

    match cli.command {
        gdrive_cli::Commands::Google(args) => {
            google::handle(args.command).await?;
        }
        gdrive_cli::Commands::Onedrive(args) => {
            onedrive::handle(args.command).await?;
        }
    }

    Ok(())
}