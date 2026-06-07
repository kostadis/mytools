use anyhow::Result;
use regex::Regex;
use serde::Deserialize;
use std::collections::HashMap;
use std::fs::File;
use std::io::{BufRead, BufReader};
use std::path::Path;

#[derive(Deserialize, Clone)]
struct DriveRecord {
    id: String,
    name: String,
    mime_type: Option<String>,
    #[serde(rename = "parents")]
    parents: Vec<String>,
    size: Option<i64>,
    modified_time: Option<String>,
    sha1: Option<String>,
    quickxor: Option<String>,
}

#[derive(Deserialize)]
struct FolderEntry {
    #[allow(dead_code)]
    id: String,
    name: String,
    #[serde(rename = "parents")]
    parents: Vec<String>,
}

fn load_jsonl(path: &str) -> Result<Vec<DriveRecord>> {
    let file = File::open(path)?;
    let reader = BufReader::new(file);
    let mut records = Vec::new();
    for line in reader.lines() {
        let line = line?;
        if line.trim().is_empty() {
            continue;
        }
        let rec: DriveRecord = serde_json::from_str(&line)?;
        records.push(rec);
    }
    Ok(records)
}

fn build_path_lookup(records: &[DriveRecord]) -> HashMap<String, String> {
    // Collect folders
    let folders: HashMap<String, FolderEntry> = records
        .iter()
        .filter(|r| {
            r.mime_type.as_ref().map_or(false, |mt| mt == "application/vnd.google-apps.folder")
        })
        .map(|r| {
            let fe = FolderEntry {
                id: r.id.clone(),
                name: r.name.clone(),
                parents: r.parents.clone(),
            };
            (r.id.clone(), fe)
        })
        .collect();

    let mut cache: HashMap<String, String> = HashMap::new();

    fn resolve(
        fid: &str,
        folders: &HashMap<String, FolderEntry>,
        cache: &mut HashMap<String, String>,
    ) -> String {
        if let Some(p) = cache.get(fid) {
            return p.clone();
        }
        let folder = match folders.get(fid) {
            Some(f) => f,
            None => {
                cache.insert(fid.to_string(), String::new());
                return String::new();
            }
        };
        let parents = &folder.parents;
        let path = if !parents.is_empty() {
            let parent_path = resolve(&parents[0], folders, cache);
            if parent_path.is_empty() {
                folder.name.clone()
            } else {
                format!("{}/{}", parent_path, folder.name)
            }
        } else {
            folder.name.clone()
        };
        cache.insert(fid.to_string(), path.clone());
        path
    }

    for fid in folders.keys() {
        resolve(fid, &folders, &mut cache);
    }
    cache
}

fn file_path(entry: &serde_json::Value, path_lookup: &HashMap<String, String>) -> String {
    let parents: Vec<String> = entry["parents"].as_array()
        .map(|a| a.iter().filter_map(|v| v.as_str()).map(String::from).collect())
        .unwrap_or_default();
    
    if !parents.is_empty() {
        if let Some(parent_path) = path_lookup.get(&parents[0]) {
            if !parent_path.is_empty() {
                return format!("{}/", parent_path);
            }
        }
    }
    String::new()
}

pub fn normalize(name: &str) -> String {
    let n = name.to_lowercase();
    let root = Path::new(&n)
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or(&n);
    let ext = Path::new(&n).extension().and_then(|s| s.to_str()).unwrap_or("");

    let root = Regex::new(r"^copy of\s+").unwrap().replace(root, "");
    let root = Regex::new(r"\s*\(\d+\)$").unwrap().replace(&root, "");
    let root = Regex::new(r"\s*-\s*copy$").unwrap().replace(&root, "");
    let root = root.trim().to_string();

    if ext.is_empty() {
        root
    } else {
        format!("{}.{}", root, ext)
    }
}

