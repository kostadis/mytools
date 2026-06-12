use serde::{Serialize, Deserialize};
use crate::validation::BuildContext;
use crate::tags::validate_tags;

#[derive(Serialize, Deserialize)]
#[serde(untagged)]
pub enum EntryOrString {
    Entry(Box<Entry>),
    String(String),
}

#[derive(Serialize, Deserialize)]
pub struct ImageHref {
    #[serde(rename = "type")]
    type_field: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    path: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    url: Option<String>,
}

#[derive(Serialize, Deserialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct GenericEntry {
    #[serde(rename = "type")]
    type_field: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    page: Option<i32>,
    #[serde(flatten)]
    extra: std::collections::HashMap<String, serde_json::Value>,
}

#[derive(Serialize, Deserialize)]
#[serde(tag = "type")]
pub enum Entry {
    #[serde(rename = "section")]
    Section {
        #[serde(skip_serializing_if = "Option::is_none")]
        name: Option<String>,
        #[serde(skip_serializing_if = "Option::is_none")]
        id: Option<String>,
        #[serde(skip_serializing_if = "Option::is_none")]
        page: Option<i32>,
        entries: Vec<EntryOrString>,
    },
    #[serde(rename = "entries")]
    Entries {
        #[serde(skip_serializing_if = "Option::is_none")]
        name: Option<String>,
        #[serde(skip_serializing_if = "Option::is_none")]
        id: Option<String>,
        #[serde(skip_serializing_if = "Option::is_none")]
        page: Option<i32>,
        entries: Vec<EntryOrString>,
    },
    #[serde(rename = "inset")]
    Inset {
        #[serde(skip_serializing_if = "Option::is_none")]
        name: Option<String>,
        #[serde(skip_serializing_if = "Option::is_none")]
        id: Option<String>,
        #[serde(skip_serializing_if = "Option::is_none")]
        page: Option<i32>,
        entries: Vec<EntryOrString>,
    },
    #[serde(rename = "quote")]
    Quote {
        #[serde(skip_serializing_if = "Option::is_none")]
        name: Option<String>,
        #[serde(skip_serializing_if = "Option::is_none")]
        id: Option<String>,
        #[serde(skip_serializing_if = "Option::is_none")]
        page: Option<i32>,
        entries: Vec<EntryOrString>,
        #[serde(skip_serializing_if = "Option::is_none")]
        by: Option<String>,
        #[serde(skip_serializing_if = "Option::is_none")]
        from: Option<String>,
    },
    #[serde(rename = "variantInner")]
    VariantInner {
        #[serde(skip_serializing_if = "Option::is_none")]
        name: Option<String>,
        #[serde(skip_serializing_if = "Option::is_none")]
        id: Option<String>,
        #[serde(skip_serializing_if = "Option::is_none")]
        page: Option<i32>,
        entries: Vec<EntryOrString>,
    },
    #[serde(rename = "list")]
    List {
        #[serde(skip_serializing_if = "Option::is_none")]
        name: Option<String>,
        #[serde(skip_serializing_if = "Option::is_none")]
        id: Option<String>,
        #[serde(skip_serializing_if = "Option::is_none")]
        page: Option<i32>,
        items: Vec<EntryOrString>,
        #[serde(skip_serializing_if = "Option::is_none")]
        style: Option<String>,
    },
    #[serde(rename = "item")]
    Item {
        #[serde(skip_serializing_if = "Option::is_none")]
        name: Option<String>,
        #[serde(skip_serializing_if = "Option::is_none")]
        id: Option<String>,
        #[serde(skip_serializing_if = "Option::is_none")]
        page: Option<i32>,
        #[serde(skip_serializing_if = "Option::is_none")]
        entry: Option<String>,
        #[serde(skip_serializing_if = "Option::is_none")]
        entries: Option<Vec<EntryOrString>>,
    },
    #[serde(rename = "itemSub")]
    ItemSub {
        #[serde(skip_serializing_if = "Option::is_none")]
        name: Option<String>,
        #[serde(skip_serializing_if = "Option::is_none")]
        id: Option<String>,
        #[serde(skip_serializing_if = "Option::is_none")]
        page: Option<i32>,
        #[serde(skip_serializing_if = "Option::is_none")]
        entry: Option<String>,
    },
    #[serde(rename = "table")]
    Table {
        #[serde(skip_serializing_if = "Option::is_none")]
        caption: Option<String>,
        colLabels: Vec<String>,
        #[serde(skip_serializing_if = "Option::is_none")]
        colStyles: Option<Vec<String>>,
        rows: Vec<Vec<String>>,
    },
    #[serde(rename = "tableGroup")]
    TableGroup {
        tables: Vec<Box<Entry>>,
    },
    #[serde(rename = "image")]
    Image {
        #[serde(skip_serializing_if = "Option::is_none")]
        href: Option<ImageHref>,
        #[serde(skip_serializing_if = "Option::is_none")]
        title: Option<String>,
        #[serde(skip_serializing_if = "Option::is_none")]
        maxWidth: Option<i32>,
        #[serde(skip_serializing_if = "Option::is_none")]
        extra: Option<serde_json::Value>,
    },
    #[serde(rename = "gallery")]
    Gallery {
        images: Vec<Box<Entry>>,
    },
    #[serde(rename = "hr")]
    Hr,
    #[serde(rename = "inline")]
    Inline {
        entries: Vec<EntryOrString>,
    },
    #[serde(rename = "inlineBlock")]
    InlineBlock {
        entries: Vec<EntryOrString>,
    },
    #[serde(rename = "flowchart")]
    Flowchart {
        blocks: Vec<Box<Entry>>,
    },
    #[serde(rename = "flowBlock")]
    FlowBlock {
        entries: Vec<EntryOrString>,
    },
    #[serde(rename = "statblock")]
    Statblock {
        tag: String,
        source: String,
        #[serde(skip_serializing_if = "Option::is_none")]
        name: Option<String>,
    },
    #[serde(rename = "spellcasting")]
    Spellcasting {
        headerEntries: Vec<String>,
        #[serde(skip_serializing_if = "Option::is_none")]
        raw: Option<serde_json::Value>,
    },
}

