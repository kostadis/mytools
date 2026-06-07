use serde_json::Value;
use crate::model::{Entry, SectionEntry, InsetEntry, QuoteEntry, ListEntry, TableEntry, ParseError};

pub fn parse_entry(raw: &Value) -> Result<Entry, ParseError> {
    match raw {
        Value::Object(map) => {
            let entry_type = map.get("type")
                .and_then(|v| v.as_str())
                .unwrap_or("");

            match entry_type {
                "section" => {
                    let name = map.get("name").and_then(|v| v.as_str()).map(|s| s.to_string());
                    let id = map.get("id").and_then(|v| v.as_str()).map(|s| s.to_string());
                    let page = map.get("page").and_then(|v| v.as_number()).map(|n| n.as_i64().unwrap() as i32);

                    let entries = map.get("entries")
                        .and_then(|v| v.as_array())
                        .unwrap_or(&vec![])
                        .iter()
                        .map(|v| parse_entry(v))
                        .collect::<Result<Vec<Entry>, ParseError>>()?;

                    let section = SectionEntry {
                        name,
                        entries,
                        id,
                        page,
                    };
                    
                    // Validate section
                    if let Err(e) = section.validate() {
                        return Err(ParseError::NestedParseError(format!("Section validation failed: {}", e)));
                    }
                    
                    Ok(Entry::Section(section))
                },
                "inset" => {
                    let text = map.get("text")
                        .and_then(|v| v.as_str())
                        .map(|s| s.to_string())
                        .ok_or_else(|| ParseError::MissingField("text".to_string(), "inset".to_string()))?;
                    
                    let name = map.get("name").and_then(|v| v.as_str()).map(|s| s.to_string());
                    let id = map.get("id").and_then(|v| v.as_str()).map(|s| s.to_string());
                    let page = map.get("page").and_then(|v| v.as_number()).map(|n| n.as_i64().unwrap() as i32);

                    let inset = InsetEntry {
                        text,
                        name,
                        id,
                        page,
                    };
                    
                    // Validate inset
                    if let Err(e) = inset.validate() {
                        return Err(ParseError::NestedParseError(format!("Inset validation failed: {}", e)));
                    }
                    
                    Ok(Entry::Inset(inset))
                },
                "quote" => {
                    println!("DEBUG: Parsing quote entry: {:?}", map);
                    let text = map.get("text")
                        .and_then(|v| v.as_str())
                        .map(|s| s.to_string())
                        .ok_or_else(|| ParseError::MissingField("text".to_string(), "quote".to_string()))?;
                    
                    let by = map.get("by").and_then(|v| v.as_str()).map(|s| s.to_string());
                    let from = map.get("from").and_then(|v| v.as_str()).map(|s| s.to_string());
                    let name = map.get("name").and_then(|v| v.as_str()).map(|s| s.to_string());
                    let id = map.get("id").and_then(|v| v.as_str()).map(|s| s.to_string());
                    let page = map.get("page").and_then(|v| v.as_number()).map(|n| n.as_i64().unwrap() as i32);

                    let quote = QuoteEntry {
                        text,
                        by,
                        from,
                        name,
                        id,
                        page,
                    };
                    
                    // Validate quote
                    if let Err(e) = quote.validate() {
                        return Err(ParseError::NestedParseError(format!("Quote validation failed: {}", e)));
                    }
                    
                    println!("DEBUG: Successfully parsed quote entry with name: {:?}", quote.name);
                    Ok(Entry::Quote(quote))
                },
                "list" => {
                    let items = map.get("items")
                        .and_then(|v| v.as_array())
                        .unwrap_or(&vec![])
                        .iter()
                        .map(|v| parse_entry(v))
                        .collect::<Result<Vec<Entry>, ParseError>>()?;
                    
                    let name = map.get("name").and_then(|v| v.as_str()).map(|s| s.to_string());
                    let id = map.get("id").and_then(|v| v.as_str()).map(|s| s.to_string());
                    let page = map.get("page").and_then(|v| v.as_number()).map(|n| n.as_i64().unwrap() as i32);

                    let list = ListEntry {
                        items,
                        name,
                        id,
                        page,
                    };
                    
                    // Validate list
                    if let Err(e) = list.validate() {
                        return Err(ParseError::NestedParseError(format!("List validation failed: {}", e)));
                    }
                    
                    Ok(Entry::List(list))
                },
                "table" => {
                    let headers = map.get("headers")
                        .and_then(|v| v.as_array())
                        .unwrap_or(&vec![])
                        .iter()
                        .map(|v| {
                            v.as_str()
                                .map(|s| s.to_string())
                                .ok_or_else(|| ParseError::MissingField("headers".to_string(), "table".to_string()))
                        })
                        .collect::<Result<Vec<String>, ParseError>>()?;
                    
                    let rows = map.get("rows")
                        .and_then(|v| v.as_array())
                        .unwrap_or(&vec![])
                        .iter()
                        .map(|row| {
                            row.as_array()
                                .unwrap_or(&vec![])
                                .iter()
                                .map(|cell| {
                                    cell.as_str()
                                        .map(|s| s.to_string())
                                        .ok_or_else(|| ParseError::MissingField("rows".to_string(), "table".to_string()))
                                })
                                .collect::<Result<Vec<String>, ParseError>>()
                        })
                        .collect::<Result<Vec<Vec<String>>, ParseError>>()?;
                    
                    let name = map.get("name").and_then(|v| v.as_str()).map(|s| s.to_string());
                    let id = map.get("id").and_then(|v| v.as_str()).map(|s| s.to_string());
                    let page = map.get("page").and_then(|v| v.as_number()).map(|n| n.as_i64().unwrap() as i32);

                    let table = TableEntry {
                        headers,
                        rows,
                        name,
                        id,
                        page,
                    };
                    
                    // Validate table
                    if let Err(e) = table.validate() {
                        return Err(ParseError::NestedParseError(format!("Table validation failed: {}", e)));
                    }
                    
                    Ok(Entry::Table(table))
                },
                _ => {
                    // Unknown type — treat as generic JSON
                    Ok(Entry::Generic(raw.clone()))
                }
            }
        },
        _ => Err(ParseError::ExpectedObject(format!("{:?}", raw))),
    }
}

