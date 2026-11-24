//! Resolve reader facts to issued excerpts without model-transcribed packet IDs.
use crate::{
    Result, SelectionError, digest_json,
    evidence::{normalize_whitespace, validate_claim},
    models::*,
    packets::ReviewPacket,
};
use std::collections::BTreeMap;

pub fn bind_reader_claim<'a>(
    claim: &Claim,
    packets: &'a [ReviewPacket],
    groups: &[Group],
    evidence: &[Evidence],
) -> Result<&'a ReviewPacket> {
    let unsupported = || {
        SelectionError::Invalid(format!(
            "no current issued reader packet supports claim {}; export fresh reader packets and check source/page/quote",
            claim.claim_id
        ))
    };
    let ev = evidence
        .iter()
        .find(|e| e.source_id == claim.source_id)
        .ok_or_else(unsupported)?;
    if claim.role != ActorRole::Reader
        || claim.actor.trim().is_empty()
        || !validate_claim(claim, ev)
    {
        return Err(unsupported());
    }
    let group = groups
        .iter()
        .find(|g| g.source_ids.contains(&claim.source_id))
        .ok_or_else(unsupported)?;
    let quote = normalize_whitespace(&claim.quote);
    // Re-exporting an identical fragment is an alias, not an ambiguity. Different
    // offsets or fragment texts require a more specific supporting quotation.
    let mut matches = BTreeMap::<(usize, String), &ReviewPacket>::new();
    for packet in packets.iter().filter(|p| {
        p.role == ActorRole::Reader
            && p.group_id == group.group_id
            && p.membership_digest == group.membership_digest
    }) {
        for excerpt in &packet.excerpts {
            if excerpt.source_id == claim.source_id
                && excerpt.source_sha256 == ev.sha256
                && excerpt.page == claim.page
                && normalize_whitespace(&excerpt.text).contains(&quote)
            {
                let key = (excerpt.offset_chars, digest_json(&excerpt.text));
                matches
                    .entry(key)
                    .and_modify(|prior| {
                        if packet.packet_id < prior.packet_id {
                            *prior = packet;
                        }
                    })
                    .or_insert(packet);
            }
        }
    }
    if matches.len() > 1 {
        return Err(SelectionError::Invalid(format!(
            "ambiguous reader citation for claim {}; provide a longer quote contained in one fragment",
            claim.claim_id
        )));
    }
    matches.into_values().next().ok_or_else(unsupported)
}
