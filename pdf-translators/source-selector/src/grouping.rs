use crate::{
    Result, SelectionError, digest_json,
    inventory::{checked_path, fingerprint},
    models::*,
    store::Store,
};
use regex::Regex;
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    io::Read,
    path::Path,
    sync::LazyLock,
};

pub fn hash_source(path: &Path) -> Result<String> {
    let before = fingerprint(path)?;
    let mut input = fs::File::open(path)?;
    let mut hash = Sha256::new();
    let mut buffer = [0u8; 65536];
    loop {
        let n = input.read(&mut buffer)?;
        if n == 0 {
            break;
        }
        hash.update(&buffer[..n]);
    }
    if before != fingerprint(path)? {
        return Err(SelectionError::Invalid(format!(
            "source changed while hashing: {}",
            path.display()
        )));
    }
    Ok(format!("{:x}", hash.finalize()))
}

pub fn cached_hash(root: &Path, source: &Source, store: &mut Store) -> Result<String> {
    let path = checked_path(root, &source.relative_path)?;
    if fingerprint(&path)? != source.fingerprint {
        return Err(SelectionError::Invalid(format!(
            "source changed since inventory: {}",
            path.display()
        )));
    }
    let key = digest_json(&(1, &source.fingerprint));
    if let Some(v) = store.get_cached(&source.source_id, "hash", &key)?
        && let Some(s) = v.as_str()
    {
        return Ok(s.into());
    }
    let hash = hash_source(&path)?;
    store.put_cached(&source.source_id, "hash", &key, &serde_json::json!(hash))?;
    Ok(hash)
}

fn normalized(text: &str) -> String {
    text.chars()
        .map(|c| {
            if c.is_alphanumeric() {
                c.to_ascii_lowercase()
            } else {
                ' '
            }
        })
        .collect::<String>()
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}
pub fn title_key(path: &Path) -> String {
    static OLD: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"(?i)\.old-\d+").unwrap());
    static ID: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^\d{5,}[-_ ]+").unwrap());
    static VERSION: LazyLock<Regex> = LazyLock::new(|| {
        Regex::new(r"(?i)(?:^|[ _.-])v(?:er(?:sion)?)?[ _.-]*\d+(?:[._]\d+)*").unwrap()
    });
    static DOTTED: LazyLock<Regex> =
        LazyLock::new(|| Regex::new(r"(?:^|[ _-])\d+\.\d+(?:\.\d+)*(?:$|[ _()-])").unwrap());
    static FORMAT: LazyLock<Regex> = LazyLock::new(|| {
        Regex::new(
            r"(?i)printer[ _-]*friendly|print[ _-]*friendly|optimized[ _-]*pdf|full[ _-]*res|quick[ _-]*load",
        )
        .unwrap()
    });
    let stem = path.file_stem().unwrap_or_default().to_string_lossy();
    let s = OLD.replace_all(&stem, "");
    let s = ID.replace(&s, "");
    let s = VERSION.replace_all(&s, " ");
    let s = DOTTED.replace_all(&s, " ");
    normalized(&FORMAT.replace_all(&s, " "))
}

