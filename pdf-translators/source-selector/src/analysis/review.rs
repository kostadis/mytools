use super::{invalid, models::*, read_json, write_json};
use crate::{Result, digest_json};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    path::Path,
};
fn escape(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&#39;")
}
fn seal(m: &ReviewManifest) -> String {
    let mut value = m.clone();
    value.manifest_digest.clear();
    digest_json(&value)
}
pub fn verify_manifest(m: &ReviewManifest) -> Result<()> {
    if m.schema_version != 1 || seal(m) != m.manifest_digest {
        return Err(invalid("review manifest changed"));
    }
    Ok(())
}
pub fn prepare_cases(audit: &AuditResult) -> Result<ReviewManifest> {
    let files = audit
        .files
        .iter()
        .map(|f| (&f.source.source_id, f))
        .collect::<BTreeMap<_, _>>();
    let mut cards = vec![];
    let mut map = serde_json::Map::new();
    let disagreements = audit
        .reference
        .iter()
        .filter(|r| r.outcome == "selected_candidate_not_confirmed_by_reference")
        .flat_map(|r| r.groups.iter())
        .collect::<BTreeSet<_>>();
    let mut pending = audit
        .relationships
        .iter()
        .filter(|g| g.needs_review)
        .collect::<Vec<_>>();
    pending.sort_by_key(|g| {
        (
            !disagreements.contains(&g.id),
            !g.flagged,
            g.reference_rows.is_empty(),
            g.id.clone(),
        )
    });
    for g in pending {
        let candidates = g
            .source_ids
            .iter()
            .map(|id| {
                files
                    .get(id)
                    .copied()
                    .ok_or_else(|| invalid("unknown review candidate"))
            })
            .collect::<Result<Vec<_>>>()?;
        let protected = candidates
            .iter()
            .filter(|f| {
                audit
                    .protected
                    .iter()
                    .any(|p| p.bound && p.rule.source_id.as_ref() == Some(&f.source.source_id))
            })
            .map(|f| f.source.source_id.clone())
            .collect::<BTreeSet<_>>();
        let all = g.source_ids.clone();
        let mut actions = serde_json::Map::new();
        let mut texts = serde_json::Map::new();
        let mut add = |label: &str,
                       retain: Vec<String>,
                       omit: Vec<String>,
                       classification: &str,
                       successor: Option<String>| {
            let readable = retain
                .iter()
                .filter(|id| files.get(id).is_some_and(|f| f.source.read_error.is_none()))
                .cloned()
                .collect::<Vec<_>>();
            texts.insert(label.into(),json!(format!("Retain: {}. Omit from the proposed list: {}. Readable retained candidates eligible for conversion: {}. Classification: {classification}. No PDFs are deleted and no conversion is started.",retain.iter().map(|id|files.get(id).unwrap().source.relative_path.to_string_lossy().into_owned()).collect::<Vec<_>>().join("; "),if omit.is_empty(){"none".into()}else{omit.iter().map(|id|files.get(id).unwrap().source.relative_path.to_string_lossy().into_owned()).collect::<Vec<_>>().join("; ")},readable.iter().map(|id|files.get(id).unwrap().source.relative_path.to_string_lossy().into_owned()).collect::<Vec<_>>().join("; "))));
            if classification == "unresolved" {
                texts.insert(label.into(),json!("Defer only the relationship decision. Preserve existing file dispositions and owner instructions exactly. Unresolved readable candidates stay eligible; verified duplicates stay collapsed. No conversion or source change is started."));
            }
            actions.insert(
                label.into(),
                json!({"retain":retain,"omit":omit,"classification":classification,"successor":successor,"preserve_dispositions":classification=="unresolved"}),
            );
        };
        add(
            "Keep all listed editions",
            all.clone(),
            vec![],
            "retained_editions",
            None,
        );
        if all.len() > 1 {
            add(
                "Treat as separate works or companions",
                all.clone(),
                vec![],
                "separate_works",
                None,
            );
            for f in candidates.iter().filter(|_| candidates.len() <= 9) {
                if f.source.read_error.is_some() {
                    continue;
                }
                let mut keep = protected.clone();
                keep.insert(f.source.source_id.clone());
                let omit = all
                    .iter()
                    .filter(|id| !keep.contains(*id))
                    .cloned()
                    .collect::<Vec<_>>();
                if omit.is_empty() {
                    continue;
                }
                let label = format!(
                    "Select {}; omit the listed drafts",
                    f.source.relative_path.display()
                );
                add(
                    &label,
                    keep.into_iter().collect(),
                    omit,
                    "owner_selected_supersession",
                    Some(f.source.source_id.clone()),
                );
            }
        }
        add(
            "Defer; retain all candidates",
            all.clone(),
            vec![],
            "unresolved",
            None,
        );
        let scope = json!({"scope":format!("Only the analysis proposal for relationship {} and the listed unchanged sources; no production mutations.",g.id),"relationship_id":g.id,"evidence_digest":g.evidence_digest,"candidates":candidates.iter().map(|f|json!({"source_id":f.source.source_id,"fingerprint":f.source.fingerprint})).collect::<Vec<_>>(),"picks":actions});
        let id = format!("case-{}", &digest_json(&scope)[..24]);
        let mut evidence = format!(
            "<p>{}</p><p>Current reference paths: {}. Dates and filename versions alone do not establish succession. Unmatched may mean withdrawn, renamed, missing, or an obsolete draft.</p>",
            escape(&g.reason),
            escape(&serde_json::to_string(
                &candidates
                    .iter()
                    .flat_map(|f| f.evidence.iter().map(|e| e.reference_path.clone()))
                    .collect::<BTreeSet<_>>()
            )?)
        );
        for entry in audit
            .review_migrations
            .iter()
            .filter(|e| e["relationship_id"].as_str() == Some(&g.id))
        {
            if let Some(note) = entry["note"].as_str() {
                evidence.push_str(&format!("<p>Earlier owner note ({}; original scope preserved in the decision ledger): {}</p>",escape(entry["status"].as_str().unwrap_or("pending")),escape(note)));
            }
        }
        if candidates.len() > 9 {
            evidence.push_str("<p>This group has more than nine candidates. Keep all, identify separate works, or defer for focused review; leave any narrower edition-selection request as a note. Every candidate remains listed and no uncertain file is dropped.</p>");
        }
        for f in &candidates {
            evidence.push_str(&format!(
                "<p><b>{}</b> ({}) — {}. Reference evidence: {}. Read warning: {}.</p>",
                escape(&f.source.relative_path.to_string_lossy()),
                escape(&f.source.source_id),
                escape(&f.reason),
                escape(&serde_json::to_string(
                    &f.evidence
                        .iter()
                        .map(super::audit::stable_pair)
                        .collect::<Vec<_>>()
                )?),
                escape(f.source.read_error.as_deref().unwrap_or("none recorded"))
            ));
        }
        for extra in audit.supplemental_evidence.iter().filter(|e| {
            e["source_id"]
                .as_str()
                .is_some_and(|id| g.source_ids.iter().any(|s| s == id))
        }) {
            evidence.push_str(&format!(
                "<p>Supplemental evidence (not an approval): {}</p>",
                escape(&serde_json::to_string(extra)?)
            ));
        }
        if let Some(h) = &g.historical {
            for candidate in h.record["candidates"].as_array().into_iter().flatten() {
                let sid = candidate["source"]["source_id"].as_str().unwrap_or("");
                if g.source_ids.iter().any(|s| s == sid) {
                    evidence.push_str(&format!("<p>Historical metadata for {} (not a newly verified edition statement): {}. Saved page count: {}.</p>",escape(sid),escape(&serde_json::to_string(&candidate["dates"])?),escape(&candidate["page_count"].to_string())));
                }
            }
            evidence.push_str(&format!(
                "<p>Historical policy {} ({}) selected {}. Reason: {}</p>",
                escape(&h.policy),
                escape(&h.run_id),
                escape(
                    &h.selected
                        .iter()
                        .map(|s| s.relative_path.clone())
                        .collect::<Vec<_>>()
                        .join("; ")
                ),
                escape(&h.reason)
            ));
        }
        let picks = actions.keys().cloned().collect::<Vec<_>>();
        cards.push(json!({"id":id,"t":format!("Which sources should remain eligible for {}?",g.product_folder),"reviewKind":"decision","choiceOnly":true,"y":"No generic approval is valid; choose a named outcome.","n":"No generic rejection is valid; choose a named outcome.","ev":evidence,"picks":picks,"pickTexts":texts,"guessPick":"Defer; retain all candidates","guessWhy":"The available evidence has not resolved this relationship. Retaining candidates avoids losing owned content.","uncertainties":["No new full-document comparison was performed by this audit."]}));
        map.insert(id, scope);
    }
    let review_id = format!(
        "library-selection-{}",
        &digest_json(&json!({"cards":cards,"map":map}))[..24]
    );
    let mut m = ReviewManifest {
        schema_version: 1,
        review_id: review_id.clone(),
        audit_digest: digest_json(audit),
        items: json!({"title":"PDF library selection review","reviewId":review_id,"reviewKind":"decision","lede":"Select exact outcomes. Undecided cases remain retained. Save each page before navigating.","footer":"This review changes an analysis proposal only. All original PDFs and existing Markdown remain untouched. Explicit owner retention instructions are already applied. Evidence coverage is limited as stated on each card.","items":cards}),
        scope_map: Value::Object(map),
        manifest_digest: String::new(),
    };
    m.manifest_digest = seal(&m);
    Ok(m)
}
pub fn export_cases(audit: &AuditResult, out: &Path) -> Result<ReviewManifest> {
    let m = prepare_cases(audit)?;
    if out.exists() {
        let old: ReviewManifest = read_json(&out.join("review-manifest.json"))?;
        verify_manifest(&old)?;
        if old.manifest_digest != m.manifest_digest {
            return Err(invalid("changed review; create a new bundle version"));
        }
        return Ok(old);
    }
    let parent = out
        .parent()
        .ok_or_else(|| invalid("review output needs a parent"))?;
    std::fs::create_dir_all(parent)?;
    let staging = parent.join(format!(".review-export-{}", std::process::id()));
    std::fs::create_dir(&staging)?;
    let result = (|| {
        write_json(&staging.join("review_items.json"), &m.items)?;
        write_json(&staging.join("review_map.json"), &m.scope_map)?;
        write_json(&staging.join("review-manifest.json"), &m)?;
        std::fs::rename(&staging, out)?;
        Ok(m)
    })();
    if result.is_err() {
        let _ = std::fs::remove_dir_all(staging);
    }
    result
}
pub fn load_results(
    manifest: &ReviewManifest,
    bundle: &Path,
    normalized: &Path,
) -> Result<ReviewResults> {
    verify_manifest(manifest)?;
    let raw: Value = read_json(normalized)?;
    verify_bundle_results(manifest, bundle, &raw)?;
    if raw["reviewId"].as_str() != Some(&manifest.review_id)
        || raw["scope_map"] != manifest.scope_map
        || raw["total"].as_u64()
            != Some(
                manifest.items["items"]
                    .as_array()
                    .ok_or_else(|| invalid("missing review items"))?
                    .len() as u64,
            )
    {
        return Err(invalid("foreign or stale review results"));
    }
    let ids = manifest
        .scope_map
        .as_object()
        .unwrap()
        .keys()
        .cloned()
        .collect::<BTreeSet<_>>();
    let decisions = raw["decisions"]
        .as_object()
        .ok_or_else(|| invalid("missing decisions object"))?;
    let raw_picks = raw["picks"]
        .as_object()
        .ok_or_else(|| invalid("missing named picks"))?;
    let notes: BTreeMap<String, String> = serde_json::from_value(raw["notes"].clone())?;
    for id in decisions.keys().chain(raw_picks.keys()).chain(notes.keys()) {
        if !ids.contains(id) {
            return Err(invalid("unknown item in review results"));
        }
    }
    let mut picks = BTreeMap::new();
    let mut unresolved = vec![];
    for id in ids {
        let note = notes
            .get(&id)
            .map(|n| n.trim().to_lowercase())
            .unwrap_or_default();
        let clear_keep = matches!(note.as_str(), "keep all" | "keep all.")
            || (matches!(note.as_str(), "keep both" | "keep both.")
                && manifest.scope_map[&id]["candidates"]
                    .as_array()
                    .is_some_and(|v| v.len() == 2));
        match decisions.get(&id).and_then(Value::as_str) {
            Some("approve" | "reject") => {
                return Err(invalid("named-choice case cannot use a generic verdict"));
            }
            Some("pick") => {
                let pick = raw_picks
                    .get(&id)
                    .and_then(Value::as_str)
                    .ok_or_else(|| invalid("pick lacks named outcome"))?;
                if !manifest.scope_map[&id]["picks"]
                    .as_object()
                    .unwrap()
                    .contains_key(pick)
                {
                    return Err(invalid("unoffered named outcome"));
                }
                if note.is_empty() {
                    picks.insert(id, pick.into());
                } else if clear_keep {
                    picks.insert(id, "Keep all listed editions".into());
                } else {
                    unresolved.push(id);
                }
            }
            Some("discuss") | None => {
                if clear_keep {
                    picks.insert(id, "Keep all listed editions".into());
                } else {
                    unresolved.push(id);
                }
            }
            _ => return Err(invalid("unsupported review verdict")),
        }
    }
    if !picks.is_empty() && raw["provenance"].as_array().is_none_or(Vec::is_empty) {
        return Err(invalid("marked rulings require validated page provenance"));
    }
    Ok(ReviewResults {
        manifest: manifest.clone(),
        picks,
        unresolved,
        notes,
        provenance: raw["provenance"].clone(),
    })
}
fn object(value: &Value) -> Result<&serde_json::Map<String, Value>> {
    value
        .as_object()
        .ok_or_else(|| invalid("review object missing"))
}
fn ids(value: &Value) -> Result<BTreeSet<String>> {
    let list = value
        .as_array()
        .ok_or_else(|| invalid("review ID list missing"))?;
    let set = list
        .iter()
        .map(|v| {
            v.as_str()
                .map(str::to_owned)
                .ok_or_else(|| invalid("review ID must be text"))
        })
        .collect::<Result<BTreeSet<_>>>()?;
    if set.len() != list.len() {
        return Err(invalid("duplicate review IDs"));
    }
    Ok(set)
}
fn file_name(s: &str) -> Result<()> {
    if s.is_empty() || s == "." || s == ".." || s.contains('/') || s.contains('\\') {
        return Err(invalid("invalid review artifact path"));
    }
    Ok(())
}
fn verify_bundle_results(m: &ReviewManifest, bundle: &Path, raw: &Value) -> Result<()> {
    let b: Value = read_json(&bundle.join("bundle.json"))?;
    if b["schemaVersion"] != 1 || b["reviewId"].as_str() != Some(&m.review_id) {
        return Err(invalid("bundle belongs to another review"));
    }
    let cards = m.items["items"]
        .as_array()
        .ok_or_else(|| invalid("missing original cards"))?
        .iter()
        .map(|c| (c["id"].as_str().unwrap_or("").to_owned(), c))
        .collect::<BTreeMap<_, _>>();
    let all = cards.keys().cloned().collect::<BTreeSet<_>>();
    if b["total"].as_u64() != Some(all.len() as u64) {
        return Err(invalid("bundle count differs from frozen review"));
    }
    let mut covered = BTreeSet::new();
    let mut page_names = BTreeSet::new();
    let mut page_ids = BTreeSet::new();
    let mut decisions = serde_json::Map::new();
    let mut picks = serde_json::Map::new();
    let mut notes = serde_json::Map::new();
    let mut expected_provenance = BTreeMap::new();
    for page in b["pages"]
        .as_array()
        .ok_or_else(|| invalid("missing bundle pages"))?
    {
        let name = page["name"]
            .as_str()
            .ok_or_else(|| invalid("missing page name"))?;
        file_name(name)?;
        if !page_names.insert(name.to_owned()) {
            return Err(invalid("duplicate bundle page"));
        }
        let folder = bundle.join(name);
        let files = object(&page["files"])?;
        for required in [
            "review_items.json",
            "review_map.json",
            "scores.json",
            "review.html",
        ] {
            let expected = files
                .get(required)
                .and_then(Value::as_str)
                .ok_or_else(|| invalid("page receipt missing artifact hash"))?;
            let actual = crate::digest(&std::fs::read(folder.join(required))?);
            if actual != expected {
                return Err(invalid("frozen review page artifact changed"));
            }
        }
        if files.len() != 4 {
            return Err(invalid("unexpected page artifact paths"));
        }
        let spec: Value = read_json(&folder.join("review_items.json"))?;
        let scope: Value = read_json(&folder.join("review_map.json"))?;
        let page_id = spec["reviewId"]
            .as_str()
            .ok_or_else(|| invalid("page review ID missing"))?;
        if page["reviewId"].as_str() != Some(page_id) || !page_ids.insert(page_id.to_owned()) {
            return Err(invalid("duplicate or mismatched page review ID"));
        }
        let mut members = BTreeSet::new();
        for card in spec["items"]
            .as_array()
            .ok_or_else(|| invalid("page missing cards"))?
        {
            let id = card["id"]
                .as_str()
                .ok_or_else(|| invalid("card lacks ID"))?;
            if cards.get(id).copied() != Some(card)
                || scope[id] != m.scope_map[id]
                || !covered.insert(id.to_owned())
            {
                return Err(invalid(
                    "displayed question, consequences, or scope differ from frozen original",
                ));
            }
            members.insert(id.to_owned());
        }
        if ids(&page["items"])? != members
            || object(&scope)?.keys().cloned().collect::<BTreeSet<_>>() != members
        {
            return Err(invalid("page membership does not match frozen cards"));
        }
        let saved = folder.join("decisions.json");
        if saved.exists() {
            let data: Value = read_json(&saved)?;
            if data["reviewId"].as_str() != Some(page_id) {
                return Err(invalid("saved choices belong to another page"));
            }
            for (key, target) in [
                ("decisions", &mut decisions),
                ("picks", &mut picks),
                ("notes", &mut notes),
            ] {
                if let Some(values) = data.get(key) {
                    for (id, v) in object(values)? {
                        if !members.contains(id) {
                            return Err(invalid("saved page contains foreign case"));
                        }
                        target.insert(id.clone(), v.clone());
                    }
                }
            }
            expected_provenance.insert(name.to_owned(),serde_json::json!({"page":name,"reviewId":page_id,"savedAt":data["savedAt"],"decisions_sha256":crate::digest(&std::fs::read(&saved)?),"frozen_files":page["files"]}));
        }
    }
    if covered != all {
        return Err(invalid(
            "bundle does not cover every frozen case exactly once",
        ));
    }
    for (id, _) in &picks {
        if decisions.get(id).and_then(Value::as_str) != Some("pick") {
            return Err(invalid("named pick without matching verdict"));
        }
    }
    if raw["decisions"] != Value::Object(decisions.clone())
        || raw["picks"] != Value::Object(picks)
        || raw["notes"] != Value::Object(notes)
    {
        return Err(invalid(
            "normalized choices/notes differ from actual saved pages",
        ));
    }
    let marked = decisions.keys().cloned().collect::<BTreeSet<_>>();
    let unmarked = all.difference(&marked).cloned().collect::<BTreeSet<_>>();
    let discuss = decisions
        .iter()
        .filter(|(_, v)| v.as_str() == Some("discuss"))
        .map(|(id, _)| id.clone())
        .collect::<BTreeSet<_>>();
    if ids(&raw["unmarked"])? != unmarked || ids(&raw["discuss"])? != discuss {
        return Err(invalid("contradictory marked, unmarked or discussion IDs"));
    }
    let mut supplied = BTreeMap::new();
    for p in raw["provenance"]
        .as_array()
        .ok_or_else(|| invalid("missing page provenance"))?
    {
        let name = p["page"]
            .as_str()
            .ok_or_else(|| invalid("malformed page provenance"))?;
        if supplied.insert(name.to_owned(), p.clone()).is_some() {
            return Err(invalid("duplicate page provenance"));
        }
    }
    if supplied != expected_provenance {
        return Err(invalid(
            "page provenance does not match saved files and frozen membership",
        ));
    }
    Ok(())
}
