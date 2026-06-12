use crate::entry::{Entry, EntryOrString};
use crate::validation::BuildContext;
use serde::{Serialize, Deserialize};
use serde::de::Deserializer;

/// Parse a raw JSON dict into the appropriate document type
pub fn parse_document(raw: serde_json::Value, ctx: &mut BuildContext) -> ParseResult {
    let obj = match raw.as_object() {
        Some(o) => o,
        None => {
            ctx.error("Top level must be a JSON object".to_string());
            return ParseResult::Official(OfficialAdventureData {
                id: String::new(),
                source: String::new(),
                data: Vec::new(),
            });
        }
    };

    if obj.contains_key("adventure") && obj.contains_key("adventureData") {
        // Homebrew format
        match serde_json::from_value(raw.clone()) {
            Ok(adv) => ParseResult::Homebrew(adv),
            Err(e) => {
                ctx.error(format!("Failed to parse homebrew format: {}", e));
                ParseResult::Homebrew(HomebrewAdventure::default())
            }
        }
    } else if obj.contains_key("data") {
        // Official format
        match serde_json::from_value(raw.clone()) {
            Ok(data) => ParseResult::Official(data),
            Err(e) => {
                ctx.error(format!("Failed to parse official format: {}", e));
                ParseResult::Official(OfficialAdventureData {
                    id: String::new(),
                    source: String::new(),
                    data: Vec::new(),
                })
            }
        }
    } else {
        ctx.error("Unrecognised top-level structure".to_string());
        ParseResult::Official(OfficialAdventureData {
            id: String::new(),
            source: String::new(),
            data: Vec::new(),
        })
    }
}

/// Result of parsing a document
pub enum ParseResult {
    Homebrew(HomebrewAdventure),
    Official(OfficialAdventureData),
}

/// Official adventure data format: {"data": [...]}
#[derive(Serialize, Deserialize)]
pub struct OfficialAdventureData {
    #[serde(rename = "id")]
    id: String,
    #[serde(rename = "source")]
    source: String,
    #[serde(rename = "data")]
    data: Vec<Entry>,
}

impl Default for HomebrewAdventure {
    fn default() -> Self {
        Self {
            meta: Meta {
                sources: Vec::new(),
                dateAdded: None,
                dateLastModified: None,
            },
            adventure: Vec::new(),
            adventure_data: Vec::new(),
            is_book: None,
        }
    }
}

#[derive(Serialize, Deserialize)]
pub struct HomebrewAdventure {
    #[serde(rename = "_meta")]
    meta: Meta,
    #[serde(rename = "adventure")]
    adventure: Vec<AdventureIndex>,
    #[serde(rename = "adventureData")]
    adventure_data: Vec<AdventureData>,
    #[serde(skip_serializing_if = "Option::is_none")]
    is_book: Option<bool>,
}

#[derive(Serialize, Deserialize)]
pub struct Meta {
    #[serde(rename = "sources")]
    sources: Vec<MetaSource>,
    #[serde(rename = "dateAdded")]
    #[serde(skip_serializing_if = "Option::is_none")]
    dateAdded: Option<i64>, // Renamed from date_added to dateAdded
    #[serde(rename = "dateLastModified")]
    #[serde(skip_serializing_if = "Option::is_none")]
    dateLastModified: Option<i64>, // Renamed from date_last_modified to dateLastModified
}

#[derive(Serialize, Deserialize)]
pub struct MetaSource {
    #[serde(rename = "json")]
    json: String,
    #[serde(rename = "abbreviation")]
    abbreviation: String,
    #[serde(rename = "full")]
    full: String,
    #[serde(rename = "version")]
    #[serde(skip_serializing_if = "Option::is_none")]
    version: Option<String>,
    #[serde(rename = "authors")]
    #[serde(default)]
    authors: Vec<String>,
    #[serde(rename = "convertedBy")]
    #[serde(default)]
    convertedBy: Vec<String>, // Renamed from converted_by to convertedBy
    #[serde(rename = "url")]
    #[serde(skip_serializing_if = "Option::is_none")]
    url: Option<String>,
    #[serde(rename = "color")]
    #[serde(skip_serializing_if = "Option::is_none")]
    color: Option<String>,
}

