pub mod entry;
pub mod homebrew;
pub mod validation;
pub mod tags;

use clap::Parser;
use serde_json;
use std::fs;
use homebrew::HomebrewAdventure;

#[derive(Parser)]
struct Cli {
    #[clap(short, long)]
    input: String,
    #[clap(short, long)]
    output: String,
    #[clap(short, long)]
    validate: bool,
}

fn main() {
    let cli = Cli::parse();
    
    // Read input file
    let input = match fs::read_to_string(&cli.input) {
        Ok(content) => content,
        Err(e) => {
            eprintln!("Error reading input file: {}", e);
            std::process::exit(1);
        }
    };
    
    // Parse the JSON
    let mut adventure: HomebrewAdventure = match serde_json::from_str(&input) {
        Ok(adv) => adv,
        Err(e) => {
            eprintln!("Error parsing JSON: {}", e);
            std::process::exit(2);
        }
    };
    
    if cli.validate {
        // Validate the parsed adventure
        let ctx = adventure.validate();
        println!("Validation result: {}", ctx.result.summary());
        
        if !ctx.result.errors.is_empty() {
            println!("Errors:");
            for err in &ctx.result.errors {
                println!("  ERROR: {}", err);
            }
        }
        if !ctx.result.warnings.is_empty() {
            println!("Warnings:");
            for warn in &ctx.result.warnings {
                println!("  WARN:  {}", warn);
            }
        }
    }
    
    // Assign IDs and build TOC
    adventure.assign_ids();
    adventure.build_toc();
    
    // Write output
    let output_json = match serde_json::to_string_pretty(&adventure) {
        Ok(json) => json,
        Err(e) => {
            eprintln!("Error serializing to JSON: {}", e);
            std::process::exit(3);
        }
    };
    
    if let Err(e) = fs::write(&cli.output, output_json) {
        eprintln!("Error writing output file: {}", e);
        std::process::exit(4);
    }
}