pub fn build_groups(sources: &[Source], hints: &[Hint], store: &mut Store) -> Result<Vec<Group>> {
    let inv: InventoryResult = serde_json::from_value(
        store
            .meta("inventory")?
            .ok_or_else(|| SelectionError::Invalid("scan first".into()))?,
    )?;
    let pdfs: Vec<_> = sources
        .iter()
        .filter(|s| s.kind == SourceKind::Pdf)
        .collect();
    let indexes: BTreeMap<_, _> = pdfs
        .iter()
        .enumerate()
        .map(|(i, s)| (s.source_id.clone(), i))
        .collect();
    let mut sets: Vec<usize> = (0..pdfs.len()).collect();
    let mut reasons = BTreeMap::<usize, BTreeSet<String>>::new();
    let mut sizes = BTreeMap::<u64, Vec<usize>>::new();
    let mut keys = BTreeMap::<(String, String, String), Vec<usize>>::new();
    for (i, s) in pdfs.iter().enumerate() {
        if s.read_error.is_none() {
            sizes.entry(s.fingerprint.size).or_default().push(i);
        }
        keys.entry((
            normalized(&s.publisher),
            normalized(&s.product_folder),
            title_key(&s.relative_path),
        ))
        .or_default()
        .push(i);
    }
    for bucket in sizes.values().filter(|v| v.len() > 1) {
        let mut hashes = BTreeMap::<String, Vec<usize>>::new();
        for i in bucket {
            match cached_hash(&inv.root, pdfs[*i], store) {
                Ok(hash) => hashes.entry(hash).or_default().push(*i),
                Err(e) => {
                    store.put_record("grouping_errors", &pdfs[*i].source_id, &e.to_string())?;
                }
            }
        }
        for group in hashes.values().filter(|g| g.len() > 1) {
            join(&mut sets, &mut reasons, group, "exact_bytes");
        }
    }
    for group in keys.values().filter(|g| g.len() > 1) {
        join(&mut sets, &mut reasons, group, "title_candidate");
    }
    for hint in hints.iter().filter(|h| h.origin == "muse") {
        let group: Vec<_> = hint
            .source_ids
            .iter()
            .filter_map(|id| indexes.get(id).copied())
            .collect();
        if group.len() > 1 {
            join(&mut sets, &mut reasons, &group, "muse_candidate");
        }
    }
    let mut components = BTreeMap::<usize, Vec<usize>>::new();
    for i in 0..pdfs.len() {
        let parent = find(&mut sets, i);
        components.entry(parent).or_default().push(i);
    }
    let mut groups = vec![];
    for members in components.values() {
        let mut ids: Vec<_> = members.iter().map(|i| pdfs[*i].source_id.clone()).collect();
        ids.sort();
        let mut rs = BTreeSet::new();
        for i in members {
            if let Some(r) = reasons.get(i) {
                rs.extend(r.iter().cloned());
            }
        }
        let fp: Vec<_> = ids
            .iter()
            .map(|id| {
                let s = pdfs[indexes[id]];
                (id, &s.fingerprint)
            })
            .collect();
        let membership_digest = digest_json(&fp);
        groups.push(Group {
            group_id: format!("g{}", &digest_json(&ids)[..20]),
            source_ids: ids,
            membership_digest,
            reasons: rs.into_iter().collect(),
        });
    }
    store.reconcile_groups(&groups)
}
fn find(sets: &mut [usize], i: usize) -> usize {
    if sets[i] != i {
        sets[i] = find(sets, sets[i]);
    }
    sets[i]
}
fn join(
    sets: &mut [usize],
    reasons: &mut BTreeMap<usize, BTreeSet<String>>,
    group: &[usize],
    reason: &str,
) {
    let p = find(sets, group[0]);
    for i in group {
        let q = find(sets, *i);
        sets[q] = p;
        reasons.entry(*i).or_default().insert(reason.into());
    }
}

impl Store {
    pub fn reconcile_groups(&mut self, groups: &[Group]) -> Result<Vec<Group>> {
        let prior: Vec<Group> = self.records("groups")?;
        let mut used = BTreeSet::new();
        let mut next = vec![];
        for group in groups {
            let mut g = group.clone();
            let old = prior
                .iter()
                .filter(|p| !used.contains(&p.group_id))
                .filter_map(|p| {
                    let n = p
                        .source_ids
                        .iter()
                        .filter(|id| g.source_ids.contains(id))
                        .count();
                    if n > 0 { Some((n, p)) } else { None }
                })
                .max_by(|a, b| a.0.cmp(&b.0).then_with(|| b.1.group_id.cmp(&a.1.group_id)));
            if let Some((_, p)) = old {
                g.group_id = p.group_id.clone();
            }
            used.insert(g.group_id.clone());
            next.push(g);
        }
        self.replace_records(
            "groups",
            &next
                .iter()
                .map(|g| Ok((g.group_id.clone(), serde_json::to_value(g)?)))
                .collect::<Result<Vec<_>>>()?,
        )?;
        Ok(next)
    }
}