#[derive(Serialize, Deserialize)]
pub struct AdventureIndex {
    #[serde(rename = "name")]
    name: String,
    #[serde(rename = "id")]
    id: String,
    #[serde(rename = "source")]
    source: String,
    #[serde(rename = "contents")]
    contents: Vec<TocEntry>,
    #[serde(rename = "group")]
    #[serde(skip_serializing_if = "Option::is_none")]
    group: Option<String>,
    #[serde(rename = "published")]
    #[serde(skip_serializing_if = "Option::is_none")]
    published: Option<String>,
    #[serde(rename = "author")]
    #[serde(skip_serializing_if = "Option::is_none")]
    author: Option<String>,
    #[serde(rename = "storyline")]
    #[serde(skip_serializing_if = "Option::is_none")]
    storyline: Option<String>,
    #[serde(rename = "level")]
    #[serde(skip_serializing_if = "Option::is_none")]
    level: Option<serde_json::Value>,
    #[serde(rename = "coverUrl")]
    #[serde(skip_serializing_if = "Option::is_none")]
    coverUrl: Option<String>, // Renamed from cover_url to coverUrl
}

#[derive(Serialize, Deserialize, Clone)]
#[serde(untagged)]
pub enum TocHeader {
    Simple(String),
    WithDepth { header: String, depth: i32 },
}

impl TocHeader {
    pub fn to_dict(&self) -> serde_json::Value {
        match self {
            TocHeader::Simple(s) => serde_json::Value::String(s.clone()),
            TocHeader::WithDepth { header, depth } => {
                let mut map = serde_json::Map::new();
                map.insert("header".to_string(), serde_json::Value::String(header.clone()));
                map.insert("depth".to_string(), serde_json::Value::Number((*depth).into()));
                serde_json::Value::Object(map)
            }
        }
    }
}

#[derive(Serialize, Deserialize)]
pub struct TocEntry {
    #[serde(rename = "name")]
    name: String,
    #[serde(rename = "headers")]
    #[serde(serialize_with = "serialize_headers")]
    #[serde(deserialize_with = "deserialize_headers")]
    headers: Vec<TocHeader>,
    #[serde(rename = "ordinal")]
    #[serde(skip_serializing_if = "Option::is_none")]
    ordinal: Option<serde_json::Value>,
}

fn serialize_headers<S>(headers: &Vec<TocHeader>, serializer: S) -> Result<S::Ok, S::Error>
where
    S: serde::Serializer,
{
    let values: Vec<serde_json::Value> = headers.iter().map(|h| h.to_dict()).collect();
    values.serialize(serializer)
}

fn deserialize_headers<'de, D>(deserializer: D) -> Result<Vec<TocHeader>, D::Error>
where
    D: Deserializer<'de>,
{
    let values = Vec::<serde_json::Value>::deserialize(deserializer)?;
    let mut result = Vec::new();
    for v in values {
        if v.is_string() {
            result.push(TocHeader::Simple(v.as_str().unwrap().to_string()));
        } else if v.is_object() {
            let obj = v.as_object().unwrap();
            let header = obj.get("header").unwrap().as_str().unwrap().to_string();
            let depth = obj.get("depth").unwrap().as_i64().unwrap() as i32;
            result.push(TocHeader::WithDepth { header, depth });
        } else {
            return Err(serde::de::Error::custom("expected string or object"));
        }
    }
    Ok(result)
}

#[derive(Serialize, Deserialize)]
pub struct AdventureData {
    #[serde(rename = "id")]
    id: String,
    #[serde(rename = "source")]
    source: String,
    #[serde(rename = "data")]
    data: Vec<Entry>,
}

impl HomebrewAdventure {
    /// Validate the parsed adventure
    pub fn validate(&self) -> BuildContext {
        let mut ctx = BuildContext::new();
        
        // Validate adventure index
        if let Some(adv) = self.adventure.first() {
            if adv.name.is_empty() {
                ctx.warn("adventure[0].name is missing".to_string());
            }
            if adv.id.is_empty() {
                ctx.warn("adventure[0].id is missing".to_string());
            }
        }
        
        // Validate data entries
        for data_obj in &self.adventure_data {
            for (i, entry) in data_obj.data.iter().enumerate() {
                entry.validate(&format!("adventureData[0].data[{}]", i), &mut ctx);
            }
        }
        
        ctx
    }

    /// Assign sequential IDs to all section/entries/inset nodes
    pub fn assign_ids(&mut self) {
        let mut counter = 0;
        for data_obj in &mut self.adventure_data {
            for entry in &mut data_obj.data {
                assign_ids_recursive(entry, &mut counter);
            }
        }
    }