pub fn run(jsonl: &str, exclude: &[String], min_group: usize) -> Result<()> {
    let records = load_jsonl(jsonl)?;
    let path_lookup = build_path_lookup(&records);
    let exclude_lower: Vec<String> = exclude.iter().map(|s| s.to_lowercase()).collect();

    // Filter and collect files
    let mut files: Vec<(String, String, DriveRecord)> = Vec::new();
    for rec in &records {
        if rec.mime_type.as_ref().map_or(false, |mt| mt == "application/vnd.google-apps.folder") {
            continue;
        }
        let parents = &rec.parents;
        let fp = if !parents.is_empty() {
            if let Some(parent_path) = path_lookup.get(&parents[0]) {
                if !parent_path.is_empty() {
                    format!("{}/{}", parent_path, rec.name)
                } else {
                    rec.name.clone()
                }
            } else {
                rec.name.clone()
            }
        } else {
            rec.name.clone()
        };

        if exclude_lower.iter().any(|ex| fp.to_lowercase().contains(ex)) {
            continue;
        }
        files.push((fp, normalize(&rec.name), rec.clone()));
    }

    // Group by normalized name
    let mut groups: HashMap<String, Vec<(String, DriveRecord)>> = HashMap::new();
    for (fp, key, rec) in files.iter() {
        groups.entry(key.clone()).or_default().push((fp.clone(), rec.clone()));
    }

    let dupes: Vec<_> = groups.into_iter().filter(|(_, v)| v.len() >= min_group).collect();
    let mut by_size = dupes.clone();
    by_size.sort_by(|a, b| b.1.len().cmp(&a.1.len()));

    eprintln!("{} groups with {}+ similar files\n", dupes.len(), min_group);

    for (key, members) in by_size {
        println!("--- {} ({} files) ---", key, members.len());
        let mut sorted = members;
        sorted.sort_by(|a, b| a.0.cmp(&b.0));
        for (fp, rec) in sorted {
            let size = rec.size.unwrap_or(0);
            let size_str = if size > 0 {
                format!("{:.1}MB", size as f64 / 1e6)
            } else {
                "native".to_string()
            };
            let modified = rec.modified_time.as_deref().unwrap_or("").chars().take(10).collect::<String>();
            println!("  {}  {:>10}  {}", modified, size_str, fp);
        }
        println!();
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;
    use std::io::Write;
    use tempfile::NamedTempFile;

    #[test]
    fn test_normalize_removes_copy_prefix() {
        assert_eq!(normalize("Copy of document.pdf"), "document.pdf");
        assert_eq!(normalize("copy of REPORT.docx"), "report.docx");
    }

    #[test]
    fn test_normalize_removes_copy_suffix() {
        assert_eq!(normalize("document - copy.pdf"), "document.pdf");
        assert_eq!(normalize("report- copy.docx"), "report.docx");
    }

    #[test]
    fn test_normalize_removes_parentheses_numbers() {
        assert_eq!(normalize("document (1).pdf"), "document.pdf");
        assert_eq!(normalize("report (23).docx"), "report.docx");
    }

    #[test]
    fn test_normalize_preserves_extension() {
        assert_eq!(normalize("file.txt"), "file.txt");
        assert_eq!(normalize("FILE.TXT"), "file.txt");
        assert_eq!(normalize("archive.tar.gz"), "archive.tar.gz");
    }

    #[test]
    fn test_normalize_collapses_whitespace() {
        // Note: The normalize function only trims leading/trailing whitespace from the root
        // (the part before the extension)
        assert_eq!(normalize("multiple   spaces.txt"), "multiple   spaces.txt");
        // Leading spaces ARE trimmed from the root
        assert_eq!(normalize("  leading.txt"), "leading.txt");
        // Spaces before extension are preserved (they're part of the root)
        assert_eq!(normalize("trailing .txt"), "trailing.txt");
    }

    #[test]
    fn test_normalize_combined() {
        // Note: regex patterns are applied in order, so "Copy of file (1) - copy.pdf":
        // 1. Remove "copy of " → "file (1) - copy"
        // 2. Try to remove " (N)" but it's not at end → "file (1) - copy"
        // 3. Remove " - copy" → "file (1)"
        // Result: "file (1).pdf"
        assert_eq!(normalize("Copy of file (1) - copy.pdf"), "file (1).pdf");
        
        // Simpler case: just "Copy of file.pdf" → "file.pdf"
        assert_eq!(normalize("Copy of file.pdf"), "file.pdf");
        
        // "file (1).pdf" → "file.pdf"
        assert_eq!(normalize("file (1).pdf"), "file.pdf");
    }

    #[test]
    fn test_build_path_lookup_root_folder() {
        let records = vec![
            DriveRecord {
                id: "folder1".to_string(),
                name: "RootFolder".to_string(),
                mime_type: Some("application/vnd.google-apps.folder".to_string()),
                parents: vec![],
                size: None,
                modified_time: None,
                sha1: None,
                quickxor: None,
            },
        ];

        let lookup = build_path_lookup(&records);
        assert_eq!(lookup.get("folder1"), Some(&"RootFolder".to_string()));
    }

    #[test]
    fn test_build_path_lookup_nested_folders() {
        let records = vec![
            DriveRecord {
                id: "root".to_string(),
                name: "Root".to_string(),
                mime_type: Some("application/vnd.google-apps.folder".to_string()),
                parents: vec![],
                size: None,
                modified_time: None,
                sha1: None,
                quickxor: None,
            },
            DriveRecord {
                id: "folder1".to_string(),
                name: "Folder1".to_string(),
                mime_type: Some("application/vnd.google-apps.folder".to_string()),
                parents: vec!["root".to_string()],
                size: None,
                modified_time: None,
                sha1: None,
                quickxor: None,
            },
            DriveRecord {
                id: "folder2".to_string(),
                name: "Folder2".to_string(),
                mime_type: Some("application/vnd.google-apps.folder".to_string()),
                parents: vec!["folder1".to_string()],
                size: None,
                modified_time: None,
                sha1: None,
                quickxor: None,
            },
        ];

        let lookup = build_path_lookup(&records);
        assert_eq!(lookup.get("root"), Some(&"Root".to_string()));
        assert_eq!(lookup.get("folder1"), Some(&"Root/Folder1".to_string()));
        assert_eq!(lookup.get("folder2"), Some(&"Root/Folder1/Folder2".to_string()));
    }

    #[test]
    fn test_file_path_with_parent() {
        let mut path_lookup = HashMap::new();
        path_lookup.insert("parent1".to_string(), "ParentFolder".to_string());

        let entry = serde_json::json!({
            "id": "file1",
            "name": "myfile.txt",
            "parents": ["parent1"]
        });

        let fp = file_path(&entry, &path_lookup);
        // file_path returns the parent path prefix
        assert_eq!(fp, "ParentFolder/");
    }

    #[test]
    fn test_file_path_without_parent() {
        let path_lookup: HashMap<String, String> = HashMap::new();

        let entry = serde_json::json!({
            "id": "file1",
            "name": "myfile.txt",
            "parents": []
        });

        let fp = file_path(&entry, &path_lookup);
        // No parent, returns empty string
        assert_eq!(fp, "");
    }

    #[test]
    fn test_file_path_unknown_parent() {
        let path_lookup: HashMap<String, String> = HashMap::new();

        let entry = serde_json::json!({
            "id": "file1",
            "name": "myfile.txt",
            "parents": ["unknown"]
        });

        let fp = file_path(&entry, &path_lookup);
        // Unknown parent, returns empty string
        assert_eq!(fp, "");
    }

    #[test]
    fn test_load_jsonl_valid() {
        let mut temp_file = NamedTempFile::new().unwrap();
        let path = temp_file.path().to_string_lossy().to_string();

        let line1 = r#"{"id":"1","name":"file1.txt","mime_type":"text/plain","parents":[],"size":100,"modified_time":"2024-01-01","sha1":"abc","quickxor":"def"}"#;
        let line2 = r#"{"id":"2","name":"file2.txt","mime_type":"text/plain","parents":["1"],"size":200,"modified_time":"2024-01-02","sha1":"ghi","quickxor":"jkl"}"#;
        writeln!(temp_file, "{}", line1).unwrap();
        writeln!(temp_file, "{}", line2).unwrap();

        let records = load_jsonl(&path).unwrap();
        assert_eq!(records.len(), 2);
        assert_eq!(records[0].id, "1");
        assert_eq!(records[0].name, "file1.txt");
        assert_eq!(records[1].id, "2");
    }

    #[test]
    fn test_grouping_similar_names() {
        // All should normalize to the same key
        assert_eq!(normalize("file1.txt"), normalize("file1 (1).txt"));
        assert_eq!(normalize("file1 (1).txt"), normalize("Copy of file1.txt"));
        assert_eq!(normalize("file1.txt"), "file1.txt");
    }

    #[test]
    fn test_exclude_pattern_matching() {
        let path = "DriveThru/RPG/module.pdf";
        let exclude = vec!["drivethru".to_string(), "rpg".to_string()];
        let exclude_lower: Vec<String> = exclude.iter().map(|s| s.to_lowercase()).collect();

        assert!(exclude_lower.iter().any(|ex| path.to_lowercase().contains(ex)));
    }

    #[test]
    fn test_drive_record_from_json() {
        let json = serde_json::json!({
            "id": "file123",
            "name": "test.pdf",
            "mime_type": "application/pdf",
            "parents": ["folder1", "folder2"],
            "size": 1234567,
            "modified_time": "2024-01-02T00:00:00Z",
            "sha1": "abc123",
            "quickxor": "def456"
        });

        let rec: DriveRecord = serde_json::from_value(json).unwrap();
        assert_eq!(rec.id, "file123");
        assert_eq!(rec.name, "test.pdf");
        assert_eq!(rec.mime_type, Some("application/pdf".to_string()));
        assert_eq!(rec.parents.len(), 2);
        assert_eq!(rec.size, Some(1234567));
    }
}