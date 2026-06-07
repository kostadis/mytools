use anyhow::Result;

pub async fn run(file_ids: Vec<String>, execute: bool) -> Result<()> {
    let (client, access_token) = crate::auth::google::drive_client_write().await?;

    for fid in file_ids {
        let url = format!(
            "https://www.googleapis.com/drive/v3/files/{}?fields=id,name,size,trashed",
            fid
        );
        
        let resp = client
            .get(&url)
            .bearer_auth(&access_token)
            .send()
            .await?;

        if !resp.status().is_success() {
            let error = resp.text().await?;
            eprintln!("ERROR {}: {}", fid, error);
            continue;
        }

        let json: serde_json::Value = resp.json().await?;
        let name = json["name"].as_str().unwrap_or("?").to_string();
        let size = json["size"].as_str().and_then(|s| s.parse().ok()).unwrap_or(0);
        let trashed = json["trashed"].as_bool().unwrap_or(false);

        if trashed {
            eprintln!("SKIP (already trashed)  {:.1} MB  {}", size as f64 / 1e6, name);
            continue;
        }

        if !execute {
            eprintln!("DRY-RUN would trash     {:.1} MB  {}", size as f64 / 1e6, name);
            continue;
        }

        let body = serde_json::json!({"trashed": true});
        let update_url = format!("https://www.googleapis.com/drive/v3/files/{}", fid);
        
        match client
            .patch(&update_url)
            .bearer_auth(&access_token)
            .json(&body)
            .send()
            .await
        {
            Ok(_) => eprintln!("TRASHED                 {:.1} MB  {}", size as f64 / 1e6, name),
            Err(e) => eprintln!("ERROR trashing {}: {}", name, e),
        }
    }

    Ok(())
}
