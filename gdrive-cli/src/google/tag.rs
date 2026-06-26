use anyhow::{Context, Result};

use crate::auth::google::drive_client_write;

/// Parse repeated `--set key=value` items into pairs. An empty value is allowed
/// and is sent as an empty string (Drive keeps the key with an empty value).
fn parse_kv(items: &[String]) -> Result<Vec<(String, String)>> {
    let mut out = Vec::with_capacity(items.len());
    for item in items {
        let (k, v) = item
            .split_once('=')
            .with_context(|| format!("invalid --set {item:?} (expected key=value)"))?;
        if k.is_empty() {
            anyhow::bail!("invalid --set {item:?}: empty key");
        }
        out.push((k.to_string(), v.to_string()));
    }
    Ok(out)
}

/// Write app-private `appProperties` (tags) onto a file via files.update.
/// Dry-run by default; mutates Drive only with `execute = true`. Uses the write
/// token. On success the resulting appProperties object is printed to stdout as
/// JSON for machine consumption.
pub async fn run(file_id: &str, set: &[String], execute: bool) -> Result<()> {
    let pairs = parse_kv(set)?;
    if pairs.is_empty() {
        anyhow::bail!("no --set key=value pairs provided");
    }

    if !execute {
        eprintln!("DRY-RUN would set appProperties on {file_id}:");
        for (k, v) in &pairs {
            eprintln!("  {k} = {v}");
        }
        eprintln!("(re-run with --execute to apply)");
        return Ok(());
    }

    let (client, access_token) = drive_client_write().await?;

    let mut props = serde_json::Map::new();
    for (k, v) in &pairs {
        props.insert(k.clone(), serde_json::Value::String(v.clone()));
    }
    let body = serde_json::json!({ "appProperties": props });

    let url = format!(
        "https://www.googleapis.com/drive/v3/files/{}?fields=id,name,appProperties&supportsAllDrives=true",
        file_id
    );

    let resp = client
        .patch(&url)
        .bearer_auth(&access_token)
        .json(&body)
        .send()
        .await?;

    if !resp.status().is_success() {
        let status = resp.status();
        let error = resp.text().await.unwrap_or_default();
        anyhow::bail!("Tag update failed ({}): {}", status, error);
    }

    let json: serde_json::Value = resp.json().await?;
    let name = json["name"].as_str().unwrap_or("?");
    eprintln!("TAGGED {name} ({file_id})");
    println!("{}", serde_json::to_string(&json["appProperties"])?);

    Ok(())
}
