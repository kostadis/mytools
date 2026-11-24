use crate::{evidence::normalize_whitespace, models::Evidence};
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Comparison {
    pub exact_bytes: bool,
    pub normalized_text_equal: bool,
    pub text_overlap: f64,
    pub changed_pages: Vec<u32>,
    pub visual_differences: bool,
    pub limitations: Vec<String>,
}
pub fn compare_evidence(left: &Evidence, right: &Evidence) -> Comparison {
    let text = |e: &Evidence| {
        e.pages
            .iter()
            .map(|p| normalize_whitespace(&p.text))
            .collect::<Vec<_>>()
            .join("\n")
    };
    let a = text(left);
    let b = text(right);
    let words = |s: &str| {
        s.split_whitespace()
            .map(|s| s.to_lowercase())
            .collect::<BTreeSet<_>>()
    };
    let wa = words(&a);
    let wb = words(&b);
    let union = wa.union(&wb).count();
    let overlap = if union == 0 {
        0.0
    } else {
        wa.intersection(&wb).count() as f64 / union as f64
    };
    let full = left.pages.len() == left.page_count as usize
        && right.pages.len() == right.page_count as usize;
    let changed = left
        .pages
        .iter()
        .filter(|p| {
            right
                .pages
                .iter()
                .find(|q| p.page == q.page)
                .is_none_or(|q| normalize_whitespace(&p.text) != normalize_whitespace(&q.text))
        })
        .map(|p| p.page)
        .chain(
            right
                .pages
                .iter()
                .filter(|q| !left.pages.iter().any(|p| p.page == q.page))
                .map(|q| q.page),
        )
        .collect();
    let visuals = left.pages.iter().any(|p| {
        right
            .pages
            .iter()
            .find(|q| p.page == q.page)
            .is_none_or(|q| p.images != q.images || p.annotations != q.annotations)
    }) || left.page_count != right.page_count;
    let mut limitations = vec![
        "Text and resource counts do not establish visual equivalence or publication order".into(),
    ];
    if !full {
        limitations.push("Partial page coverage; no full-text equivalence established".into());
    }
    Comparison {
        exact_bytes: left.sha256 == right.sha256,
        normalized_text_equal: full && !a.trim().is_empty() && a == b,
        text_overlap: overlap,
        changed_pages: changed,
        visual_differences: visuals,
        limitations,
    }
}
