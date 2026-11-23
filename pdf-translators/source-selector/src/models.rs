use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{collections::BTreeMap, path::PathBuf};

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum SourceKind {
    Pdf,
    Archive,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct Fingerprint {
    pub size: u64,
    pub mtime_ns: Option<u128>,
    pub ctime_ns: Option<i128>,
    pub device: Option<u64>,
    pub inode: Option<u64>,
    pub sha256: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Source {
    pub source_id: String,
    #[serde(with = "path_serde")]
    pub relative_path: PathBuf,
    pub kind: SourceKind,
    pub publisher: String,
    pub product_folder: String,
    pub fingerprint: Fingerprint,
    pub read_error: Option<String>,
    #[serde(default)]
    pub baseline_established: bool,
    #[serde(default)]
    pub artifacts: Vec<String>,
    #[serde(default)]
    pub metadata: BTreeMap<String, Value>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct InventoryResult {
    #[serde(with = "path_serde")]
    pub root: PathBuf,
    pub started: String,
    pub finished: String,
    pub sources: Vec<Source>,
    pub errors: Vec<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Hint {
    pub origin: String,
    pub source_ids: Vec<String>,
    pub payload: Value,
    pub unmatched_references: Vec<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Group {
    pub group_id: String,
    pub source_ids: Vec<String>,
    pub membership_digest: String,
    pub reasons: Vec<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ActorRole {
    Deterministic,
    Reader,
    Sol,
    User,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Claim {
    pub claim_id: String,
    pub kind: String,
    pub value: String,
    pub source_id: String,
    pub page: u32,
    pub quote: String,
    pub actor: String,
    pub role: ActorRole,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct PageText {
    pub page: u32,
    pub text: String,
    pub images: Option<usize>,
    pub annotations: Option<usize>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Evidence {
    pub source_id: String,
    pub sha256: String,
    pub version: u32,
    pub pdf_metadata: BTreeMap<String, Value>,
    pub pages: Vec<PageText>,
    pub page_count: u32,
    pub bookmarks: Value,
    pub errors: Vec<String>,
    pub text_quality: String,
    #[serde(default)]
    pub claims: Vec<Claim>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Status {
    Selected,
    ExactDuplicate,
    EquivalentPresentation,
    Superseded,
    DistinctWork,
    NeedsReview,
    ExcludedAsset,
    Unreadable,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Outcome {
    pub source_id: String,
    pub status: Status,
    pub work_id: Option<String>,
    pub representative_id: Option<String>,
    pub successor_id: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Decision {
    pub group_id: String,
    pub membership_digest: String,
    pub evidence_digest: String,
    pub actor: String,
    pub actor_role: ActorRole,
    pub outcomes: Vec<Outcome>,
    pub rationale: String,
    pub evidence_refs: Vec<String>,
}

/// Preserve Unix filename bytes instead of silently replacing invalid UTF-8.
pub mod path_serde {
    #[cfg(not(unix))]
    use serde::ser::Error as _;
    use serde::{Deserialize, Deserializer, Serializer};
    use std::path::PathBuf;
    pub fn serialize<S: Serializer>(
        path: &std::path::Path,
        serializer: S,
    ) -> Result<S::Ok, S::Error> {
        if let Some(text) = path.to_str() {
            return serializer.serialize_str(text);
        }
        #[cfg(unix)]
        {
            use serde::Serialize;
            use std::os::unix::ffi::OsStrExt;
            let bytes: Vec<u8> = path.as_os_str().as_bytes().to_vec();
            serde_json::json!({"unix_bytes":bytes}).serialize(serializer)
        }
        #[cfg(not(unix))]
        {
            Err(S::Error::custom("unsupported non-UTF-8 path"))
        }
    }
    pub fn deserialize<'de, D: Deserializer<'de>>(deserializer: D) -> Result<PathBuf, D::Error> {
        use serde::de::Error;
        let value = serde_json::Value::deserialize(deserializer)?;
        if let Some(s) = value.as_str() {
            return Ok(PathBuf::from(s));
        }
        #[cfg(unix)]
        {
            use std::os::unix::ffi::OsStringExt;
            let bytes: Vec<u8> =
                serde_json::from_value(value.get("unix_bytes").cloned().unwrap_or_default())
                    .map_err(D::Error::custom)?;
            Ok(std::ffi::OsString::from_vec(bytes).into())
        }
        #[cfg(not(unix))]
        {
            Err(D::Error::custom("unsupported path representation"))
        }
    }
}
