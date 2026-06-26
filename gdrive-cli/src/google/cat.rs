use anyhow::Result;
use std::io::Write;

use crate::auth::google::drive_client_read;

/// Download raw file content (binary-safe) for a non-native file (PDF, docx,
/// pptx, txt, md, ...) and write it to `out` (a file path) or stdout. Uses the
/// read-only token.
pub async fn run(file_id: &str, out: Option<&str>) -> Result<()> {
    let (client, access_token) = drive_client_read().await?;

    let url = format!(
        "https://www.googleapis.com/drive/v3/files/{}?alt=media&supportsAllDrives=true",
        file_id
    );

    let resp = client
        .get(&url)
        .bearer_auth(&access_token)
        .send()
        .await?;

    if !resp.status().is_success() {
        let status = resp.status();
        let error = resp.text().await.unwrap_or_default();
        anyhow::bail!("Download failed ({}): {}", status, error);
    }

    let bytes = resp.bytes().await?;

    match out {
        Some(path) => {
            std::fs::write(path, &bytes)?;
            eprintln!("DOWNLOADED {} bytes -> {}", bytes.len(), path);
        }
        None => {
            let mut stdout = std::io::stdout();
            stdout.write_all(&bytes)?;
            stdout.flush()?;
        }
    }

    Ok(())
}
