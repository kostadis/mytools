fn main() -> std::process::ExitCode {
    match rpg_source_select::cli::run(std::env::args_os()) {
        Ok(code) => code,
        Err(error) => {
            eprintln!("rpg-source-select: {error}");
            std::process::ExitCode::from(
                if matches!(error, rpg_source_select::SelectionError::Usage(_)) {
                    2
                } else {
                    1
                },
            )
        }
    }
}