impl Entry {
    pub fn to_dict(&self) -> serde_json::Value {
        serde_json::to_value(self).unwrap_or(serde_json::Value::Null)
    }

    /// Validate this entry and its children
    pub fn validate(&self, path: &str, ctx: &mut BuildContext) {
        // Validate ID uniqueness
        if let Some(id) = self.get_id() {
            ctx.check_id(&id, path);
        }

        // Validate name tags
        if let Some(name) = self.get_name() {
            validate_tags(&name, &format!("{}.name", path), ctx);
        }

        // Validate type-specific fields
        self.validate_fields(path, ctx);

        // Recursively validate child entries
        self.validate_entries(path, ctx);
    }

    /// Get the entry's type
    pub fn get_type(&self) -> &str {
        match self {
            Entry::Section { .. } => "section",
            Entry::Entries { .. } => "entries",
            Entry::Inset { .. } => "inset",
            Entry::Quote { .. } => "quote",
            Entry::VariantInner { .. } => "variantInner",
            Entry::List { .. } => "list",
            Entry::Item { .. } => "item",
            Entry::ItemSub { .. } => "itemSub",
            Entry::Table { .. } => "table",
            Entry::TableGroup { .. } => "tableGroup",
            Entry::Image { .. } => "image",
            Entry::Gallery { .. } => "gallery",
            Entry::Hr => "hr",
            Entry::Inline { .. } => "inline",
            Entry::InlineBlock { .. } => "inlineBlock",
            Entry::Flowchart { .. } => "flowchart",
            Entry::FlowBlock { .. } => "flowBlock",
            Entry::Statblock { .. } => "statblock",
            Entry::Spellcasting { .. } => "spellcasting",
        }
    }

