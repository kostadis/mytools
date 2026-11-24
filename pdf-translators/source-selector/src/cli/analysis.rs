use crate::{
    Result,
    analysis::{models::AnalysisConfig, read_json, workflow},
};
use clap::Subcommand;
use std::{path::PathBuf, process::ExitCode};
#[derive(Subcommand)]
pub enum Command {
    Run {
        #[arg(long)]
        config: PathBuf,
        #[arg(long)]
        output: PathBuf,
    },
    ReviewExport {
        #[arg(long)]
        run: PathBuf,
        #[arg(long)]
        output: PathBuf,
    },
    ReviewImport {
        #[arg(long)]
        run: PathBuf,
        #[arg(long)]
        manifest: PathBuf,
        #[arg(long)]
        results: PathBuf,
        #[arg(long)]
        output: PathBuf,
    },
}
pub fn execute(command: &Command) -> Result<ExitCode> {
    match command {
        Command::Run { config, output } => {
            let c: AnalysisConfig = read_json(config)?;
            let audit = workflow::run(&c, output)?;
            super::print_json(
                &serde_json::json!({"provisional":audit.provisional,"counts":audit.counts,"report":output.join("report/report.md")}),
            )?;
        }
        Command::ReviewExport { run, output } => {
            let m = workflow::export(run, output)?;
            super::print_json(
                &serde_json::json!({"review_id":m.review_id,"cases":m.items["items"].as_array().map(Vec::len),"output":output}),
            )?;
        }
        Command::ReviewImport {
            run,
            manifest,
            results,
            output,
        } => {
            let a = workflow::import(run, manifest, results, output)?;
            super::print_json(&serde_json::json!({"counts":a.counts,"output":output}))?;
        }
    }
    Ok(ExitCode::SUCCESS)
}
