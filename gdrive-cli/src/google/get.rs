use anyhow::Result;

use crate::auth::google::drive_client_read;

/// Read a file's id, name, mimeType, and app-private `appProperties`, printing
/// the JSON to stdout. Useful for inspecting tags written by `tag`. Uses the
/// read-only token (appProperties are visible to the same OAuth client).
pub async fn run(file_id: &str) -> Result<()> {
    let (client, access_token) = drive_client_read().await?;

    let url = format!(
        "https://www.googleapis.com/drive/v3/files/{}?fields=id,name,mimeType,appProperties&supportsAllDrives=true",
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
        anyhow::bail!("Get failed ({}): {}", status, error);
    }

    let json: serde_json::Value = resp.json().await?;
    println!("{}", serde_json::to_string_pretty(&json)?);

    Ok(())
}
