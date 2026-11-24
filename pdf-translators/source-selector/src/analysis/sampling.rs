use super::models::*;
use crate::{Result, digest};
use std::collections::BTreeMap;
pub fn select(audit: &AuditResult, config: &AnalysisConfig) -> Result<SampleManifest> {
    let mut membership = vec![];
    let mut buckets: BTreeMap<String, Vec<(String, String)>> = BTreeMap::new();
    let mut selected = vec![];
    for g in &audit.relationships {
        let publisher = g.publisher.trim().to_lowercase();
        let key = if publisher.is_empty() || publisher == "unknown" {
            format!("product:{}", g.product_folder)
        } else {
            format!("publisher:{publisher}")
        };
        let value = u64::from_str_radix(
            &digest(format!("{}:{key}", config.sample_seed).as_bytes())[..16],
            16,
        )
        .unwrap();
        let holdout = value % 100 < u64::from(config.holdout_percent);
        let stratum = format!(
            "{}:{}:{}:{}",
            publisher,
            holdout,
            if g.reference_rows.is_empty() {
                "old-only"
            } else {
                "reference"
            },
            if g.source_ids.len() > 1 {
                "multi"
            } else {
                "single"
            }
        );
        membership.push(SampleMember {
            relationship_id: g.id.clone(),
            publisher: g.publisher.clone(),
            partition_key: key,
            holdout,
            stratum: stratum.clone(),
            flagged: g.flagged,
        });
        if g.flagged {
            selected.push(g.id.clone());
        } else {
            buckets.entry(stratum).or_default().push((
                digest(format!("{}:{}", config.sample_seed, g.id).as_bytes()),
                g.id.clone(),
            ));
        }
    }
    for bucket in buckets.values_mut() {
        bucket.sort();
        selected.extend(
            bucket
                .iter()
                .take(config.sample_per_stratum)
                .map(|(_, id)| id.clone()),
        );
    }
    selected.sort();
    selected.dedup();
    Ok(SampleManifest {
        seed: config.sample_seed.clone(),
        per_stratum: config.sample_per_stratum,
        holdout_percent: config.holdout_percent,
        membership,
        selected,
    })
}
