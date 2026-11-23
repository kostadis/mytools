use chrono::{DateTime, Datelike, FixedOffset, NaiveDate, TimeZone};
use regex::Regex;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{collections::BTreeMap, sync::LazyLock};

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Stamp {
    pub field: String,
    pub raw: String,
    pub start_ms: i64,
    pub end_ms: i64,
    pub utc: String,
    pub precision: String,
    pub offset_seconds: Option<i32>,
    pub parts: Vec<i32>,
}
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct DateEvidence {
    pub fields: BTreeMap<String, String>,
    pub effective: Option<Stamp>,
    pub flags: Vec<String>,
    pub notes: Vec<String>,
}

fn parse(field: &str, raw: &str) -> std::result::Result<Stamp, String> {
    if !raw.starts_with("D:") && raw.contains('T') {
        let d = DateTime::parse_from_rfc3339(raw).map_err(|_| format!("{field}:invalid_date"))?;
        let width = if raw.split('T').nth(1).is_some_and(|s| s.contains('.')) {
            1
        } else {
            1000
        };
        return Ok(Stamp {
            field: field.into(),
            raw: raw.into(),
            start_ms: d.timestamp_millis(),
            end_ms: d.timestamp_millis() + width,
            utc: d.with_timezone(&chrono::Utc).to_rfc3339(),
            precision: if width == 1 { "fractional" } else { "second" }.into(),
            offset_seconds: Some(d.offset().local_minus_utc()),
            parts: vec![
                d.year(),
                d.month() as i32,
                d.day() as i32,
                d.hour() as i32,
                d.minute() as i32,
                d.second() as i32,
            ],
        });
    }
    use chrono::Timelike;
    static PDF: LazyLock<Regex> = LazyLock::new(|| {
        Regex::new(
            r"^(?:D:)?(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?(Z|[+-]\d{2}(?:'?\d{2}'?)?)?$",
        )
        .unwrap()
    });
    let c = PDF
        .captures(raw)
        .ok_or_else(|| format!("{field}:invalid_date"))?;
    let mut parts = vec![];
    for i in 1..=6 {
        if let Some(v) = c.get(i) {
            parts.push(
                v.as_str()
                    .parse::<i32>()
                    .map_err(|_| format!("{field}:invalid_date"))?,
            );
        }
    }
    let y = parts[0];
    let month = *parts.get(1).unwrap_or(&1);
    let day = *parts.get(2).unwrap_or(&1);
    let date = NaiveDate::from_ymd_opt(y, month as u32, day as u32)
        .ok_or_else(|| format!("{field}:invalid_calendar"))?;
    let t = date
        .and_hms_opt(
            *parts.get(3).unwrap_or(&0) as u32,
            *parts.get(4).unwrap_or(&0) as u32,
            *parts.get(5).unwrap_or(&0) as u32,
        )
        .ok_or_else(|| format!("{field}:invalid_clock"))?;
    let offset = match c.get(7).map(|m| m.as_str()) {
        None => None,
        Some("Z") => Some(0),
        Some(s) => {
            let compact = s.replace('\'', "");
            let h: i32 = compact[1..3].parse().unwrap();
            let m: i32 = compact
                .get(3..)
                .filter(|s| !s.is_empty())
                .unwrap_or("00")
                .parse()
                .map_err(|_| format!("{field}:invalid_timezone"))?;
            if h > 23 || m > 59 {
                return Err(format!("{field}:invalid_timezone"));
            }
            Some((h * 3600 + m * 60) * if compact.starts_with('-') { -1 } else { 1 })
        }
    };
    let zone = FixedOffset::east_opt(offset.unwrap_or(0))
        .ok_or_else(|| format!("{field}:invalid_timezone"))?;
    let end = match parts.len() {
        1 => NaiveDate::from_ymd_opt(y + 1, 1, 1).and_then(|d| d.and_hms_opt(0, 0, 0)),
        2 => {
            let (ny, nm) = if month == 12 {
                (y + 1, 1)
            } else {
                (y, month + 1)
            };
            NaiveDate::from_ymd_opt(ny, nm as u32, 1).and_then(|d| d.and_hms_opt(0, 0, 0))
        }
        3 => t.checked_add_signed(chrono::Duration::days(1)),
        4 => t.checked_add_signed(chrono::Duration::hours(1)),
        5 => t.checked_add_signed(chrono::Duration::minutes(1)),
        _ => t.checked_add_signed(chrono::Duration::seconds(1)),
    }
    .ok_or_else(|| format!("{field}:date_overflow"))?;
    let start = zone.from_local_datetime(&t).single().unwrap();
    let end = zone.from_local_datetime(&end).single().unwrap();
    Ok(Stamp {
        field: field.into(),
        raw: raw.into(),
        start_ms: start.timestamp_millis(),
        end_ms: end.timestamp_millis(),
        utc: if offset.is_some() {
            start.with_timezone(&chrono::Utc).to_rfc3339()
        } else {
            String::new()
        },
        precision: ["year", "month", "day", "hour", "minute", "second"][parts.len() - 1].into(),
        offset_seconds: offset,
        parts,
    })
}