    /// Get the entry's name
    pub fn get_name(&self) -> Option<&str> {
        match self {
            Entry::Section { name, .. } => name.as_deref(),
            Entry::Entries { name, .. } => name.as_deref(),
            Entry::Inset { name, .. } => name.as_deref(),
            Entry::Quote { name, .. } => name.as_deref(),
            Entry::VariantInner { name, .. } => name.as_deref(),
            Entry::List { name, .. } => name.as_deref(),
            Entry::Item { name, .. } => name.as_deref(),
            Entry::ItemSub { name, .. } => name.as_deref(),
            Entry::Table { .. } => None,
            Entry::TableGroup { .. } => None,
            Entry::Image { .. } => None,
            Entry::Gallery { .. } => None,
            Entry::Hr => None,
            Entry::Inline { .. } => None,
            Entry::InlineBlock { .. } => None,
            Entry::Flowchart { .. } => None,
            Entry::FlowBlock { .. } => None,
            Entry::Statblock { name, .. } => name.as_deref(),
            Entry::Spellcasting { .. } => None,
        }
    }

    /// Get the entry's ID
    pub fn get_id(&self) -> Option<&str> {
        match self {
            Entry::Section { id, .. } => id.as_deref(),
            Entry::Entries { id, .. } => id.as_deref(),
            Entry::Inset { id, .. } => id.as_deref(),
            Entry::Quote { id, .. } => id.as_deref(),
            Entry::VariantInner { id, .. } => id.as_deref(),
            Entry::List { id, .. } => id.as_deref(),
            Entry::Item { id, .. } => id.as_deref(),
            Entry::ItemSub { id, .. } => id.as_deref(),
            Entry::Table { .. } => None,
            Entry::TableGroup { .. } => None,
            Entry::Image { .. } => None,
            Entry::Gallery { .. } => None,
            Entry::Hr => None,
            Entry::Inline { .. } => None,
            Entry::InlineBlock { .. } => None,
            Entry::Flowchart { .. } => None,
            Entry::FlowBlock { .. } => None,
            Entry::Statblock { .. } => None,
            Entry::Spellcasting { .. } => None,
        }
    }

    /// Validate type-specific fields
    fn validate_fields(&self, path: &str, ctx: &mut BuildContext) {
        match self {
            Entry::Table { caption, colLabels, rows, .. } => {
                // Table validation: colLabels is required if rows exist
                if colLabels.is_empty() && !rows.is_empty() {
                    ctx.warn(format!("{}: table has rows but no colLabels", path));
                }
                // Validate caption tags
                if let Some(caption) = caption {
                    validate_tags(caption, &format!("{}.caption", path), ctx);
                }
                // Validate row tags
                for (ri, row) in rows.iter().enumerate() {
                    for (ci, cell) in row.iter().enumerate() {
                        validate_tags(cell, &format!("{}.rows[{}][{}]", path, ri, ci), ctx);
                    }
                }
            }
            Entry::Quote { by, from, .. } => {
                // Validate by and from tags
                if let Some(by) = by {
                    validate_tags(by, &format!("{}.by", path), ctx);
                }
                if let Some(from) = from {
                    validate_tags(from, &format!("{}.from", path), ctx);
                }
            }
            Entry::List { style, .. } => {
                // Validate items are arrays
                // Note: items is already Vec<EntryOrString> so it's always an array
                if let Some(style) = style {
                    validate_tags(style, &format!("{}.style", path), ctx);
                }
            }
            Entry::Image { href, title, .. } => {
                // Validate image href
                if href.is_none() {
                    ctx.error(format!("{}: image has no href", path));
                } else if let Some(h) = href {
                    if h.path.is_none() && h.url.is_none() {
                        ctx.warn(format!("{}: image href has no path or url", path));
                    }
                }
                // Validate title tags
                if let Some(title) = title {
                    validate_tags(title, &format!("{}.title", path), ctx);
                }
            }
            Entry::Statblock { tag, source, name, .. } => {
                // Statblock requires tag and source
                if tag.is_empty() {
                    ctx.warn(format!("{}: statblock has no tag", path));
                }
                if source.is_empty() {
                    ctx.warn(format!("{}: statblock has no source", path));
                }
                if let Some(name) = name {
                    validate_tags(name, &format!("{}.name", path), ctx);
                }
            }
            Entry::Spellcasting { headerEntries, .. } => {
                // Validate headerEntries tags
                for (i, header) in headerEntries.iter().enumerate() {
                    validate_tags(header, &format!("{}.headerEntries[{}]", path, i), ctx);
                }
            }
            Entry::Item { entry, entries, .. } => {
                // Validate entry field
                if let Some(e) = entry {
                    validate_tags(e, &format!("{}.entry", path), ctx);
                }
                // Validate entries
                if let Some(entries) = entries {
                    self.validate_entry_list(entries, &format!("{}.entries", path), ctx);
                }
            }
            Entry::ItemSub { entry, .. } => {
                // Validate entry field
                if let Some(e) = entry {
                    validate_tags(e, &format!("{}.entry", path), ctx);
                }
            }
            _ => {}
        }
    }

