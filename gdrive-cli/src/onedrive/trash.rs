use anyhow::Result;

pub async fn run(file_ids: Vec<String>, execute: bool) -> Result<()> {
    let (client, access_token) = crate::auth::onedrive::graph_client().await?;

    for fid in file_ids {
        let url = format!(
            "{}/me/drive/items/{}?fields=id,name,size,deleted",
            crate::auth::onedrive::GRAPH_BASE,
            fid
        );
        
        let resp = client
            .get(&url)
            .header("Authorization", format!("Bearer {}", access_token))
            .send()
            .await?;

        if !resp.status().is_success() {
            let error = resp.text().await?;
            eprintln!("ERROR {}: {}", fid, error);
            continue;
        }

        let json: serde_json::Value = resp.json().await?;
        let name = json["name"].as_str().unwrap_or("?").to_string();
        let size = json["size"].as_i64().unwrap_or(0);
        let deleted = json["deleted"].as_object().is_some();

        if deleted {
            eprintln!("SKIP (already trashed)  {:.1} MB  {}", size as f64 / 1e6, name);
            continue;
        }

        if !execute {
            eprintln!("DRY-RUN would trash     {:.1} MB  {}", size as f64 / 1e6, name);
            continue;
        }

        let body = serde_json::json!({"deleted": {}});
        let update_url = format!("{}/me/drive/items/{}", crate::auth::onedrive::GRAPH_BASE, fid);
        
        match client
            .patch(&update_url)
            .header("Authorization", format!("Bearer {}", access_token))
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