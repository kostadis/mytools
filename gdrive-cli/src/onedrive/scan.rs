use anyhow::{Context, Result};
use serde::Deserialize;
use serde::Serialize;
use std::fs::File;
use std::io::Write;
use std::time::Instant;

use crate::auth::onedrive::{graph_get, get_credentials, GRAPH_BASE};

#[derive(Serialize, Deserialize)]
struct DriveRecord {
    #[serde(rename = "id")]
    id: String,
    #[serde(rename = "name")]
    name: String,
    #[serde(rename = "file")]
    file: Option<FileInfo>,
    #[serde(rename = "folder")]
    folder: Option<FolderInfo>,
    #[serde(rename = "parentReference")]
    parent: Option<ParentRef>,
    #[serde(rename = "createdDateTime")]
    created_time: Option<String>,
    #[serde(rename = "lastModifiedDateTime")]
    modified_time: Option<String>,
    #[serde(rename = "createdBy")]
    created_by: Option<CreatedBy>,
    #[serde(rename = "lastModifiedBy")]
    modified_by: Option<ModifiedBy>,
    #[serde(rename = "deleted")]
    deleted: Option<bool>,
    #[serde(rename = "size")]
    size: Option<i64>,
    #[serde(rename = "webUrl")]
    web_url: Option<String>,
    #[serde(rename = "shared")]
    shared: Option<bool>,
}

#[derive(Serialize, Deserialize)]
struct FileInfo {
    #[serde(rename = "mimeType")]
    mime_type: Option<String>,
    #[serde(rename = "hashes")]
    hashes: Option<Hashes>,
}

#[derive(Serialize, Deserialize)]
struct FolderInfo {
    #[serde(rename = "childCount")]
    child_count: Option<i32>,
}

#[derive(Serialize, Deserialize)]
struct Hashes {
    #[serde(rename = "sha1Hash")]
    sha1: Option<String>,
    #[serde(rename = "quickXorHash")]
    quickxor: Option<String>,
}

#[derive(Serialize, Deserialize)]
struct ParentRef {
    #[serde(rename = "id")]
    id: Option<String>,
    #[serde(rename = "path")]
    path: Option<String>,
    #[serde(rename = "driveId")]
    drive_id: Option<String>,
}

#[derive(Serialize, Deserialize)]
struct CreatedBy {
    #[serde(rename = "user")]
    user: Option<UserInfo>,
}

#[derive(Serialize, Deserialize)]
struct ModifiedBy {
    #[serde(rename = "user")]
    user: Option<UserInfo>,
}

#[derive(Serialize, Deserialize)]
struct UserInfo {
    #[serde(rename = "displayName")]
    display_name: Option<String>,
    #[serde(rename = "email")]
    email: Option<String>,
}

fn normalize_record(rec: DriveRecord) -> serde_json::Value {
    let DriveRecord {
        id,
        name,
        file,
        folder,
        parent,
        created_time,
        modified_time,
        created_by,
        modified_by,
        deleted,
        size,
        web_url,
        shared,
    } = rec;

    let mime_type = file.as_ref().and_then(|f| f.mime_type.clone());
    let sha1 = file.as_ref().and_then(|f| f.hashes.as_ref().and_then(|h| h.sha1.clone()));
    let quickxor = file.as_ref().and_then(|f| f.hashes.as_ref().and_then(|h| h.quickxor.clone()));
    let child_count = folder.and_then(|f| f.child_count);
    let owner = created_by.and_then(|c| c.user).and_then(|u| {
        u.display_name.or(u.email)
    });
    let modifier = modified_by.and_then(|m| m.user).and_then(|u| {
        u.display_name.or(u.email)
    });
    let parent_id = parent.as_ref().and_then(|p| p.id.clone());
    let parent_path = parent.as_ref().and_then(|p| p.path.clone());
    let drive_id = parent.as_ref().and_then(|p| p.drive_id.clone());

    serde_json::json!({
        "id": id,
        "name": name,
        "mime_type": mime_type,
        "sha1": sha1,
        "quickxor": quickxor,
        "child_count": child_count,
        "parents": if let Some(pid) = parent_id { vec![pid] } else { vec![] },
        "parent_path": parent_path,
        "drive_id": drive_id,
        "owner": owner,
        "modifier": modifier,
        "created_time": created_time,
        "modified_time": modified_time,
        "deleted": deleted,
        "size": size,
        "web_url": web_url,
        "shared": shared,
    })
}

pub async fn run(out_path: &str, include_trashed: bool) -> Result<()> {
    let token = get_credentials().await?;
    let t0 = Instant::now();

    let _filter = if include_trashed {
        None
    } else {
        Some("deleted eq null".to_string())
    };

    let mut page_url = format!(
        "{}/me/drive/root/children?$select=id,name,file,folder,parentReference,\
         createdDateTime,lastModifiedDateTime,createdBy,lastModifiedBy,\
         deleted,size,webUrl,shared&$top=200",
        GRAPH_BASE
    );

    let out_file = File::create(out_path)?;
    let mut writer = std::io::BufWriter::new(out_file);

    let mut total = 0;

    loop {
        let resp = graph_get(&page_url, &token.access_token).await?;
        let resp = resp.error_for_status().context("Graph API error")?;

        #[derive(Deserialize)]
        struct Page {
            #[serde(rename = "value")]
            value: Vec<DriveRecord>,
            #[serde(rename = "@odata.nextLink")]
            next_link: Option<String>,
        }

        let page: Page = resp.json().await.context("Failed to parse response")?;

        for rec in page.value {
            let normalized = normalize_record(rec);
            let json = serde_json::to_string(&normalized)?;
            writeln!(writer, "{}", json)?;
            total += 1;
        }

        page_url = match page.next_link {
            Some(url) => url,
            None => break,
        };
    }

    eprintln!("done: {} files in {}s", total, t0.elapsed().as_secs());
    Ok(())
}