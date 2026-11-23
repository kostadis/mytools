use crate::{Result, SelectionError, models::*};
use rusqlite::{Connection, OptionalExtension, params};
use serde::{Serialize, de::DeserializeOwned};
use serde_json::Value;
use std::path::Path;

pub struct Store {
    conn: Connection,
}
impl Store {
    pub fn open(path: &Path) -> Result<Self> {
        let conn = Connection::open(path)?;
        conn.execute_batch("PRAGMA journal_mode=WAL; CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, body TEXT NOT NULL); CREATE TABLE IF NOT EXISTS sources (id TEXT PRIMARY KEY, body TEXT NOT NULL, active INTEGER NOT NULL); CREATE TABLE IF NOT EXISTS cache (id TEXT, stage TEXT, cache_key TEXT, body TEXT NOT NULL, PRIMARY KEY(id,stage,cache_key)); CREATE TABLE IF NOT EXISTS records (kind TEXT,id TEXT,body TEXT NOT NULL,PRIMARY KEY(kind,id));")?;
        let store = Self { conn };
        if let Some(v) = store.meta("schema_version")? {
            if v != serde_json::json!(1) {
                return Err(SelectionError::Invalid(
                    "unsupported database schema".into(),
                ));
            }
        } else {
            store.set_meta("schema_version", &serde_json::json!(1))?;
        }
        Ok(store)
    }
    pub fn upsert_inventory(&mut self, result: &InventoryResult) -> Result<()> {
        let root = serde_json::to_value(&result.root.to_string_lossy())?;
        let root_key = serde_json::json!(crate::inventory::path_bytes(&result.root));
        if let Some(prior) = self.meta("root_key")? {
            if prior != root_key {
                return Err(SelectionError::Invalid(
                    "state database belongs to a different root".into(),
                ));
            }
        }
        let tx = self.conn.transaction()?;
        tx.execute("UPDATE sources SET active=0", [])?;
        for source in &result.sources {
            tx.execute("INSERT INTO sources VALUES (?1,?2,1) ON CONFLICT(id) DO UPDATE SET body=excluded.body,active=1", params![source.source_id,serde_json::to_string(source)?])?;
        }
        for (key, value) in [
            ("root_key", root_key),
            ("root", root),
            ("inventory", serde_json::to_value(result)?),
        ] {
            tx.execute(
                "INSERT OR REPLACE INTO meta VALUES (?1,?2)",
                params![key, value.to_string()],
            )?;
        }
        tx.commit()?;
        Ok(())
    }
    pub fn sources(&self) -> Result<Vec<Source>> {
        let mut stmt = self
            .conn
            .prepare("SELECT body FROM sources WHERE active=1 ORDER BY id")?;
        let rows = stmt.query_map([], |r| r.get::<_, String>(0))?;
        rows.map(|row| Ok(serde_json::from_str(&row?)?)).collect()
    }
    pub fn get_cached(&self, id: &str, stage: &str, key: &str) -> Result<Option<Value>> {
        let body: Option<String> = self
            .conn
            .query_row(
                "SELECT body FROM cache WHERE id=?1 AND stage=?2 AND cache_key=?3",
                params![id, stage, key],
                |r| r.get(0),
            )
            .optional()?;
        body.map(|s| Ok(serde_json::from_str(&s)?)).transpose()
    }
    pub fn put_cached(&mut self, id: &str, stage: &str, key: &str, body: &Value) -> Result<()> {
        self.conn.execute(
            "INSERT OR REPLACE INTO cache VALUES (?1,?2,?3,?4)",
            params![id, stage, key, body.to_string()],
        )?;
        Ok(())
    }
    pub fn meta(&self, key: &str) -> Result<Option<Value>> {
        let s: Option<String> = self
            .conn
            .query_row("SELECT body FROM meta WHERE key=?1", [key], |r| r.get(0))
            .optional()?;
        s.map(|v| Ok(serde_json::from_str(&v)?)).transpose()
    }
    pub fn set_meta(&self, key: &str, value: &Value) -> Result<()> {
        self.conn.execute(
            "INSERT OR REPLACE INTO meta VALUES (?1,?2)",
            params![key, value.to_string()],
        )?;
        Ok(())
    }
    pub fn put_record(&mut self, kind: &str, id: &str, value: &impl Serialize) -> Result<()> {
        self.conn.execute(
            "INSERT OR REPLACE INTO records VALUES (?1,?2,?3)",
            params![kind, id, serde_json::to_string(value)?],
        )?;
        Ok(())
    }
    pub fn records<T: DeserializeOwned>(&self, kind: &str) -> Result<Vec<T>> {
        let mut stmt = self
            .conn
            .prepare("SELECT body FROM records WHERE kind=?1 ORDER BY id")?;
        let rows = stmt.query_map([kind], |r| r.get::<_, String>(0))?;
        rows.map(|r| Ok(serde_json::from_str(&r?)?)).collect()
    }
    pub fn replace_records(&mut self, kind: &str, values: &[(String, Value)]) -> Result<()> {
        let tx = self.conn.transaction()?;
        tx.execute("DELETE FROM records WHERE kind=?1", [kind])?;
        for (id, value) in values {
            tx.execute(
                "INSERT INTO records VALUES (?1,?2,?3)",
                params![kind, id, value.to_string()],
            )?;
        }
        tx.commit()?;
        Ok(())
    }
}
