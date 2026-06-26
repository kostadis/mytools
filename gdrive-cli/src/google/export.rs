use anyhow::Result;
use std::io::Write;

use crate::auth::google::drive_client_read;

/// Export a native Google editor file (Docs/Sheets/Slides) to text and write it
/// to `out` (a file path) or stdout. Uses the read-only token.
pub async fn run(file_id: &str, out: Option<&str>, mime: &str) -> Result<()> {
    let (client, access_token) = drive_client_read().await?;

    let url = format!(
        "https://www.googleapis.com/drive/v3/files/{}/export?mimeType={}&supportsAllDrives=true",
        file_id,
        urlencoding::encode(mime)
    );

    let resp = client
        .get(&url)
        .bearer_auth(&access_token)
        .send()
        .await?;

    if !resp.status().is_success() {
        let status = resp.status();
        let error = resp.text().await.unwrap_or_default();
        anyhow::bail!("Export failed ({}): {}", status, error);
    }

    let bytes = resp.bytes().await?;

    match out {
        Some(path) => {
            std::fs::write(path, &bytes)?;
            eprintln!("EXPORTED {} bytes -> {}", bytes.len(), path);
        }
        None => {
            let mut stdout = std::io::stdout();
            stdout.write_all(&bytes)?;
            stdout.flush()?;
        }
    }

    Ok(())
}
