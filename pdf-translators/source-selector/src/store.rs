use crate::{Result, SelectionError, models::*};
use rusqlite::{Connection, OptionalExtension, params};
use serde::{Serialize, de::DeserializeOwned};
use serde_json::Value;
use std::path::Path;

pub struct Store {
    conn: Connection,
}
impl Store {
    pub fn path(&self) -> &Path {
        Path::new(self.conn.path().expect("file-backed store"))
    }
    pub fn record<T: DeserializeOwned>(&self, kind: &str, id: &str) -> Result<Option<T>> {
        let body: Option<String> = self
            .conn
            .query_row(
                "SELECT body FROM records WHERE kind=?1 AND id=?2",
                params![kind, id],
                |r| r.get(0),
            )
            .optional()?;
        Ok(body.map(|b| serde_json::from_str(&b)).transpose()?)
    }
    fn bump_graph(&self, kind: &str) -> Result<()> {
        if matches!(kind, "groups" | "hints" | "decisions" | "evidence") {
            let n = self
                .meta("authority_revision")?
                .and_then(|v| v.as_u64())
                .unwrap_or(0);
            self.set_meta("authority_revision", &serde_json::json!(n + 1))?;
        }
        if matches!(kind, "groups" | "hints") {
            let n = self
                .meta("graph_revision")?
                .and_then(|v| v.as_u64())
                .unwrap_or(0);
            self.set_meta("graph_revision", &serde_json::json!(n + 1))?;
        }
        Ok(())
    }
    pub fn open_readonly(path: &Path) -> Result<Self> {
        let conn = Connection::open_with_flags(path, rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY)?;
        let store = Self { conn };
        if store.meta("schema_version")? != Some(serde_json::json!(1)) {
            return Err(SelectionError::Invalid(
                "unsupported database schema".into(),
            ));
        }
        Ok(store)
    }
    /// Shared with the final publication boundary. No PDF reads belong here.
    pub fn authority_guard(&self) -> Result<std::fs::File> {
        use std::os::unix::fs::OpenOptionsExt;
        let path = self
            .conn
            .path()
            .ok_or_else(|| SelectionError::Invalid("database has no path".into()))?;
        let file = std::fs::OpenOptions::new()
            .create(true)
            .truncate(false)
            .read(true)
            .write(true)
            .custom_flags(libc::O_NOFOLLOW)
            .open(format!("{path}.authority.lock"))?;
        file.lock()?;
        Ok(file)
    }
    fn mutation_guard(&self) -> Result<Option<std::fs::File>> {
        if self.conn.is_autocommit() {
            Ok(Some(self.authority_guard()?))
        } else {
            Ok(None)
        }
    }
    pub fn scan_transaction<T>(&mut self, f: impl FnOnce(&mut Self) -> Result<T>) -> Result<T> {
        let _gate = self.authority_guard()?;
        self.conn.execute_batch("BEGIN IMMEDIATE")?;
        match f(self) {
            Ok(v) => {
                self.conn.execute_batch("COMMIT")?;
                Ok(v)
            }
            Err(e) => {
                let _ = self.conn.execute_batch("ROLLBACK");
                Err(e)
            }
        }
    }
    pub fn count_records(&self, kind: &str) -> Result<usize> {
        Ok(self
            .conn
            .query_row("SELECT count(*) FROM records WHERE kind=?1", [kind], |r| {
                r.get::<_, i64>(0)
            })? as usize)
    }
    pub fn keyed_records<T: DeserializeOwned>(
        &self,
        kind: &str,
    ) -> Result<std::collections::BTreeMap<String, T>> {
        let mut stmt = self
            .conn
            .prepare("SELECT id,body FROM records WHERE kind=?1 ORDER BY id")?;
        let rows = stmt.query_map([kind], |r| {
            Ok((r.get::<_, String>(0)?, r.get::<_, String>(1)?))
        })?;
        rows.map(|r| {
            let (id, body) = r?;
            Ok((id, serde_json::from_str(&body)?))
        })
        .collect()
    }
    pub fn delete_record(&mut self, kind: &str, id: &str) -> Result<()> {
        let _gate = self.mutation_guard()?;
        self.conn.execute(
            "DELETE FROM records WHERE kind=?1 AND id=?2",
            params![kind, id],
        )?;
        self.bump_graph(kind)?;
        Ok(())
    }
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
        let observed_identity = crate::inventory::root_identity(&result.root)?;
        if let Some(prior) = self.meta("root_identity")?
            && prior != observed_identity
        {
            return Err(SelectionError::Invalid(
                "library root identity changed; verify the mount before using fresh state".into(),
            ));
        }
        if result.sources.is_empty()
            && self
                .meta("inventory")?
                .is_some_and(|v| v["sources"].as_array().is_some_and(|s| !s.is_empty()))
        {
            return Err(SelectionError::Invalid(
                "library became empty; prior inventory retained, verify the mount".into(),
            ));
        }
        let root = serde_json::to_value(result.root.to_string_lossy())?;
        let root_key = serde_json::json!(crate::inventory::path_bytes(&result.root));
        if let Some(prior) = self.meta("root_key")?
            && prior != root_key
        {
            return Err(SelectionError::Invalid(
                "state database belongs to a different root".into(),
            ));
        }
        let tx = self.conn.savepoint()?;
        tx.execute("UPDATE sources SET active=0", [])?;
        for source in &result.sources {
            tx.execute("INSERT INTO sources VALUES (?1,?2,1) ON CONFLICT(id) DO UPDATE SET body=excluded.body,active=1", params![source.source_id,serde_json::to_string(source)?])?;
        }
        for (key, value) in [
            ("root_identity", observed_identity),
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
        let mut sources: Vec<Source> = rows
            .map(|row| Ok(serde_json::from_str(&row?)?))
            .collect::<Result<_>>()?;
        let failures = self.keyed_records::<Value>("inspection_errors")?;
        for source in &mut sources {
            if let Some(failure) = failures.get(&source.source_id)
                && failure.get("fingerprint") == Some(&serde_json::to_value(&source.fingerprint)?)
            {
                source.read_error = failure["error"].as_str().map(str::to_string);
            }
        }
        Ok(sources)
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
        let _gate = self.mutation_guard()?;
        self.conn.execute(
            "INSERT OR REPLACE INTO records VALUES (?1,?2,?3)",
            params![kind, id, serde_json::to_string(value)?],
        )?;
        self.bump_graph(kind)?;
        Ok(())
    }
    /// Preserve the original audit event when the same fact is replayed.
    pub fn put_record_once(
        &mut self,
        kind: &str,
        id: &str,
        value: &impl Serialize,
    ) -> Result<bool> {
        let _gate = self.mutation_guard()?;
        let inserted = self.conn.execute(
            "INSERT OR IGNORE INTO records VALUES (?1,?2,?3)",
            params![kind, id, serde_json::to_string(value)?],
        )? > 0;
        if inserted {
            self.bump_graph(kind)?;
        }
        Ok(inserted)
    }
    pub fn records<T: DeserializeOwned>(&self, kind: &str) -> Result<Vec<T>> {
        let mut stmt = self
            .conn
            .prepare("SELECT body FROM records WHERE kind=?1 ORDER BY id")?;
        let rows = stmt.query_map([kind], |r| r.get::<_, String>(0))?;
        rows.map(|r| Ok(serde_json::from_str(&r?)?)).collect()
    }
    pub fn replace_records(&mut self, kind: &str, values: &[(String, Value)]) -> Result<()> {
        let _gate = self.mutation_guard()?;
        let tx = self.conn.savepoint()?;
        tx.execute("DELETE FROM records WHERE kind=?1", [kind])?;
        for (id, value) in values {
            tx.execute(
                "INSERT INTO records VALUES (?1,?2,?3)",
                params![kind, id, value.to_string()],
            )?;
        }
        tx.commit()?;
        self.bump_graph(kind)?;
        Ok(())
    }
}
