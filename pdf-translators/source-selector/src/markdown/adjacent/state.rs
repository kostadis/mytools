use super::super::*;
use crate::models::path_serde;

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Receipt {
    #[serde(with = "path_serde")]
    pub target: PathBuf,
    pub sha256: String,
    pub work_id: String,
    pub source_sha256: String,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Ownership {
    pub schema_version: u32,
    #[serde(with = "path_serde")]
    pub root: PathBuf,
    pub root_identity: Value,
    pub receipts: Vec<Receipt>,
    pub intents: Vec<Receipt>,
}
impl Ownership {
    pub fn open(path: &Path, s: &Snapshot) -> Result<Self> {
        let state = if path.exists() {
            read_json(path)?
        } else {
            Self {
                schema_version: 1,
                root: s.source_root.clone(),
                root_identity: s.root_identity.clone(),
                receipts: vec![],
                intents: vec![],
            }
        };
        if state.schema_version != 1
            || state.root != s.source_root
            || state.root_identity != s.root_identity
        {
            return Err(SelectionError::Invalid(
                "ownership registry root/schema mismatch".into(),
            ));
        }
        Ok(state)
    }
    pub fn owns(&self, target: &Path, sha: &str) -> bool {
        self.receipts
            .iter()
            .chain(&self.intents)
            .any(|r| r.target == target && r.sha256 == sha)
    }
    pub fn remember(&mut self, r: Receipt) {
        if !self.receipts.contains(&r) {
            self.receipts.push(r);
        }
    }
    pub fn save(&self, path: &Path) -> Result<()> {
        let bytes = serde_json::to_vec_pretty(self)?;
        if fs::read(path).ok().as_deref() != Some(&bytes) {
            atomic_write(path, &bytes)?;
        }
        Ok(())
    }
}
