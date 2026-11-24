use super::*;
use crate::{
    digest_json,
    grouping::hash_source,
    inventory::checked_path,
    models::*,
    review::{
        ReviewPacket, apply_reader_claims, bind_reader_claim, prepare_packets, propose_decision,
    },
};
use serde::Deserialize;
use serde_json::Value;
use std::collections::BTreeSet;

pub(super) fn run(store: &mut Store, command: ReviewCommand) -> Result<ExitCode> {
    match command {
        ReviewCommand::Export {
            role,
            limit,
            group,
            out,
        } => export_packets(store, role.into(), limit, group, out),
        ReviewCommand::Import { file } => import(store, &file),
    }
}
fn export_packets(
    store: &mut Store,
    role: ActorRole,
    limit: usize,
    requested: Option<String>,
    out: PathBuf,
) -> Result<ExitCode> {
    if limit == 0 {
        return Err(SelectionError::Usage("--limit must be positive".into()));
    }
    let inventory: InventoryResult = serde_json::from_value(store.meta("inventory")?.unwrap())?;
    let parent = out
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    validate_work_dir(&inventory.root, parent)?;
    let sources = store.sources()?;
    let evidence = store.evidence()?;
    let groups: Vec<Group> = store.records("groups")?;
    let decisions = store.current_decisions()?;
    if requested
        .as_ref()
        .is_some_and(|id| !groups.iter().any(|g| &g.group_id == id))
    {
        return Err(SelectionError::Usage("unknown group".into()));
    }
    let mut output = String::new();
    let mut emitted = 0;
    let mut count = 0;
    let mut remaining = 0;
    let mut issued_packets = vec![];
    for group in groups
        .iter()
        .filter(|g| requested.as_ref().is_none_or(|id| id == &g.group_id))
    {
        let mut proposal = propose_decision(
            group,
            &evidence,
            &sources,
            decisions.iter().find(|d| d.group_id == group.group_id),
        );
        if requested.is_none()
            && !proposal
                .outcomes
                .iter()
                .any(|o| matches!(o.status, Status::NeedsReview | Status::Unreadable))
        {
            continue;
        }
        if count >= limit {
            remaining += 1;
            continue;
        }
        let packets = prepare_packets(group, &evidence, &sources, role.clone(), 32000)?;
        let ids: Vec<_> = packets.iter().map(|p| p.packet_id.clone()).collect();
        proposal.actor_role = role.clone();
        proposal.packet_ids.clear();
        proposal.evidence_digest = crate::review::evidence_digest(group, &evidence);
        proposal.actor = if role == ActorRole::User {
            "user"
        } else {
            "sol"
        }
        .into();
        for packet in packets {
            let template = if role == ActorRole::Reader {
                json!({"claims":[]})
            } else {
                json!({"packet_ids":ids,"decision":proposal})
            };
            output.push_str(&serde_json::to_string(
                &json!({"packet":packet,"response_template":template}),
            )?);
            output.push('\n');
            issued_packets.push(packet);
            emitted += 1;
        }
        count += 1;
    }
    fs::create_dir_all(parent)?;
    let temp = parent.join(format!(".review-{}", std::process::id()));
    {
        use std::io::Write;
        let mut f = fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&temp)?;
        f.write_all(output.as_bytes())?;
        f.sync_all()?;
    }
    fs::rename(temp, &out)?;
    store.scan_transaction(|store| {
        for packet in &issued_packets {
            store.put_record("packets", &packet.packet_id, packet)?;
        }
        Ok(())
    })?;
    print_json(
        &json!({"file":out,"groups":count,"packets":emitted,"groups_remaining":remaining,"role":role,"model_calls":0}),
    )?;
    Ok(ExitCode::SUCCESS)
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Response {
    packet_id: Option<String>,
    #[serde(default)]
    packet_ids: Vec<String>,
    claims: Option<Vec<Claim>>,
    decision: Option<Decision>,
}
fn responses(path: &Path) -> Result<Vec<Response>> {
    let text = fs::read_to_string(path)?;
    let values: Vec<serde_json::Value> = match serde_json::from_str::<serde_json::Value>(&text) {
        Ok(Value::Array(rows)) => rows,
        Ok(v) => vec![v],
        Err(_) => text
            .lines()
            .filter(|l| !l.trim().is_empty())
            .map(|l| serde_json::from_str(l).map_err(|e| SelectionError::Usage(e.to_string())))
            .collect::<Result<_>>()?,
    };
    if values.is_empty() {
        return Err(SelectionError::Usage("response file is empty".into()));
    }
    values
        .into_iter()
        .map(|v| serde_json::from_value(v).map_err(|e| SelectionError::Usage(e.to_string())))
        .collect()
}
fn import(store: &mut Store, path: &Path) -> Result<ExitCode> {
    let rows = responses(path)?;
    let result = store.scan_transaction(|store| {
        let inventory: InventoryResult = serde_json::from_value(store.meta("inventory")?.unwrap())?;
        let sources = store.sources()?;
        let groups: Vec<Group> = store.records("groups")?;
        let packets: Vec<ReviewPacket> = store.records("packets")?;
        let mut evidence = store.evidence()?;
        let mut claims_count = 0;
        let mut decisions_count = 0;
        let mut auto_bound_claims = 0;
        for row in rows {
            if row.packet_id.is_none()
                && row.packet_ids.is_empty()
                && row.decision.is_none()
                && let Some(claims) = row.claims
            {
                for claim in claims {
                    let packet = bind_reader_claim(&claim, &packets, &groups, &evidence)?;
                    let source = sources
                        .iter()
                        .find(|s| s.source_id == claim.source_id)
                        .ok_or_else(|| SelectionError::Invalid("unknown reader source".into()))?;
                    let ev = evidence
                        .iter()
                        .find(|e| e.source_id == claim.source_id)
                        .unwrap();
                    if hash_source(&checked_path(&inventory.root, &source.relative_path)?)?
                        != ev.sha256
                    {
                        return Err(SelectionError::Invalid(
                            "source changed since evidence was collected".into(),
                        ));
                    }
                    apply_reader_claims(packet, std::slice::from_ref(&claim), &evidence)?;
                    claims_count += usize::from(persist_reader_claim(
                        store,
                        &mut evidence,
                        claim,
                        packet,
                        "automatic",
                    )?);
                    auto_bound_claims += 1;
                }
                continue;
            }
            let mut ids = row.packet_ids;
            if let Some(id) = row.packet_id {
                ids.push(id);
            }
            let unique: BTreeSet<_> = ids.iter().collect();
            if unique.len() != ids.len() || ids.is_empty() {
                return Err(SelectionError::Usage(
                    "response requires unique packet IDs".into(),
                ));
            }
            let selected: Vec<_> = ids
                .iter()
                .map(|id| {
                    packets
                        .iter()
                        .find(|p| &p.packet_id == id)
                        .ok_or_else(|| SelectionError::Invalid("unknown packet ID".into()))
                })
                .collect::<Result<_>>()?;
            let first = selected[0];
            let group = groups
                .iter()
                .find(|g| {
                    g.group_id == first.group_id && g.membership_digest == first.membership_digest
                })
                .ok_or_else(|| SelectionError::Invalid("stale packet membership".into()))?;
            if selected.iter().any(|p| {
                p.group_id != first.group_id
                    || p.role != first.role
                    || p.evidence_digest != first.evidence_digest
            }) {
                return Err(SelectionError::Usage(
                    "response mixes different packet sets".into(),
                ));
            }
            for id in &group.source_ids {
                if let Some(source) = sources.iter().find(|s| &s.source_id == id)
                    && let Some(ev) = evidence.iter().find(|e| &e.source_id == id)
                    && hash_source(&checked_path(&inventory.root, &source.relative_path)?)?
                        != ev.sha256
                {
                    return Err(SelectionError::Invalid(
                        "source changed since evidence was collected".into(),
                    ));
                }
            }
            match (row.claims, row.decision) {
                (Some(claims), None) => {
                    if selected.len() != 1 {
                        return Err(SelectionError::Usage(
                            "reader response names exactly one packet".into(),
                        ));
                    }
                    let accepted = apply_reader_claims(first, &claims, &evidence)?;
                    for claim in accepted {
                        claims_count += usize::from(persist_reader_claim(
                            store,
                            &mut evidence,
                            claim,
                            first,
                            "explicit",
                        )?);
                    }
                }
                (None, Some(mut decision)) => {
                    if !matches!(first.role, ActorRole::Sol | ActorRole::User)
                        || decision.actor_role != first.role
                    {
                        return Err(SelectionError::Invalid(
                            "decision role does not match issued packet".into(),
                        ));
                    }
                    let parts: BTreeSet<_> = selected.iter().map(|p| p.part).collect();
                    if selected.len() != first.total_parts
                        || parts != (1..=first.total_parts).collect()
                    {
                        return Err(SelectionError::Invalid(
                            "decision must acknowledge every packet part".into(),
                        ));
                    }
                    if decision.group_id != group.group_id {
                        return Err(SelectionError::Invalid(
                            "decision belongs to another group".into(),
                        ));
                    }
                    if selected.iter().any(|p| {
                        p.membership_digest != group.membership_digest
                            || p.evidence_digest != crate::review::evidence_digest(group, &evidence)
                    }) || decision.evidence_digest != first.evidence_digest
                    {
                        return Err(SelectionError::Invalid(
                            "stale judgment packet evidence".into(),
                        ));
                    }
                    decision.packet_ids = ids.clone();
                    store.save_decision(&decision)?;
                    decisions_count += 1;
                }
                _ => {
                    return Err(SelectionError::Usage(
                        "response contains claims or a decision, not both".into(),
                    ));
                }
            }
        }
        Ok((claims_count, decisions_count, auto_bound_claims))
    })?;
    print_json(
        &json!({"accepted_claims":result.0,"accepted_decisions":result.1,"auto_bound_claims":result.2}),
    )?;
    Ok(ExitCode::SUCCESS)
}

