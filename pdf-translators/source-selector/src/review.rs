use crate::{
    Result, SelectionError, digest_json,
    evidence::{normalize_whitespace, validate_claim},
    grouping::hash_source,
    inventory::checked_path,
    models::*,
    store::Store,
};
use std::collections::{BTreeMap, BTreeSet};

pub fn evidence_digest(group: &Group, evidence: &[Evidence]) -> String {
    let mut ev: Vec<_> = evidence
        .iter()
        .filter(|e| group.source_ids.contains(&e.source_id))
        .collect();
    ev.sort_by_key(|e| &e.source_id);
    digest_json(&ev)
}
fn source_hashes(group: &Group, evidence: &[Evidence]) -> BTreeMap<String, String> {
    evidence
        .iter()
        .filter(|e| group.source_ids.contains(&e.source_id))
        .map(|e| (e.source_id.clone(), e.sha256.clone()))
        .collect()
}
fn same_user_sources(decision: &Decision, group: &Group, evidence: &[Evidence]) -> bool {
    decision.actor_role == ActorRole::User
        && !decision.source_hashes.is_empty()
        && decision.source_hashes == source_hashes(group, evidence)
}
pub use crate::packets::{PageExcerpt, ReviewPacket, prepare_packets};

pub fn apply_reader_claims(
    packet: &ReviewPacket,
    claims: &[Claim],
    evidence: &[Evidence],
) -> Result<Vec<Claim>> {
    if packet.role != ActorRole::Reader {
        return Err(SelectionError::Invalid(
            "claims require reader packet".into(),
        ));
    }
    for claim in claims {
        let supported = packet.excerpts.iter().any(|p| {
            p.source_id == claim.source_id
                && p.page == claim.page
                && normalize_whitespace(&p.text).contains(&normalize_whitespace(&claim.quote))
        });
        if claim.role != ActorRole::Reader
            || claim.actor.trim().is_empty()
            || !supported
            || !evidence.iter().any(|e| validate_claim(claim, e))
        {
            return Err(SelectionError::Invalid(format!(
                "unsupported reader claim: {}",
                claim.claim_id
            )));
        }
    }
    Ok(claims.to_vec())
}

pub fn propose_decision(
    group: &Group,
    evidence: &[Evidence],
    sources: &[Source],
    prior: Option<&Decision>,
) -> Decision {
    let ed = evidence_digest(group, evidence);
    if let Some(p) = prior
        && p.membership_digest == group.membership_digest
        && (p.evidence_digest == ed || same_user_sources(p, group, evidence))
    {
        return p.clone();
    }
    let mut decision = Decision {
        packet_ids: vec![],
        source_hashes: source_hashes(group, evidence),
        group_id: group.group_id.clone(),
        membership_digest: group.membership_digest.clone(),
        evidence_digest: ed,
        actor: "rpg-source-select".into(),
        actor_role: ActorRole::Deterministic,
        outcomes: group
            .source_ids
            .iter()
            .map(|id| Outcome {
                source_id: id.clone(),
                status: Status::NeedsReview,
                work_id: None,
                representative_id: None,
                successor_id: None,
            })
            .collect(),
        rationale: "No supported equivalence or chronology decision yet".into(),
        evidence_refs: vec![],
    };
    let members: Vec<_> = sources
        .iter()
        .filter(|s| group.source_ids.contains(&s.source_id))
        .collect();
    for o in &mut decision.outcomes {
        if members
            .iter()
            .find(|s| s.source_id == o.source_id)
            .is_some_and(|s| s.read_error.is_some())
        {
            o.status = Status::Unreadable;
        }
    }
    if members.len() != group.source_ids.len() {
        return decision;
    }
    let all: Vec<_> = members
        .iter()
        .filter_map(|s| evidence.iter().find(|e| e.source_id == s.source_id))
        .collect();
    if all.len() != members.len()
        || all.iter().any(|e| e.text_quality != "text")
        || members.iter().any(|s| s.read_error.is_some())
    {
        return decision;
    }
    let same = all.iter().all(|e| e.sha256 == all[0].sha256);
    if members.len() > 1 && !same {
        return decision;
    }
    let rep = members
        .iter()
        .min_by_key(|s| {
            (
                !s.baseline_established,
                s.relative_path.to_string_lossy().contains(".old-"),
                &s.relative_path,
            )
        })
        .unwrap();
    if members.len() == 1 && rep.relative_path.to_string_lossy().contains(".old-") {
        return decision;
    }
    let work = format!("w{}", &group.group_id[1..]);
    for o in &mut decision.outcomes {
        o.work_id = Some(work.clone());
        if o.source_id == rep.source_id {
            o.status = Status::Selected;
        } else {
            o.status = Status::ExactDuplicate;
            o.representative_id = Some(rep.source_id.clone());
        }
    }
    decision.rationale = if members.len() > 1 {
        "Byte-identical copies; representative preference does not assert chronology"
    } else {
        "Uncontested readable text-bearing source; page coverage recorded"
    }
    .into();
    decision
}

