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
pub fn export_cases(audit: &AuditResult, out: &Path) -> Result<ReviewManifest> {
    let files = audit
        .files
        .iter()
        .map(|f| (&f.source.source_id, f))
        .collect::<BTreeMap<_, _>>();
    let mut cards = vec![];
    let mut map = serde_json::Map::new();
    for g in audit.relationships.iter().filter(|g| g.needs_review) {
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
            .filter(|f| f.ruling.is_some())
            .map(|f| f.source.source_id.clone())
            .collect::<BTreeSet<_>>();
        let all = g.source_ids.clone();
        let mut actions = serde_json::Map::new();
        let mut texts = serde_json::Map::new();
        let mut add = |label: &str,
                       retain: Vec<String>,
                       omit: Vec<String>,
                       classification: &str| {
            let readable = retain
                .iter()
                .filter(|id| files.get(id).is_some_and(|f| f.source.read_error.is_none()))
                .cloned()
                .collect::<Vec<_>>();
            texts.insert(label.into(),json!(format!("Retain: {}. Omit from the proposed list: {}. Readable retained candidates eligible for conversion: {}. Classification: {classification}. No PDFs are deleted and no conversion is started.",retain.join(", "),if omit.is_empty(){"none".into()}else{omit.join(", ")},readable.join(", "))));
            actions.insert(
                label.into(),
                json!({"retain":retain,"omit":omit,"classification":classification}),
            );
        };
        add(
            "Keep all listed editions",
            all.clone(),
            vec![],
            "retained_editions",
        );
        if all.len() > 1 {
            add(
                "Treat as separate works or companions",
                all.clone(),
                vec![],
                "separate_works",
            );
            for f in &candidates {
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
                );
            }
        }
        add(
            "Defer; retain all candidates",
            all.clone(),
            vec![],
            "unresolved",
        );
        let scope = json!({"scope":format!("Only the analysis proposal for relationship {} and the listed unchanged sources; no production mutations.",g.id),"relationship_id":g.id,"evidence_digest":g.evidence_digest,"candidates":candidates.iter().map(|f|json!({"source_id":f.source.source_id,"fingerprint":f.source.fingerprint})).collect::<Vec<_>>(),"picks":actions});
        let id = format!("case-{}", &digest_json(&scope)[..24]);
        let mut evidence = format!(
            "<p>{}</p><p>Current reference rows: {:?}. Dates and filename versions alone do not establish succession. Unmatched may mean withdrawn, renamed, missing, or an obsolete draft.</p>",
            escape(&g.reason),
            g.reference_rows
        );
        for f in &candidates {
            evidence.push_str(&format!(
                "<p><b>{}</b> ({}) — {}. Reference evidence: {}. Read warning: {}.</p>",
                escape(&f.source.relative_path.to_string_lossy()),
                escape(&f.source.source_id),
                escape(&f.reason),
                escape(&serde_json::to_string(&f.evidence)?),
                escape(f.source.read_error.as_deref().unwrap_or("none recorded"))
            ));
        }
        if let Some(h) = &g.historical {
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