pub fn parse_document(raw: &Value) -> Result<crate::model::HomebrewAdventure, ParseError> {
    // Print the raw JSON for debugging
    println!("DEBUG: Raw JSON: {}", serde_json::to_string_pretty(raw).unwrap_or("<error>".to_string()));
    
    // Extract meta data
    let meta_sources = raw.get("_meta")
        .and_then(|v| v.get("sources"))
        .and_then(|v| v.as_array())
        .map(|sources| {
            sources.iter().map(|source| {
                let id = source.get("id").and_then(|v| v.as_str()).unwrap_or("");
                let name = source.get("name").and_then(|v| v.as_str()).unwrap_or("");
                let url = source.get("url").and_then(|v| v.as_str()).unwrap_or("");
                crate::model::MetaSource {
                    id: id.to_string(),
                    name: name.to_string(),
                    url: url.to_string(),
                }
            }).collect()
        })
        .unwrap_or_else(Vec::new);
    
    let meta = crate::model::Meta { sources: meta_sources };
    
    // Validate sources for duplicate IDs
    if let Err(e) = meta.validate_sources() {
        return Err(e);
    }
    
    // Extract data array
    let data = raw.get("data")
        .and_then(|v| v.as_array())
        .unwrap_or(&vec![])
        .iter()
        .map(|entry| parse_entry(entry))
        .collect::<Result<Vec<crate::model::Entry>, ParseError>>()?;
    
    // Build HomebrewAdventure with TOC
    match crate::model::HomebrewAdventure::build(meta, data) {
        Ok(adventure) => Ok(adventure),
        Err(e) => Err(ParseError::NestedParseError(e)),
    }
}