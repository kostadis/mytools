use anyhow::Result;
use reqwest::Client;

const FOLDER_MIME: &str = "application/vnd.google-apps.folder";

pub async fn run(
    file_ids: Vec<String>,
    to: &str,
    create_folder: bool,
    execute: bool,
) -> Result<()> {
    let (client, access_token) = crate::auth::google::drive_client_write().await?;

    if create_folder {
        let dest_id = ensure_folder_path(&client, &access_token, to, execute).await?;
        if dest_id.is_none() {
            eprintln!("\nDRY-RUN: would move {} files into {}/", file_ids.len(), to);
            for fid in &file_ids {
                match get_file_info(&client, &access_token, fid).await {
                    Ok(meta) => {
                        let size = meta.size.unwrap_or(0);
                        eprintln!("  DRY-RUN would move  {:8.1} MB  {}", size as f64 / 1e6, meta.name);
                    }
                    Err(e) => eprintln!("  ERROR {}: {}", fid, e),
                }
            }
            return Ok(());
        } else {
            move_files(&client, &access_token, &file_ids, &dest_id.unwrap(), execute).await?;
        }
    } else {
        move_files(&client, &access_token, &file_ids, to, execute).await?;
    }

    Ok(())
}

struct FileInfo {
    #[allow(dead_code)]
    id: String,
    name: String,
    size: Option<i64>,
    parents: Vec<String>,
    owned_by_me: bool,
    capabilities: Capabilities,
}

struct Capabilities {
    can_move_item_within_drive: bool,
    can_copy: bool,
}

async fn get_file_info(client: &Client, access_token: &str, fid: &str) -> Result<FileInfo> {
    let url = format!("https://www.googleapis.com/drive/v3/files/{}?fields=id,name,size,parents,ownedByMe,capabilities", fid);
    
    let resp = client
        .get(&url)
        .bearer_auth(access_token)
        .send()
        .await?;
    
    if !resp.status().is_success() {
        let error = resp.text().await?;
        anyhow::bail!("API error: {}", error);
    }
    
    let json: serde_json::Value = resp.json().await?;
    
    let capabilities = json["capabilities"].as_object().map(|caps| {
        Capabilities {
            can_move_item_within_drive: caps.get("canMoveItemWithinDrive").and_then(|v| v.as_bool()).unwrap_or(false),
            can_copy: caps.get("canCopy").and_then(|v| v.as_bool()).unwrap_or(false),
        }
    }).unwrap_or(Capabilities {
        can_move_item_within_drive: false,
        can_copy: false,
    });
    
    Ok(FileInfo {
        id: json["id"].as_str().unwrap_or("").to_string(),
        name: json["name"].as_str().unwrap_or("?").to_string(),
        size: json["size"].as_str().and_then(|s| s.parse().ok()),
        parents: json["parents"].as_array()
            .map(|a| a.iter().filter_map(|v| v.as_str().map(String::from)).collect())
            .unwrap_or_default(),
        owned_by_me: json["ownedByMe"].as_bool().unwrap_or(true),
        capabilities,
    })
}

async fn ensure_folder_path(client: &Client, access_token: &str, path: &str, execute: bool) -> Result<Option<String>> {
    let parts: Vec<&str> = path.split('/').filter(|p| !p.is_empty()).collect();
    let mut parent_id = "root".to_string();

    for part in parts {
        let query = format!(
            "name = '{}' and '{}' in parents and mimeType = '{}' and trashed = false",
            part.replace('\'', "\\'"),
            parent_id,
            FOLDER_MIME
        );

        let url = format!(
            "https://www.googleapis.com/drive/v3/files?q={}&fields=files(id,name)&pageSize=1",
            urlencoding::encode(&query)
        );

        let resp = client
            .get(&url)
            .bearer_auth(access_token)
            .send()
            .await?;

        let json: serde_json::Value = resp.json().await?;
        let files = json["files"].as_array().cloned().unwrap_or_default();
        
        if !files.is_empty() {
            parent_id = files[0]["id"].as_str().unwrap().to_string();
            eprintln!("FOLDER EXISTS  {}/ (id: {})", part, parent_id);
        } else if execute {
            let body = serde_json::json!({
                "name": part,
                "mimeType": FOLDER_MIME,
                "parents": [parent_id]
            });

            let url = "https://www.googleapis.com/drive/v3/files?fields=id";
            let resp = client
                .post(url)
                .bearer_auth(access_token)
                .json(&body)
                .send()
                .await?;

            if !resp.status().is_success() {
                let error = resp.text().await?;
                anyhow::bail!("Failed to create folder: {}", error);
            }

            let json: serde_json::Value = resp.json().await?;
            parent_id = json["id"].as_str().unwrap().to_string();
            eprintln!("FOLDER CREATED {}/ (id: {})", part, parent_id);
        } else {
            eprintln!("DRY-RUN would create folder {}/ under {}", part, parent_id);
            return Ok(None);
        }
    }

    Ok(Some(parent_id))
}

