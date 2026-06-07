use anyhow::Result;
use serde::Serialize;
use std::fs::File as FsFile;
use std::io::Write;
use std::time::Instant;

use crate::auth::google::drive_client_read;

#[derive(Serialize)]
struct DriveRecord {
    id: String,
    name: String,
    mime_type: String,
    parents: Vec<String>,
    owners: Vec<String>,
    owned_by_me: bool,
    size: i64,
    created_time: String,
    modified_time: String,
    viewed_by_me_time: Option<String>,
    shared_with_me_time: Option<String>,
    shared: bool,
    trashed: bool,
    web_view_link: Option<String>,
    md5_checksum: Option<String>,
    drive_id: Option<String>,
}

impl From<serde_json::Value> for DriveRecord {
    fn from(f: serde_json::Value) -> Self {
        DriveRecord {
            id: f["id"].as_str().unwrap_or("").to_string(),
            name: f["name"].as_str().unwrap_or("").to_string(),
            mime_type: f["mimeType"].as_str().unwrap_or("").to_string(),
            parents: f["parents"].as_array()
                .map(|a| a.iter().filter_map(|v| v.as_str()).map(String::from).collect())
                .unwrap_or_default(),
            owners: f["owners"].as_array()
                .map(|a| a.iter().filter_map(|v| {
                    v["displayName"].as_str().or(v["emailAddress"].as_str()).map(String::from)
                }).collect())
                .unwrap_or_default(),
            owned_by_me: f["ownedByMe"].as_bool().unwrap_or(false),
            size: f["size"].as_str().and_then(|s| s.parse().ok()).unwrap_or(0),
            created_time: f["createdTime"].as_str().unwrap_or("").to_string(),
            modified_time: f["modifiedTime"].as_str().unwrap_or("").to_string(),
            viewed_by_me_time: f["viewedByMeTime"].as_str().map(String::from),
            shared_with_me_time: f["sharedWithMeTime"].as_str().map(String::from),
            shared: f["shared"].as_bool().unwrap_or(false),
            trashed: f["trashed"].as_bool().unwrap_or(false),
            web_view_link: f["webViewLink"].as_str().map(String::from),
            md5_checksum: f["md5Checksum"].as_str().map(String::from),
            drive_id: f["driveId"].as_str().map(String::from),
        }
    }
}

pub async fn run(out_path: &str, all_drives: bool, _include_trashed: bool) -> Result<()> {
    let (client, access_token) = drive_client_read().await?;
    let t0 = Instant::now();

    let mut page_token: Option<String> = None;
    let mut total = 0;
    let mut pages = 0;

    let out_file = FsFile::create(out_path)?;
    let mut writer = std::io::BufWriter::new(out_file);

    loop {
        let mut url = "https://www.googleapis.com/drive/v3/files?pageSize=100&fields=nextPageToken,files(id,name,mimeType,parents,owners,ownedByMe,size,createdTime,modifiedTime,viewedByMeTime,sharedWithMeTime,shared,trashed,webViewLink,md5Checksum,driveId)".to_string();
        
        if let Some(ref token) = page_token {
            url.push_str(&format!("&pageToken={}", token));
        }
        
        if all_drives {
            url.push_str("&includeItemsFromAllDrives=true&supportsAllDrives=true");
        }

        let response = client
            .get(&url)
            .bearer_auth(&access_token)
            .send()
            .await?;

        if !response.status().is_success() {
            let error = response.text().await?;
            anyhow::bail!("API error: {}", error);
        }

        let json: serde_json::Value = response.json().await?;
        
        let files = json["files"].as_array();
        if files.is_none() || files.unwrap().is_empty() {
            break;
        }

        for file in files.unwrap().clone() {
            let rec: DriveRecord = file.into();
            let json = serde_json::to_string(&rec)?;
            writeln!(writer, "{}", json)?;
            total += 1;
        }

        pages += 1;
        if pages % 10 == 0 {
            eprintln!(
                "{} pages, {} files, {}s",
                pages,
                total,
                t0.elapsed().as_secs()
            );
        }

        page_token = json["nextPageToken"].as_str().map(String::from);
        if page_token.is_none() {
            break;
        }
    }

    eprintln!(
        "done: {} files in {} pages, {}s",
        total,
        pages,
        t0.elapsed().as_secs()
    );

    Ok(())
}