fn persist_reader_claim(
    store: &mut Store,
    evidence: &mut [Evidence],
    claim: Claim,
    packet: &ReviewPacket,
    mode: &str,
) -> Result<bool> {
    if evidence
        .iter()
        .flat_map(|e| &e.claims)
        .any(|c| c.claim_id == claim.claim_id && digest_json(c) != digest_json(&claim))
    {
        return Err(SelectionError::Usage(
            "claim ID already refers to different evidence".into(),
        ));
    }
    let ev = evidence
        .iter_mut()
        .find(|e| e.source_id == claim.source_id)
        .expect("validated source evidence");
    let added = !ev.claims.iter().any(|c| c.claim_id == claim.claim_id);
    if added {
        ev.claims.push(claim.clone());
    }
    store.save_evidence(ev)?;
    let excerpt = packet
        .excerpts
        .iter()
        .find(|e| {
            e.source_id == claim.source_id
                && e.page == claim.page
                && crate::evidence::normalize_whitespace(&e.text)
                    .contains(&crate::evidence::normalize_whitespace(&claim.quote))
        })
        .expect("validated reader excerpt");
    let key = digest_json(&(&claim.claim_id, &packet.packet_id, &ev.sha256));
    store.put_record_once("claim_bindings", &key, &json!({"claim_id":claim.claim_id,"packet_id":packet.packet_id,"group_id":packet.group_id,"source_id":claim.source_id,"source_sha256":ev.sha256,"page":claim.page,"offset_chars":excerpt.offset_chars,"quote_sha256":digest_json(&claim.quote),"mode":mode,"bound_at":chrono::Utc::now().to_rfc3339()}))?;
    Ok(added)
}
