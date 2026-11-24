use crate::models::{Group, Source};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{collections::BTreeMap, path::PathBuf};

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct AnalysisConfig {
    pub schema_version: u32,
    pub csv: PathBuf,
    pub d_root: String,
    pub g_root: String,
    pub old_inventory: PathBuf,
    pub current_inventory: PathBuf,
    pub history: PathBuf,
    pub history_status: PathBuf,
    pub historical_runs: Vec<String>,
    pub owner_rulings: PathBuf,
    #[serde(default)]
    pub evidence_imports: Vec<PathBuf>,
    #[serde(default)]
    pub reference_complete: bool,
    #[serde(default)]
    pub completion_attestation: Option<String>,
    pub sample_seed: String,
    #[serde(default = "sample_default")]
    pub sample_per_stratum: usize,
    #[serde(default = "holdout_default")]
    pub holdout_percent: u8,
}
fn sample_default() -> usize {
    5
}
fn holdout_default() -> u8 {
    20
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum EvidenceMethod {
    ExactBytes,
    AllRenderedPages,
    SampledBytes,
    SampledPages,
    PartialReference,
    UnspecifiedOtherCopy,
    Unconfirmed,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ReferenceRow {
    pub row: usize,
    pub d_path: String,
    pub g_path: Option<String>,
    pub other_paths: Vec<String>,
    pub method: EvidenceMethod,
    pub raw: BTreeMap<String, String>,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct InputReceipt {
    pub label: String,
    pub original: PathBuf,
    pub snapshot: String,
    pub sha256: String,
    pub source_size: u64,
    pub source_modified_ns: u128,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct FrozenInputs {
    pub schema_version: u32,
    pub snapshot_root: PathBuf,
    pub receipt_id: String,
    pub config: AnalysisConfig,
    pub receipts: Vec<InputReceipt>,
    pub reference: Vec<ReferenceRow>,
    pub old_sources: Vec<Source>,
    pub current_sources: Vec<Source>,
    pub groups: Vec<Group>,
    pub owner_rulings: Vec<RetentionRule>,
    pub imported_evidence: Vec<Value>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct RetentionRule {
    pub id: String,
    pub wording: String,
    pub provenance: String,
    #[serde(default)]
    pub source_id: Option<String>,
    #[serde(default)]
    pub fingerprint: Option<crate::models::Fingerprint>,
    #[serde(default)]
    pub action: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct HistoricalChoice {
    pub source_id: String,
    pub relative_path: String,
    pub sha256: Option<String>,
    pub detail: Value,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct HistoricalObservation {
    pub group_id: String,
    pub run_id: String,
    pub policy: String,
    pub status: String,
    pub reason: String,
    pub selected: Vec<HistoricalChoice>,
    pub hashes: BTreeMap<String, String>,
    pub scorable: bool,
    pub record: Value,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct HistoricalView {
    pub groups: BTreeMap<String, HistoricalObservation>,
    pub unprocessed_groups: Vec<String>,
    pub warnings: Vec<String>,
}
