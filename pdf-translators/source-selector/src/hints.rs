use crate::{Result, SelectionError, models::*};
use serde_json::Value;
use std::{
    collections::BTreeMap,
    fs,
    path::{Component, Path},
};

pub fn read_muse(
    csv_path: &Path,
    sources: &[Source],
    twins_path: Option<&Path>,
) -> Result<Vec<Hint>> {
    let mut out = vec![];
    for row in csv::Reader::from_path(csv_path)?.deserialize::<BTreeMap<String, String>>() {
        let row = row?;
        let publisher = row.get("publisher").map(String::as_str).unwrap_or("");
        let folder = row.get("product_folder").map(String::as_str).unwrap_or("");
        let mut names = vec![row.get("canonical_file").cloned().unwrap_or_default()];
        names.extend(
            row.get("duplicate_files")
                .into_iter()
                .flat_map(|s| s.split(';'))
                .map(|s| s.trim().to_string()),
        );
        let mut ids = vec![];
        let mut missing = vec![];
        for name in names.into_iter().filter(|s| !s.is_empty()) {
            let matches: Vec<_> = sources
                .iter()
                .filter(|s| {
                    s.publisher == publisher
                        && s.product_folder == folder
                        && s.relative_path
                            .file_name()
                            .is_some_and(|v| v == name.as_str())
                })
                .collect();
            if matches.is_empty() {
                missing.push(format!("{publisher}/{folder}/{name}"));
            }
            ids.extend(matches.into_iter().map(|s| s.source_id.clone()));
        }
        ids.sort();
        ids.dedup();
        out.push(Hint {
            origin: "muse".into(),
            source_ids: ids,
            payload: serde_json::to_value(row)?,
            unmatched_references: missing,
        });
    }
    if let Some(path) = twins_path {
        let pairs: Vec<Value> = serde_json::from_slice(&fs::read(path)?)?;
        for pair in pairs {
            let publisher = pair["publisher"].as_str().unwrap_or("");
            let folders = pair["folders"]
                .as_array()
                .ok_or_else(|| SelectionError::Invalid("twin hint needs folders array".into()))?;
            let ids = sources
                .iter()
                .filter(|s| {
                    s.publisher == publisher
                        && folders
                            .iter()
                            .any(|f| f.as_str() == Some(&s.product_folder))
                })
                .map(|s| s.source_id.clone())
                .collect();
            out.push(Hint {
                origin: "muse".into(),
                source_ids: ids,
                payload: pair,
                unmatched_references: vec![],
            });
        }
    }
    Ok(out)
}

pub fn read_rpglib(json_path: &Path, sources: &[Source]) -> Result<Vec<Hint>> {
    let value: Value = serde_json::from_slice(&fs::read(json_path)?)?;
    let rows = value
        .as_array()
        .or_else(|| value.get("books").and_then(Value::as_array))
        .or_else(|| value.get("items").and_then(Value::as_array))
        .ok_or_else(|| {
            SelectionError::Invalid("rpg-lib snapshot needs array, books, or items".into())
        })?;
    let mut out = vec![];
    for row in rows {
        let name = row["filepath"].as_str().unwrap_or("");
        let path = Path::new(name);
        let ids = if path.components().any(|p| matches!(p, Component::ParentDir)) {
            vec![]
        } else {
            sources
                .iter()
                .filter(|s| {
                    if path.is_absolute() {
                        s.metadata
                            .get("inventory_root")
                            .and_then(Value::as_str)
                            .is_some_and(|root| Path::new(root).join(&s.relative_path) == path)
                    } else {
                        path == s.relative_path
                    }
                })
                .map(|s| s.source_id.clone())
                .collect::<Vec<_>>()
        };
        out.push(Hint {
            origin: "rpglib".into(),
            unmatched_references: if ids.len() == 1 {
                vec![]
            } else {
                vec![name.into()]
            },
            source_ids: if ids.len() == 1 { ids } else { vec![] },
            payload: row.clone(),
        });
    }
    Ok(out)
}

pub fn legacy_hints(root: &Path, sources: &[Source]) -> Vec<Hint> {
    let mut hints = vec![];
    for source in sources {
        let parent = source.relative_path.parent().unwrap_or(Path::new(""));
        if let Ok(text) = fs::read_to_string(root.join(parent).join(".extract_skip")) {
            let name = source
                .relative_path
                .file_name()
                .unwrap_or_default()
                .to_string_lossy();
            for line in text
                .lines()
                .filter(|l| l.split('#').next().unwrap_or("").trim() == name)
            {
                hints.push(Hint {
                    origin: "legacy_skip".into(),
                    source_ids: vec![source.source_id.clone()],
                    payload: serde_json::json!({"line":line}),
                    unmatched_references: vec![],
                });
            }
        }
    }
    hints
}
