use crate::protocol::Outline;
use lopdf::{Document, Object, ObjectId};
use std::collections::{HashMap, HashSet};
fn resolve<'a>(d: &'a Document, mut o: &'a Object) -> Result<&'a Object, String> {
    for _ in 0..100 {
        if let Object::Reference(id) = o {
            o = d.get_object(*id).map_err(|e| e.to_string())?;
        } else {
            return Ok(o);
        }
    }
    Err("outline reference recursion limit".into())
}
fn named<'a>(d: &'a Document, o: &'a Object, name: &[u8], depth: usize) -> Option<&'a Object> {
    if depth > 100 {
        return None;
    }
    let dict = resolve(d, o).ok()?.as_dict().ok()?;
    if let Ok(items) = dict
        .get(b"Names")
        .and_then(|o| resolve(d, o).map_err(|_| lopdf::Error::RecursionLimit))
        .and_then(Object::as_array)
    {
        for pair in items.as_chunks::<2>().0 {
            if pair[0].as_str().ok() == Some(name) {
                return Some(&pair[1]);
            }
        }
    }
    if let Ok(kids) = dict
        .get(b"Kids")
        .and_then(|o| resolve(d, o).map_err(|_| lopdf::Error::RecursionLimit))
        .and_then(Object::as_array)
    {
        for kid in kids {
            if let Some(v) = named(d, kid, name, depth + 1) {
                return Some(v);
            }
        }
    }
    None
}
fn destination(
    d: &Document,
    o: &Object,
    pages: &HashMap<ObjectId, u32>,
    depth: usize,
) -> Option<u32> {
    if depth > 100 {
        return None;
    }
    match resolve(d, o).ok()? {
        Object::Array(a) => match a.first()? {
            Object::Reference(id) => pages.get(id).copied(),
            Object::Integer(n) => u32::try_from(*n).ok()?.checked_add(1),
            _ => None,
        },
        Object::Dictionary(dict) => destination(d, dict.get(b"D").ok()?, pages, depth + 1),
        Object::Name(name) | Object::String(name, _) => {
            let cat = d.catalog().ok()?;
            if let Ok(dests) = cat
                .get(b"Dests")
                .and_then(|o| resolve(d, o).map_err(|_| lopdf::Error::RecursionLimit))
                .and_then(Object::as_dict)
                && let Ok(v) = dests.get(name)
            {
                return destination(d, v, pages, depth + 1);
            }
            let names = resolve(d, cat.get(b"Names").ok()?).ok()?.as_dict().ok()?;
            destination(
                d,
                named(d, names.get(b"Dests").ok()?, name, 0)?,
                pages,
                depth + 1,
            )
        }
        _ => None,
    }
}
pub fn read(d: &Document) -> Result<Vec<Outline>, String> {
    let cat = d.catalog().map_err(|e| e.to_string())?;
    let Ok(outlines) = cat.get(b"Outlines") else {
        return Ok(vec![]);
    };
    let root = resolve(d, outlines)?.as_dict().map_err(|e| e.to_string())?;
    let Ok(first) = root.get(b"First") else {
        return Ok(vec![]);
    };
    let pages: HashMap<_, _> = d.get_pages().into_iter().map(|(n, id)| (id, n)).collect();
    let mut out = vec![];
    let mut seen = HashSet::new();
    fn walk(
        d: &Document,
        start: &Object,
        level: usize,
        pages: &HashMap<ObjectId, u32>,
        seen: &mut HashSet<ObjectId>,
        out: &mut Vec<Outline>,
    ) -> Result<(), String> {
        if level > 100 {
            return Err("outline nesting limit".into());
        }
        let mut current = Some(start);
        while let Some(o) = current {
            if let Object::Reference(id) = o
                && !seen.insert(*id)
            {
                return Err("cyclic outline".into());
            }
            let dict = resolve(d, o)?.as_dict().map_err(|e| e.to_string())?;
            let title = lopdf::decode_text_string(resolve(
                d,
                dict.get(b"Title").map_err(|e| e.to_string())?,
            )?)
            .map_err(|e| e.to_string())?;
            let dest = dict.get(b"Dest").ok().or_else(|| {
                let action = resolve(d, dict.get(b"A").ok()?).ok()?.as_dict().ok()?;
                if action.get(b"S").and_then(Object::as_name).ok() != Some(b"GoTo".as_slice()) {
                    return None;
                }
                action.get(b"D").ok()
            });
            let page = dest
                .and_then(|v| destination(d, v, pages, 0))
                .filter(|p| *p > 0 && *p <= pages.len() as u32);
            out.push(Outline { level, title, page });
            if let Ok(child) = dict.get(b"First") {
                walk(d, child, level + 1, pages, seen, out)?
            }
            current = dict.get(b"Next").ok();
        }
        Ok(())
    }
    walk(d, first, 1, &pages, &mut seen, &mut out)?;
    Ok(out)
}