    /// Rebuild contents[] from data[] sections
    pub fn build_toc(&mut self) {
        for data_obj in &mut self.adventure_data {
            let mut toc_entries = Vec::new();
            for section in &data_obj.data {
                let mut headers = Vec::new();
                if let Entry::Section { entries, .. } | Entry::Entries { entries, .. } = section {
                    for entry_or_string in entries {
                        if let EntryOrString::Entry(boxed) = entry_or_string {
                            if let Entry::Section { name, .. } | Entry::Entries { name, .. } = &**boxed {
                                if let Some(name) = name {
                                    headers.push(TocHeader::WithDepth {
                                        header: name.clone(),
                                        depth: 0,
                                    });
                                }
                            }
                        }
                    }
                }
                let section_name = section.get_name().unwrap_or("Untitled");
                toc_entries.push(TocEntry {
                    name: section_name.to_string(),
                    headers,
                    ordinal: None,
                });
            }
            // Update the first adventure index
            if let Some(adv) = self.adventure.first_mut() {
                adv.contents = toc_entries;
            }
        }
    }
}

/// Recursively assign sequential IDs to section/entries/inset nodes
fn assign_ids_recursive(entry: &mut Entry, counter: &mut i32) {
    // Only assign IDs to section, entries, and inset types
    let should_assign = matches!(
        entry,
        Entry::Section { .. } | Entry::Entries { .. } | Entry::Inset { .. }
    );

    if should_assign {
        entry.set_id(Some(format!("{:03}", counter)));
        *counter += 1;
    }

    // Recurse into entries[]
    if let Some(entries) = entry.get_entries_mut() {
        for entry_or_string in entries {
            if let EntryOrString::Entry(boxed) = entry_or_string {
                assign_ids_recursive(boxed, counter);
            }
        }
    }

    // Recurse into items[]
    if let Some(items) = entry.get_items_mut() {
        for entry_or_string in items {
            if let EntryOrString::Entry(boxed) = entry_or_string {
                assign_ids_recursive(boxed, counter);
            }
        }
    }
}

impl Entry {
    /// Set the entry's ID
    pub fn set_id(&mut self, id: Option<String>) {
        match self {
            Entry::Section { id: section_id, .. } => *section_id = id,
            Entry::Entries { id: entries_id, .. } => *entries_id = id,
            Entry::Inset { id: inset_id, .. } => *inset_id = id,
            Entry::Quote { id: quote_id, .. } => *quote_id = id,
            Entry::VariantInner { id: variant_id, .. } => *variant_id = id,
            Entry::List { id: list_id, .. } => *list_id = id,
            Entry::Item { id: item_id, .. } => *item_id = id,
            Entry::ItemSub { id: itemsub_id, .. } => *itemsub_id = id,
            Entry::Table { .. } => {}
            Entry::TableGroup { .. } => {}
            Entry::Image { .. } => {}
            Entry::Gallery { .. } => {}
            Entry::Hr => {}
            Entry::Inline { .. } => {}
            Entry::InlineBlock { .. } => {}
            Entry::Flowchart { .. } => {}
            Entry::FlowBlock { .. } => {}
            Entry::Statblock { .. } => {}
            Entry::Spellcasting { .. } => {}
        }
    }

    /// Get mutable entries for recursion
    fn get_entries_mut(&mut self) -> Option<&mut Vec<EntryOrString>> {
        match self {
            Entry::Section { entries, .. } => Some(entries),
            Entry::Entries { entries, .. } => Some(entries),
            Entry::Inset { entries, .. } => Some(entries),
            Entry::Quote { entries, .. } => Some(entries),
            Entry::VariantInner { entries, .. } => Some(entries),
            Entry::List { items, .. } => Some(items),
            Entry::Item { entries, .. } => entries.as_mut(),
            Entry::ItemSub { .. } => None,
            Entry::Table { .. } => None,
            Entry::TableGroup { .. } => None,
            Entry::Image { .. } => None,
            Entry::Gallery { .. } => None,
            Entry::Hr => None,
            Entry::Inline { entries, .. } => Some(entries),
            Entry::InlineBlock { entries, .. } => Some(entries),
            Entry::Flowchart { .. } => None,
            Entry::FlowBlock { entries, .. } => Some(entries),
            Entry::Statblock { .. } => None,
            Entry::Spellcasting { .. } => None,
        }
    }

    /// Get mutable items for recursion
    fn get_items_mut(&mut self) -> Option<&mut Vec<EntryOrString>> {
        match self {
            Entry::List { items, .. } => Some(items),
            _ => None,
        }
    }
}