async fn move_files(client: &Client, access_token: &str, file_ids: &[String], dest_id: &str, execute: bool) -> Result<()> {
    // Get root ID
    let root_url = "https://www.googleapis.com/drive/v3/files/root?fields=id";
    let resp = client
        .get(root_url)
        .bearer_auth(access_token)
        .send()
        .await?;
    let root_json: serde_json::Value = resp.json().await?;
    let root_id = root_json["id"].as_str().unwrap_or("root").to_string();

    for fid in file_ids {
        let info = match get_file_info(client, access_token, fid).await {
            Ok(info) => info,
            Err(e) => {
                eprintln!("ERROR {}: {}", fid, e);
                continue;
            }
        };

        let name = info.name;
        let size = info.size.unwrap_or(0);
        let owned = info.owned_by_me;
        let current_parents = info.parents;
        let can_move = info.capabilities.can_move_item_within_drive || owned;
        let need_copy = !can_move && info.capabilities.can_copy;

        if !execute {
            let method = if need_copy { "copy+remove" } else { "move" };
            eprintln!("DRY-RUN would {:12}  {:8.1} MB  {}", method, size as f64 / 1e6, name);
            continue;
        }

        if need_copy {
            // Copy the file to destination
            let body = serde_json::json!({
                "name": name,
                "parents": [dest_id]
            });

            let copy_url = format!("https://www.googleapis.com/drive/v3/files/{}?fields=id", fid);
            let resp = client
                .post(&copy_url)
                .bearer_auth(access_token)
                .json(&body)
                .send()
                .await?;

            if !resp.status().is_success() {
                let error = resp.text().await?;
                eprintln!("ERROR copying {}: {}", name, error);
                continue;
            }

            let copy_json: serde_json::Value = resp.json().await?;
            let new_id = copy_json["id"].as_str().unwrap();
            eprintln!("COPIED          {:8.1} MB  {}  (new id: {})", size as f64 / 1e6, name, new_id);

            // Remove from original parent(s)
            let remove_parents = if current_parents.is_empty() {
                root_id.clone()
            } else {
                current_parents.join(",")
            };

            let update_body = serde_json::json!({});
            let update_url = format!(
                "https://www.googleapis.com/drive/v3/files/{}?removeParents={}",
                fid, remove_parents
            );
            
            let _resp = client
                .patch(&update_url)
                .bearer_auth(access_token)
                .json(&update_body)
                .send()
                .await?;

            eprintln!("REMOVED ORIGINAL from Drive view: {}", name);
        } else {
            // Direct move
            let remove_parents = if current_parents.is_empty() {
                root_id.clone()
            } else {
                current_parents.join(",")
            };

            let update_body = serde_json::json!({});
            let update_url = format!(
                "https://www.googleapis.com/drive/v3/files/{}?addParents={}&removeParents={}",
                fid, dest_id, remove_parents
            );
            
            let _resp = client
                .patch(&update_url)
                .bearer_auth(access_token)
                .json(&update_body)
                .send()
                .await?;

            eprintln!("MOVED           {:8.1} MB  {}", size as f64 / 1e6, name);
        }
    }

    Ok(())
}
