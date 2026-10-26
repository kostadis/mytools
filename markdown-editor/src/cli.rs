//! Command-line parsing, by hand: two options don't justify a parser crate.

use crate::chooser_mode::ChooserPreference;
use std::ffi::OsString;
use std::path::PathBuf;

pub const USAGE: &str = "\
Usage: markdown-editor [--chooser=MODE] [--] [FILE]

Options:
  --chooser=MODE   Which file chooser Open and Save As use:
                     auto    system dialog on a local display, the built-in
                             chooser over SSH or when unsure (default)
                     system  always try the system dialog first
                     window  always use the built-in chooser
  -h, --help       Print this help and exit
  --               Treat everything after it as a file name
";

#[derive(Debug, Default, PartialEq, Eq)]
pub struct CliArgs {
    pub chooser: ChooserPreference,
    pub file: Option<PathBuf>,
}

#[derive(Debug, PartialEq, Eq)]
pub enum CliCommand {
    Run(CliArgs),
    Help,
}

#[derive(Debug, PartialEq, Eq)]
pub struct UsageError(pub String);

/// Parse the arguments after the program name. File names stay `OsString`
/// so names that aren't UTF-8 still open; options must be UTF-8.
pub fn parse(args: impl IntoIterator<Item = OsString>) -> Result<CliCommand, UsageError> {
    let mut parsed = CliArgs::default();
    let mut files = Vec::new();
    let mut args = args.into_iter();
    while let Some(arg) = args.next() {
        let Some(text) = arg.to_str() else {
            files.push(arg);
            continue;
        };
        if text == "--" {
            files.extend(args.by_ref());
        } else if text == "-h" || text == "--help" {
            return Ok(CliCommand::Help);
        } else if text == "--chooser" {
            let value = args
                .next()
                .ok_or_else(|| UsageError("--chooser needs a value".to_owned()))?;
            parsed.chooser = chooser(value.to_str())?;
        } else if let Some(value) = text.strip_prefix("--chooser=") {
            parsed.chooser = chooser(Some(value))?;
        } else if text.starts_with('-') && text != "-" {
            return Err(UsageError(format!("unknown option '{text}'")));
        } else {
            files.push(arg);
        }
    }
    if files.len() > 1 {
        return Err(UsageError("expected at most one file".to_owned()));
    }
    parsed.file = files.pop().map(PathBuf::from);
    Ok(CliCommand::Run(parsed))
}

fn chooser(value: Option<&str>) -> Result<ChooserPreference, UsageError> {
    match value {
        Some("auto") => Ok(ChooserPreference::Auto),
        Some("system") => Ok(ChooserPreference::System),
        Some("window") => Ok(ChooserPreference::Window),
        Some(other) => Err(UsageError(format!(
            "unknown chooser '{other}' (expected auto, system or window)"
        ))),
        None => Err(UsageError(
            "unknown chooser (expected auto, system or window)".to_owned(),
        )),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn run(args: &[&str]) -> Result<CliCommand, UsageError> {
        parse(args.iter().map(OsString::from))
    }

    fn args(chooser: ChooserPreference, file: Option<&str>) -> Result<CliCommand, UsageError> {
        Ok(CliCommand::Run(CliArgs {
            chooser,
            file: file.map(PathBuf::from),
        }))
    }

    fn error(text: &str) -> Result<CliCommand, UsageError> {
        Err(UsageError(text.to_owned()))
    }

    #[test]
    fn files_and_options_parse_in_any_order() {
        use ChooserPreference::*;
        assert_eq!(run(&[]), args(Auto, None));
        assert_eq!(run(&["notes.md"]), args(Auto, Some("notes.md")));
        assert_eq!(
            run(&["--chooser=window", "notes.md"]),
            args(Window, Some("notes.md"))
        );
        assert_eq!(
            run(&["--chooser", "window", "notes.md"]),
            args(Window, Some("notes.md"))
        );
        assert_eq!(
            run(&["notes.md", "--chooser=system"]),
            args(System, Some("notes.md"))
        );
        assert_eq!(run(&["--chooser=auto"]), args(Auto, None));
    }

    #[test]
    fn a_double_dash_ends_the_options() {
        assert_eq!(
            run(&["--", "--chooser=window"]),
            args(ChooserPreference::Auto, Some("--chooser=window"))
        );
    }

    #[test]
    fn help_is_a_command() {
        assert_eq!(run(&["--help"]), Ok(CliCommand::Help));
        assert_eq!(run(&["-h"]), Ok(CliCommand::Help));
        assert_eq!(run(&["notes.md", "--help"]), Ok(CliCommand::Help));
    }

    #[test]
    fn bad_arguments_are_usage_errors() {
        assert_eq!(
            run(&["--chooser=bogus"]),
            error("unknown chooser 'bogus' (expected auto, system or window)")
        );
        assert_eq!(run(&["--chooser"]), error("--chooser needs a value"));
        assert_eq!(
            run(&["--frobnicate"]),
            error("unknown option '--frobnicate'")
        );
        assert_eq!(run(&["a.md", "b.md"]), error("expected at most one file"));
    }

    #[cfg(unix)]
    #[test]
    fn a_file_name_that_is_not_utf8_still_parses() {
        use std::os::unix::ffi::OsStringExt;
        let name = OsString::from_vec(b"caf\xe9.md".to_vec());
        let parsed = parse([name.clone()]);
        assert_eq!(
            parsed,
            Ok(CliCommand::Run(CliArgs {
                chooser: ChooserPreference::Auto,
                file: Some(PathBuf::from(name)),
            }))
        );
    }

    #[test]
    fn the_usage_text_lists_the_option() {
        assert!(USAGE.contains("--chooser=MODE"));
        assert!(USAGE.contains("-h, --help"));
    }
}