pub fn accept_decision(
    mut decision: Decision,
    group: &Group,
    evidence: &[Evidence],
    sources: &[Source],
) -> Result<Decision> {
    let bad = |s: &str| SelectionError::Invalid(s.into());
    if decision.actor_role == ActorRole::Reader {
        return Err(bad("reader may not decide"));
    }
    if decision.group_id != group.group_id
        || decision.membership_digest != group.membership_digest
        || (decision.evidence_digest != evidence_digest(group, evidence)
            && !same_user_sources(&decision, group, evidence))
    {
        return Err(bad("stale group membership or evidence"));
    }
    let expected: BTreeSet<_> = group.source_ids.iter().collect();
    let got: BTreeSet<_> = decision.outcomes.iter().map(|o| &o.source_id).collect();
    if got != expected || got.len() != decision.outcomes.len() {
        return Err(bad("outcomes must cover every group member exactly once"));
    }
    let source_map: BTreeMap<_, _> = sources.iter().map(|s| (&s.source_id, s)).collect();
    let outcomes: BTreeMap<_, _> = decision
        .outcomes
        .iter()
        .map(|o| (&o.source_id, o))
        .collect();
    for o in &decision.outcomes {
        let source = source_map
            .get(&o.source_id)
            .ok_or_else(|| bad("unknown source"))?;
        let fields_valid = match o.status {
            Status::Selected | Status::DistinctWork => {
                o.representative_id.is_none() && o.successor_id.is_none()
            }
            Status::ExactDuplicate | Status::EquivalentPresentation => {
                o.representative_id.is_some() && o.successor_id.is_none()
            }
            Status::Superseded => o.representative_id.is_none() && o.successor_id.is_some(),
            _ => o.representative_id.is_none() && o.successor_id.is_none() && o.work_id.is_none(),
        };
        if !fields_valid {
            return Err(bad(
                "outcome carries missing or inapplicable reference/work fields",
            ));
        }
        if o.status == Status::Unreadable && source.read_error.is_none() {
            return Err(bad(
                "unreadable status requires a recorded read or inspection failure",
            ));
        }
        if matches!(o.status, Status::Selected | Status::DistinctWork)
            && source.read_error.is_some()
        {
            return Err(bad("unreadable source cannot be selected"));
        }
        if matches!(o.status, Status::Selected | Status::DistinctWork)
            && !evidence.iter().any(|e| e.source_id == o.source_id)
        {
            return Err(bad("selection requires inspected evidence"));
        }
        let reference = match o.status {
            Status::ExactDuplicate | Status::EquivalentPresentation => o.representative_id.as_ref(),
            Status::Superseded => o.successor_id.as_ref(),
            _ => None,
        };
        if matches!(
            o.status,
            Status::ExactDuplicate | Status::EquivalentPresentation | Status::Superseded
        ) && reference.is_none()
        {
            return Err(bad("excluded source needs representative or successor"));
        }
        if let Some(id) = reference {
            if id == &o.source_id
                || !outcomes.get(id).is_some_and(|target| {
                    matches!(target.status, Status::Selected | Status::DistinctWork)
                })
            {
                return Err(bad(
                    "exclusion target must be a different selected member; chains/cycles are refused",
                ));
            }
            if o.status == Status::ExactDuplicate {
                let a = evidence.iter().find(|e| e.source_id == o.source_id);
                let b = evidence.iter().find(|e| &e.source_id == id);
                if !matches!((a,b),(Some(a),Some(b)) if a.sha256==b.sha256) {
                    return Err(bad("exact duplicate requires matching hashes"));
                }
            }
        }
    }
    if decision.rationale.trim().is_empty() || decision.actor.trim().is_empty() {
        return Err(bad("decision requires actor and rationale"));
    }
    if decision.actor_role == ActorRole::Deterministic {
        let expected = propose_decision(group, evidence, sources, None);
        let signature = |d: &Decision| {
            d.outcomes
                .iter()
                .map(|o| {
                    (
                        &o.source_id,
                        &o.status,
                        &o.representative_id,
                        &o.successor_id,
                    )
                })
                .map(|v| serde_json::to_value(v).unwrap())
                .collect::<Vec<_>>()
        };
        if signature(&expected) != signature(&decision) {
            return Err(bad("unsupported deterministic decision"));
        }
    }
    let referenced: BTreeSet<_> = decision.evidence_refs.iter().collect();
    for id in &referenced {
        if !evidence.iter().any(|e| {
            group.source_ids.contains(&e.source_id)
                && e.claims
                    .iter()
                    .any(|c| &c.claim_id == *id && validate_claim(c, e))
        }) {
            return Err(bad("unchecked evidence reference"));
        }
    }
    if decision.actor_role == ActorRole::Sol
        && decision.outcomes.iter().any(|o| {
            matches!(
                o.status,
                Status::Superseded | Status::EquivalentPresentation | Status::ExcludedAsset
            )
        })
        && referenced.is_empty()
    {
        return Err(bad(
            "Sol exclusions require checked in-document evidence references",
        ));
    }
    let mut selected = BTreeMap::new();
    for o in &mut decision.outcomes {
        if matches!(o.status, Status::Selected | Status::DistinctWork) {
            let work = o.work_id.clone().unwrap_or_else(|| {
                format!("w{}", &digest_json(&(&group.group_id, &o.source_id))[..20])
            });
            if selected.values().any(|v| v == &work) {
                return Err(bad("distinct selected sources cannot share work ID"));
            }
            selected.insert(o.source_id.clone(), work.clone());
            o.work_id = Some(work);
        }
    }
    for o in &mut decision.outcomes {
        let target = match o.status {
            Status::ExactDuplicate | Status::EquivalentPresentation => o.representative_id.as_ref(),
            Status::Superseded => o.successor_id.as_ref(),
            _ => None,
        };
        if let Some(id) = target {
            o.work_id = selected.get(id).cloned();
        }
    }
    decision.source_hashes = source_hashes(group, evidence);
    Ok(decision)
}