fn agree(
    values: &[(String, String)],
    flags: &mut Vec<String>,
    notes: &mut Vec<String>,
) -> Option<Stamp> {
    if values.is_empty() {
        return None;
    }
    let mut parsed = vec![];
    for (field, value) in values {
        match parse(field, value) {
            Ok(s) => parsed.push(s),
            Err(e) => flags.push(e),
        }
    }
    if parsed.len() != values.len() {
        return None;
    }
    let mut zoned: Vec<_> = parsed
        .iter()
        .filter(|s| s.offset_seconds.is_some())
        .cloned()
        .collect();
    zoned.sort_by_key(|s| (s.end_ms - s.start_ms, s.field.clone()));
    let Some(best) = zoned.first().cloned() else {
        flags.push(format!("{}:timezone_unknown", values[0].0));
        return None;
    };
    if zoned.iter().map(|s| s.start_ms).max().unwrap()
        >= zoned.iter().map(|s| s.end_ms).min().unwrap()
        || parsed
            .iter()
            .filter(|s| s.offset_seconds.is_none())
            .any(|s| !s.parts.iter().zip(&best.parts).all(|(a, b)| a == b))
    {
        flags.push(format!("{}:conflicting_representations", values[0].0));
        return None;
    }
    if parsed.iter().any(|s| s.offset_seconds.is_none()) {
        notes.push(format!("timezone/precision resolved by {}", best.field));
    }
    Some(best)
}
pub fn resolve(raw: &BTreeMap<String, Value>) -> DateEvidence {
    let mut out = DateEvidence::default();
    let mut modifications = vec![];
    let mut creations = vec![];
    for (name, kind) in [("ModDate", true), ("CreationDate", false)] {
        if let Some(value) = raw.get(name) {
            let v = value
                .as_str()
                .map(str::to_string)
                .unwrap_or_else(|| value.to_string());
            out.fields.insert(format!("pdf_info.{name}"), v.clone());
            if kind {
                modifications.push((format!("pdf_info.{name}"), v));
            } else {
                creations.push((format!("pdf_info.{name}"), v));
            }
        }
    }
    if raw.contains_key("xmp_error") {
        out.flags.push("xmp_unreadable".into());
    }
    if let Some(xmp) = raw.get("xmp").and_then(Value::as_str) {
        match roxmltree::Document::parse(xmp) {
            Err(_) => out.flags.push("xmp_invalid_xml".into()),
            Ok(doc) => {
                for node in doc.descendants().filter(|n| n.is_element()) {
                    let mut fields = vec![];
                    if node.tag_name().namespace() == Some("http://ns.adobe.com/xap/1.0/")
                        && let Some(v) = node.text()
                    {
                        fields.push((node.tag_name().name(), v));
                    }
                    for a in node
                        .attributes()
                        .filter(|a| a.namespace() == Some("http://ns.adobe.com/xap/1.0/"))
                    {
                        fields.push((a.name(), a.value()));
                    }
                    for (name, v) in fields {
                        if name == "ModifyDate" || name == "CreateDate" {
                            let key = format!("xmp.{name}");
                            out.fields.insert(key.clone(), v.into());
                            if name == "ModifyDate" {
                                modifications.push((key, v.into()));
                            } else {
                                creations.push((key, v.into()));
                            }
                        }
                    }
                }
            }
        }
    }
    let modification = agree(&modifications, &mut out.flags, &mut out.notes);
    let creation = agree(&creations, &mut out.flags, &mut out.notes);
    if let (Some(m), Some(c)) = (&modification, &creation)
        && m.end_ms <= c.start_ms
    {
        out.flags.push("modification_before_creation".into());
    }
    if out.flags.is_empty() {
        out.effective = if modifications.is_empty() {
            creation
        } else {
            modification
        };
    }
    if out.fields.is_empty() {
        out.flags.push("missing_internal_dates".into());
    }
    out
}
