# gdrive-cli

A unified command-line interface for Google Drive and OneDrive.

## Features

- **Google Drive**: Scan, Dupes, Move, Trash commands
- **OneDrive**: Scan, Dupes, Move, Trash commands
- **Unified authentication**: Single configuration directory for both services
- **Dry-run mode**: Safe testing before executing changes
- **JSONL output**: Structured output for integration with other tools

## Installation

### Prerequisites

- Rust (1.60+)
- A Google Cloud Platform project with Drive API enabled
- An Azure AD app registration with Microsoft Graph permissions

### Build from source

```bash
# Clone the repository
git clone https://github.com/yourusername/gdrive-cli.git
cd gdrive-cli

# Build the project
cargo build --release

# Install the binary (optional)
cargo install --path .
```

## Setup

### Google Drive Setup

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the Google Drive API
4. Go to "Credentials" and create an "OAuth 2.0 Client ID"
5. Select "Desktop application" as the application type
6. Download the credentials JSON file
7. Save it as `~/.config/gdrive-cli/credentials.json`

### OneDrive Setup

1. Go to the [Azure Portal](https://portal.azure.com/)
2. Create a new App Registration
3. Add a redirect URI of `http://localhost:8080`
4. Add the following API permissions:
   - Files.Read (Delegated)
   - Files.ReadWrite (Delegated)
5. Create a client secret and save it
6. Download the credentials JSON file
7. Save it as `~/.config/gdrive-cli/credentials.json`

> Note: Both Google Drive and OneDrive use the same credentials.json file. The application will detect which service you're using based on the client_id format.

## Usage

### Google Drive Commands

```bash
# Scan Google Drive
./target/release/gdrive-cli google scan --out drive-scan.jsonl

# Find duplicates in a scan
./target/release/gdrive-cli google dupes drive-scan.jsonl --exclude "backup" "temp" --min-group 2

# Move files to a folder
./target/release/gdrive-cli google move FILE_ID_1 FILE_ID_2 --to "MyFolder" --create-folder --execute

# Trash files
./target/release/gdrive-cli google trash FILE_ID_1 FILE_ID_2 --execute
```

### OneDrive Commands

```bash
# Scan OneDrive
./target/release/gdrive-cli onedrive scan --out onedrive-scan.jsonl

# Find duplicates in a scan
./target/release/gdrive-cli onedrive dupes onedrive-scan.jsonl --exclude "backup" "temp" --min-group 2

# Move files to a folder
./target/release/gdrive-cli onedrive move FILE_ID_1 FILE_ID_2 --to "MyFolder" --create-folder --execute

# Trash files
./target/release/gdrive-cli onedrive trash FILE_ID_1 FILE_ID_2 --execute
```

## Command Reference

### Google Scan

```
Usage: gdrive-cli google scan [OPTIONS]

Options:
    --out <OUT>             Output path for JSONL file (default: drive-scan.jsonl)
    --all-drives, -a        Include files from all drives (not just My Drive)
    --include-trashed, -t   Include trashed files
    -h, --help              Print help
```

### Google Dupes

```
Usage: gdrive-cli google dupes [OPTIONS] <JSONL>

Arguments:
    <JSONL>    Input JSONL scan file

Options:
    --exclude <EXCLUDE>...    Patterns to exclude
    --min-group <MIN_GROUP>   Minimum group size (default: 2)
    -h, --help                Print help
```

### Google Move

```
Usage: gdrive-cli google move [OPTIONS] <FILE_IDS>...

Arguments:
    <FILE_IDS>...    File IDs to move (space-separated)

Options:
    --to <TO>               Destination folder name or ID
    --create-folder, -c     Create destination folder if it doesn't exist
    --execute, -e           Actually execute (dry-run by default)
    -h, --help              Print help
```

### Google Trash

```
Usage: gdrive-cli google trash [OPTIONS] <FILE_IDS>...

Arguments:
    <FILE_IDS>...    File IDs to trash (space-separated)

Options:
    --execute, -e    Actually execute (dry-run by default)
    -h, --help       Print help
```

### OneDrive Scan

```
Usage: gdrive-cli onedrive scan [OPTIONS]

Options:
    --out <OUT>             Output path for JSONL file (default: onedrive-scan.jsonl)
    --include-trashed, -t   Include trashed files
    -h, --help              Print help
```

### OneDrive Dupes

```
Usage: gdrive-cli onedrive dupes [OPTIONS] <JSONL>

Arguments:
    <JSONL>    Input JSONL scan file

Options:
    --exclude <EXCLUDE>...    Patterns to exclude
    --min-group <MIN_GROUP>   Minimum group size (default: 2)
    -h, --help                Print help
```

### OneDrive Move

```
Usage: gdrive-cli onedrive move [OPTIONS] <FILE_IDS>...

Arguments:
    <FILE_IDS>...    File IDs to move (space-separated)

Options:
    --to <TO>               Destination folder name or ID
    --create-folder, -c     Create destination folder if it doesn't exist
    --execute, -e           Actually execute (dry-run by default)
    -h, --help              Print help
```

### OneDrive Trash

```
Usage: gdrive-cli onedrive trash [OPTIONS] <FILE_IDS>...

Arguments:
    <FILE_IDS>...    File IDs to trash (space-separated)

Options:
    --execute, -e    Actually execute (dry-run by default)
    -h, --help       Print help
```

## Configuration Files

The tool uses the following files in `~/.config/gdrive-cli/`:

- `credentials.json` - Google Cloud Platform or Azure AD credentials
- `token.json` - Google Drive read-only access token
- `token-write.json` - Google Drive write access token
- `onedrive-token.json` - OneDrive access token

## Notes

- The tool uses dry-run mode by default for safety. Use `--execute` or `-e` to perform actual operations.
- Duplicate detection normalizes filenames by removing common variants like "Copy of", "(1)", "- copy", etc.
- Folder paths are resolved recursively for both services.
- For large scans, the tool outputs progress information to stderr.

## Troubleshooting

### Authentication Issues

If you get authentication errors:

1. Ensure your credentials.json file is correctly formatted
2. Delete the token files in `~/.config/gdrive-cli/` and re-authenticate
3. Make sure the API services are enabled in your cloud provider

### Performance Issues

For very large drives with thousands of files:

- Use `--exclude` patterns to filter out unnecessary files
- Consider running scans during off-peak hours
- The tool uses pagination and rate limiting to avoid API limits

## License

MIT License

## Contributing

Contributions are welcome! Please open an issue or pull request on GitHub.