impl Store {
    pub fn save_decision(&mut self, decision: &Decision) -> Result<()> {
        let groups: Vec<Group> = self.records("groups")?;
        let group = groups
            .iter()
            .find(|g| g.group_id == decision.group_id)
            .ok_or_else(|| SelectionError::Invalid("unknown group".into()))?;
        let sources = self.sources()?;
        let evidence = self.evidence()?;
        if self
            .current_decisions()?
            .iter()
            .any(|d| d.group_id == decision.group_id && d.actor_role == ActorRole::User)
            && decision.actor_role != ActorRole::User
        {
            return Err(SelectionError::Invalid(
                "a current user ruling can only be replaced by a user ruling".into(),
            ));
        }
        validate_issued_packets(self, decision, group, &evidence)?;
        let inventory: InventoryResult = serde_json::from_value(
            self.meta("inventory")?
                .ok_or_else(|| SelectionError::Invalid("scan first".into()))?,
        )?;
        for id in &group.source_ids {
            let pending_without_evidence = !evidence.iter().any(|e| &e.source_id == id)
                && decision.outcomes.iter().any(|o| {
                    &o.source_id == id
                        && matches!(o.status, Status::NeedsReview | Status::Unreadable)
                });
            if pending_without_evidence {
                continue;
            }
            if let Some(source) = sources.iter().find(|s| &s.source_id == id)
                && source.read_error.is_none()
            {
                let current = hash_source(&checked_path(&inventory.root, &source.relative_path)?)?;
                if !evidence
                    .iter()
                    .any(|e| &e.source_id == id && e.sha256 == current)
                {
                    return Err(SelectionError::Invalid(
                        "source changed or missing inspected evidence; inspect again".into(),
                    ));
                }
            }
        }
        let accepted = accept_decision(decision.clone(), group, &evidence, &sources)?;
        self.put_record("decision_history", &digest_json(&accepted), &accepted)?;
        self.put_record("decisions", &accepted.group_id, &accepted)
    }
    pub fn current_decisions(&self) -> Result<Vec<Decision>> {
        let groups: Vec<Group> = self.records("groups")?;
        let evidence = self.evidence()?;
        Ok(self
            .records::<Decision>("decisions")?
            .into_iter()
            .filter(|d| {
                groups.iter().any(|g| {
                    g.group_id == d.group_id
                        && g.membership_digest == d.membership_digest
                        && (evidence_digest(g, &evidence) == d.evidence_digest
                            || same_user_sources(d, g, &evidence))
                })
            })
            .collect())
    }
}

fn validate_issued_packets(
    store: &Store,
    decision: &Decision,
    group: &Group,
    evidence: &[Evidence],
) -> Result<()> {
    if decision.packet_ids.is_empty() {
        if decision.actor_role == ActorRole::Sol {
            return Err(SelectionError::Invalid(
                "Sol decisions require issued packet IDs".into(),
            ));
        }
        return Ok(());
    }
    let packets: Vec<ReviewPacket> = store.records("packets")?;
    let mut parts = BTreeSet::new();
    let mut expected = None;
    let current = evidence_digest(group, evidence);
    let mut ids = BTreeSet::new();
    for id in &decision.packet_ids {
        if !ids.insert(id) {
            return Err(SelectionError::Invalid("duplicate issued packet ID".into()));
        }
        let packet = packets
            .iter()
            .find(|p| &p.packet_id == id)
            .ok_or_else(|| SelectionError::Invalid("unknown issued packet".into()))?;
        if packet.group_id != group.group_id
            || packet.membership_digest != group.membership_digest
            || packet.evidence_digest != current
            || decision.evidence_digest != packet.evidence_digest
            || packet.role != decision.actor_role
        {
            return Err(SelectionError::Invalid(
                "stale packet evidence or mismatched decision role".into(),
            ));
        }
        if expected.is_some_and(|n| n != packet.total_parts) {
            return Err(SelectionError::Invalid("mixed issued packet sets".into()));
        }
        expected = Some(packet.total_parts);
        if !parts.insert(packet.part) {
            return Err(SelectionError::Invalid("duplicate packet part".into()));
        }
    }
    if parts != (1..=expected.unwrap_or(0)).collect() {
        return Err(SelectionError::Invalid(
            "decision must acknowledge every issued packet part".into(),
        ));
    }
    Ok(())
}
