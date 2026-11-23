//! Read-only source selection for RPG libraries.
pub mod citations;
pub mod cli;
pub mod compare;
pub mod evidence;
pub mod export;
pub mod grouping;
pub mod hints;
pub mod inventory;
pub mod markdown;
pub mod models;
pub mod packets;
pub mod review;
pub mod store;

#[derive(Debug, thiserror::Error)]
pub enum SelectionError {
    #[error("{0}")]
    Capacity(String),
    #[error("{0}")]
    Usage(String),
    #[error("{0}")]
    Invalid(String),
    #[error(transparent)]
    Io(#[from] std::io::Error),
    #[error(transparent)]
    Json(#[from] serde_json::Error),
    #[error(transparent)]
    Sql(#[from] rusqlite::Error),
    #[error(transparent)]
    Csv(#[from] csv::Error),
}
pub type Result<T> = std::result::Result<T, SelectionError>;

pub fn digest(bytes: &[u8]) -> String {
    use sha2::{Digest, Sha256};
    format!("{:x}", Sha256::digest(bytes))
}
pub fn digest_json(value: &impl serde::Serialize) -> String {
    digest(&serde_json::to_vec(value).expect("serializable record"))
}
