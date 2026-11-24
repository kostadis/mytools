use crate::models::{Group, Source};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{collections::BTreeMap, path::PathBuf};

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct AnalysisConfig {
    #[serde(default = "policy_default")]
    pub analysis_policy: String,
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
    #[serde(default)]
    pub verified_hashes: BTreeMap<String, String>,
    pub groups: BTreeMap<String, HistoricalObservation>,
    pub unprocessed_groups: Vec<String>,
    pub warnings: Vec<String>,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ProposalState {
    Selected,
    ExplicitlyRetained,
    UnresolvedRetained,
    Duplicate,
    Superseded,
    UnreadableRetained,
}
impl ProposalState {
    pub fn eligible(&self) -> bool {
        matches!(
            self,
            Self::Selected | Self::ExplicitlyRetained | Self::UnresolvedRetained
        )
    }
    pub fn retained(&self) -> bool {
        self.eligible() || *self == Self::UnreadableRetained
    }
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct PairEvidence {
    pub old_source_id: String,
    pub reference_row: usize,
    pub reference_path: String,
    pub method: EvidenceMethod,
    pub scope: String,
    pub provenance: String,
    pub raw_evidence: String,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct FileCoverage {
    pub source: Source,
    pub reference_rows: Vec<usize>,
    pub reported_reference_rows: Vec<usize>,
    pub evidence: Vec<PairEvidence>,
    pub state: ProposalState,
    pub reason: String,
    pub representative: Option<String>,
    pub ruling: Option<String>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ReferenceOutcome {
    pub row: usize,
    pub d_path: String,
    pub method: EvidenceMethod,
    pub matched_sources: Vec<String>,
    pub reported_sources: Vec<String>,
    pub current_source_ids: Vec<String>,
    pub groups: Vec<String>,
    pub outcome: String,
    pub selected_support_methods: Vec<EvidenceMethod>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Relationship {
    pub id: String,
    pub source_ids: Vec<String>,
    pub reference_rows: Vec<usize>,
    pub publisher: String,
    pub product_folder: String,
    pub historical: Option<HistoricalObservation>,
    pub needs_review: bool,
    pub flagged: bool,
    pub evidence_digest: String,
    pub reason: String,
    pub classification: String,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ProtectedEdition {
    pub rule: RetentionRule,
    pub bound: bool,
    pub warning: Option<String>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct AuditResult {
    pub policy_version: String,
    pub schema_version: u32,
    pub input_receipt: String,
    pub provisional: bool,
    pub files: Vec<FileCoverage>,
    pub current_files: Vec<CurrentCoverage>,
    #[serde(default)]
    pub review_migrations: Vec<Value>,
    pub reference: Vec<ReferenceOutcome>,
    pub relationships: Vec<Relationship>,
    pub protected: Vec<ProtectedEdition>,
    pub warnings: Vec<String>,
    pub counts: BTreeMap<String, usize>,
    #[serde(default)]
    pub review_notes: BTreeMap<String, String>,
    #[serde(default)]
    pub supplemental_evidence: Vec<Value>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct SampleMember {
    pub relationship_id: String,
    pub publisher: String,
    pub partition_key: String,
    pub holdout: bool,
    pub stratum: String,
    pub flagged: bool,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct SampleManifest {
    pub seed: String,
    pub per_stratum: usize,
    pub holdout_percent: u8,
    pub membership: Vec<SampleMember>,
    pub selected: Vec<String>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ReviewManifest {
    pub schema_version: u32,
    pub review_id: String,
    pub audit_digest: String,
    pub items: Value,
    pub scope_map: Value,
    pub manifest_digest: String,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ReviewResults {
    pub manifest: ReviewManifest,
    pub picks: BTreeMap<String, String>,
    pub unresolved: Vec<String>,
    pub notes: BTreeMap<String, String>,
    pub provenance: Value,
}

fn policy_default() -> String {
    super::POLICY_VERSION.into()
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CurrentCoverage {
    pub source: Source,
    pub scope: String,
    pub reference_rows: Vec<usize>,
    pub size_agreement: Option<bool>,
    pub provenance: String,
}
