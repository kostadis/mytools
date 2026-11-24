use super::{invalid, models::*, write_json};
use crate::{Result, digest_json};
use serde_json::json;
use std::{
    collections::{BTreeMap, BTreeSet},
    io::Write,
    path::Path,
};
pub fn write(audit: &AuditResult, sample: &SampleManifest, out: &Path) -> Result<()> {
    if out.exists() {
        let receipt: serde_json::Value = super::read_json(&out.join("report-receipt.json"))?;
        if receipt["audit_digest"] == digest_json(audit)
            && receipt["sample_digest"] == digest_json(sample)
        {
            return Ok(());
        }
        return Err(invalid("report changed; use a new output directory"));
    }
    let parent = out
        .parent()
        .ok_or_else(|| invalid("report output needs parent"))?;
    std::fs::create_dir_all(parent)?;
    let stage = parent.join(format!(".analysis-report-{}", std::process::id()));
    std::fs::create_dir(&stage)?;
    let result = (|| {
        let mut states = BTreeMap::new();
        let mut methods = BTreeMap::new();
        let mut publishers = BTreeMap::new();
        let mut metadata_breakdown: BTreeMap<String, BTreeMap<String, usize>> = BTreeMap::new();
        for f in &audit.files {
            *states
                .entry(serde_json::to_value(&f.state)?.as_str().unwrap().to_owned())
                .or_insert(0usize) += 1;
            *publishers
                .entry(f.source.publisher.clone())
                .or_insert(0usize) += 1;
            for field in ["system", "language", "document_role", "text_reliability"] {
                let val = f
                    .source
                    .metadata
                    .get(field)
                    .map(|v| {
                        v.as_str()
                            .map(str::to_owned)
                            .unwrap_or_else(|| v.to_string())
                    })
                    .unwrap_or_else(|| "unknown".into());
                *metadata_breakdown
                    .entry(field.into())
                    .or_default()
                    .entry(val)
                    .or_default() += 1;
            }
        }
        for r in &audit.reference {
            *methods
                .entry(
                    serde_json::to_value(&r.method)?
                        .as_str()
                        .unwrap()
                        .to_owned(),
                )
                .or_insert(0usize) += 1;
        }
        let comparable = audit
            .relationships
            .iter()
            .filter(|g| {
                g.historical
                    .as_ref()
                    .is_some_and(|h| h.scorable && !h.selected.is_empty())
            })
            .collect::<Vec<_>>();
        let source_ids = comparable
            .iter()
            .flat_map(|g| g.source_ids.iter().cloned())
            .collect::<BTreeSet<_>>();
        let historical_ids = comparable
            .iter()
            .flat_map(|g| {
                g.historical
                    .as_ref()
                    .unwrap()
                    .selected
                    .iter()
                    .map(|s| s.source_id.clone())
            })
            .filter(|id| source_ids.contains(id))
            .collect::<BTreeSet<_>>();
        let mut exact_keys = BTreeSet::new();
        for f in audit
            .files
            .iter()
            .filter(|f| source_ids.contains(&f.source.source_id))
        {
            let hash = f.source.fingerprint.sha256.clone().or_else(|| {
                comparable.iter().find_map(|g| {
                    g.historical
                        .as_ref()
                        .unwrap()
                        .hashes
                        .get(&f.source.source_id)
                        .cloned()
                })
            });
            exact_keys.insert(
                hash.map(|h| format!("sha:{h}"))
                    .unwrap_or_else(|| format!("source:{}", f.source.source_id)),
            );
        }
        let comparison = json!({"scope":"Only inventoried sources in scorable historical groups with a saved selection; file counts are not quality scores","relationship_count":comparable.len(),"source_count":source_ids.len(),"exact_byte_baseline_representatives":exact_keys.len(),"historical_selected_inventoried_sources":historical_ids.len(),"conservative_retained_sources":audit.files.iter().filter(|f|source_ids.contains(&f.source.source_id)&&f.state.retained()).count(),"limits":"No omission is confirmed wrong merely because an unresolved candidate is retained. Reviewed desired-content findings must be reported with their evidence and owner rulings."});
        let summary = json!({"schema_version":1,"policy_version":audit.policy_version,"provisional":audit.provisional,"input_receipt":audit.input_receipt,"counts":audit.counts,"proposal_states":states,"reference_evidence_methods":methods,"publisher_files":publishers,"metadata_breakdown":metadata_breakdown,"policy_comparison":comparison,"review_required":audit.relationships.iter().filter(|g|g.needs_review).count(),"sample":{"seed":sample.seed,"per_stratum":sample.per_stratum,"holdout_percent":sample.holdout_percent,"selected":sample.selected.len()},"warnings":audit.warnings,"limits":["Current availability is not a complete ownership catalog.","Candidate relationships are not counts of unique works.","Sampled and partial matches cannot prove complete equivalence.","Historical unprocessed and deferred groups measure coverage, not incorrect choices.","Publisher holdouts test transfer within this collection; unfamiliar dumps require calibration."]});
        write_json(&stage.join("summary.json"), &summary)?;
        write_json(
            &stage.join("current-inventory-files.json"),
            &audit.current_files,
        )?;
        write_json(
            &stage.join("review-migrations.json"),
            &audit.review_migrations,
        )?;
        write_json(
            &stage.join("supplemental-evidence.json"),
            &audit.supplemental_evidence,
        )?;
        write_json(&stage.join("sample-manifest.json"), sample)?;
        write_json(&stage.join("protected-editions.json"), &audit.protected)?;
        write_json(
            &stage.join("proposed-conversion-list.json"),
            &json!({"schema_version":1,"policy_version":audit.policy_version,"provisional":audit.provisional,"input_receipt":audit.input_receipt,"files":audit.files,"notes":audit.review_notes}),
        )?;
        let mut refs = csv::Writer::from_path(stage.join("reference-rows.csv"))?;
        refs.write_record([
            "row",
            "reference_path",
            "evidence_method",
            "outcome",
            "matched_sources",
            "reported_sources",
            "current_source_ids",
            "groups",
        ])?;
        for r in &audit.reference {
            refs.write_record([
                r.row.to_string(),
                r.d_path.clone(),
                serde_json::to_string(&r.method)?,
                r.outcome.clone(),
                r.matched_sources.join("\n"),
                r.reported_sources.join("\n"),
                r.current_source_ids.join("\n"),
                r.groups.join("\n"),
            ])?;
        }
        refs.flush()?;
        let mut files = csv::Writer::from_path(stage.join("old-library-files.csv"))?;
        files.write_record([
            "source_id",
            "relative_path",
            "state",
            "reason",
            "reference_rows",
            "representative",
            "ruling",
        ])?;
        for f in &audit.files {
            files.write_record([
                f.source.source_id.clone(),
                f.source.relative_path.to_string_lossy().into_owned(),
                serde_json::to_string(&f.state)?,
                f.reason.clone(),
                f.reference_rows
                    .iter()
                    .map(ToString::to_string)
                    .collect::<Vec<_>>()
                    .join("\n"),
                f.representative.clone().unwrap_or_default(),
                f.ruling.clone().unwrap_or_default(),
            ])?;
        }
        files.flush()?;
        let mut relationships = std::fs::File::create(stage.join("relationships.jsonl"))?;
        for g in &audit.relationships {
            writeln!(relationships, "{}", serde_json::to_string(g)?)?;
        }
        let mut prose = format!(
            "# Library selection analysis\n\nStatus: {}.\n\nThis audit checks current-edition selection and preservation of owned material absent from the fresh download. It changes no PDFs, production decisions, or Markdown.\n\n## Coverage\n\n",
            if audit.provisional {
                "provisional; reference recheck not confirmed complete"
            } else {
                "completed reference snapshot; unresolved relationships remain explicit"
            }
        );
        for (k, v) in &audit.counts {
            prose.push_str(&format!("- {k}: {v}\n"));
        }
        prose.push_str("\n## Proposed file dispositions\n\n");
        for (k, v) in &states {
            prose.push_str(&format!("- {k}: {v}\n"));
        }
        prose.push_str(&format!("\n## Investigation and review\n\n{} relationships need review. The worklist contains {} sampled or flagged cases. All unresolved readable candidates remain eligible; unreadable retained sources need recovery. Nulb retention instructions and binding status are in protected-editions.json.\n\n## Policy comparison\n\n```json\n{}\n```\n\n## Limits\n\nCurrent availability does not establish completeness of ownership. Groups are candidate relationships, not verified unique works. Sampled and partial evidence cannot prove complete equivalence. This report makes no overall accuracy claim. File-level ledgers preserve evidence and reasons; the relationships ledger preserves historical observations. Sources lacking publisher/system/language/role metadata are reported as unknown.\n",summary["review_required"],sample.selected.len(),serde_json::to_string_pretty(&comparison)?));
        prose.push_str("\n## Warnings\n\n");
        for w in &audit.warnings {
            prose.push_str(&format!("- {w}\n"));
        }
        std::fs::write(stage.join("report.md"), prose)?;
        write_json(
            &stage.join("report-receipt.json"),
            &json!({"audit_digest":digest_json(audit),"sample_digest":digest_json(sample)}),
        )?;
        std::fs::rename(&stage, out)?;
        Ok(())
    })();
    if result.is_err() {
        let _ = std::fs::remove_dir_all(stage);
    }
    result
}