    /// Validate child entries recursively
    fn validate_entries(&self, path: &str, ctx: &mut BuildContext) {
        match self {
            Entry::Section { entries, .. } => {
                self.validate_entry_list(entries, &format!("{}.entries", path), ctx);
            }
            Entry::Entries { entries, .. } => {
                self.validate_entry_list(entries, &format!("{}.entries", path), ctx);
            }
            Entry::Inset { entries, .. } => {
                self.validate_entry_list(entries, &format!("{}.entries", path), ctx);
            }
            Entry::Quote { entries, .. } => {
                self.validate_entry_list(entries, &format!("{}.entries", path), ctx);
            }
            Entry::VariantInner { entries, .. } => {
                self.validate_entry_list(entries, &format!("{}.entries", path), ctx);
            }
            Entry::List { items, .. } => {
                self.validate_entry_list(items, &format!("{}.items", path), ctx);
            }
            Entry::Item { entries, .. } => {
                if let Some(entries) = entries {
                    self.validate_entry_list(entries, &format!("{}.entries", path), ctx);
                }
            }
            Entry::ItemSub { .. } => {
                // ItemSub has no child entries
            }
            Entry::Table { .. } => {
                // Table has no child entries
            }
            Entry::TableGroup { tables, .. } => {
                for (i, table) in tables.iter().enumerate() {
                    table.validate(&format!("{}.tables[{}]", path, i), ctx);
                }
            }
            Entry::Image { .. } => {
                // Image has no child entries
            }
            Entry::Gallery { images, .. } => {
                for (i, image) in images.iter().enumerate() {
                    image.validate(&format!("{}.images[{}]", path, i), ctx);
                }
            }
            Entry::Inline { entries, .. } => {
                self.validate_entry_list(entries, &format!("{}.entries", path), ctx);
            }
            Entry::InlineBlock { entries, .. } => {
                self.validate_entry_list(entries, &format!("{}.entries", path), ctx);
            }
            Entry::Flowchart { blocks, .. } => {
                for (i, block) in blocks.iter().enumerate() {
                    block.validate(&format!("{}.blocks[{}]", path, i), ctx);
                }
            }
            Entry::FlowBlock { entries, .. } => {
                self.validate_entry_list(entries, &format!("{}.entries", path), ctx);
            }
            Entry::Statblock { .. } => {}
            Entry::Spellcasting { .. } => {}
            Entry::Hr => {}
        }
    }

    /// Validate a list of entries
    fn validate_entry_list(&self, entries: &[EntryOrString], path: &str, ctx: &mut BuildContext) {
        for (i, entry) in entries.iter().enumerate() {
            let entry_path = format!("{}.{}", path, i);
            match entry {
                EntryOrString::Entry(boxed) => {
                    boxed.validate(&entry_path, ctx);
                }
                EntryOrString::String(s) => {
                    validate_tags(s, &entry_path, ctx);
                }
            }
        }
    }
}
