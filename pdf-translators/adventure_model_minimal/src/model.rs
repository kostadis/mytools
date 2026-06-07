use serde::{Deserialize, Serialize};
use thiserror::Error;

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct Meta {
    pub sources: Vec<MetaSource>,
}

impl Meta {
    pub fn validate_sources(&self) -> Result<(), ParseError> {
        let mut seen_ids = std::collections::HashSet::new();
        
        for source in &self.sources {
            if seen_ids.contains(&source.id) {
                return Err(ParseError::DuplicateSourceId(source.id.clone()));
            }
            seen_ids.insert(&source.id);
        }
        
        Ok(())
    }
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct MetaSource {
    pub id: String,
    pub name: String,
    pub url: String,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct SectionEntry {
    pub name: Option<String>,
    pub entries: Vec<Entry>,
    pub id: Option<String>,
    pub page: Option<i32>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct InsetEntry {
    pub text: String,
    pub name: Option<String>,
    pub id: Option<String>,
    pub page: Option<i32>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct QuoteEntry {
    pub text: String,
    pub by: Option<String>,
    pub from: Option<String>,
    pub name: Option<String>,
    pub id: Option<String>,
    pub page: Option<i32>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct ListEntry {
    pub items: Vec<Entry>,
    pub name: Option<String>,
    pub id: Option<String>,
    pub page: Option<i32>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct TableEntry {
    pub headers: Vec<String>,
    pub rows: Vec<Vec<String>>,
    pub name: Option<String>,
    pub id: Option<String>,
    pub page: Option<i32>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct ImageEntry {
    pub href: String,
    pub alt: Option<String>,
    pub title: Option<String>,
    pub id: Option<String>,
    pub page: Option<i32>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub enum Entry {
    Section(SectionEntry),
    Inset(InsetEntry),
    Quote(QuoteEntry),
    List(ListEntry),
    Table(TableEntry),
    Image(ImageEntry),
    Generic(serde_json::Value),
}

impl ImageEntry {
    pub fn validate(&self) -> Result<(), ValidationError> {
        if self.href.is_empty() {
            return Err(ValidationError::EmptyField("href".to_string(), "image".to_string()));
        }
        
        if let Some(id) = &self.id {
            if id.is_empty() {
                return Err(ValidationError::EmptyField("id".to_string(), "image".to_string()));
            }
        }
        
        Ok(())
    }
}

impl Entry {
    pub fn as_section(&self) -> Option<&SectionEntry> {
        match self {
            Entry::Section(section) => Some(section),
            _ => None,
        }
    }
    
    pub fn as_inset(&self) -> Option<&InsetEntry> {
        match self {
            Entry::Inset(inset) => Some(inset),
            _ => None,
        }
    }
    
    pub fn as_quote(&self) -> Option<&QuoteEntry> {
        match self {
            Entry::Quote(quote) => Some(quote),
            _ => None,
        }
    }
    
    pub fn as_list(&self) -> Option<&ListEntry> {
        match self {
            Entry::List(list) => Some(list),
            _ => None,
        }
    }
    
    pub fn as_table(&self) -> Option<&TableEntry> {
        match self {
            Entry::Table(table) => Some(table),
            _ => None,
        }
    }
    
    pub fn as_image(&self) -> Option<&ImageEntry> {
        match self {
            Entry::Image(image) => Some(image),
            _ => None,
        }
    }
}

#[derive(Error, Debug)]
pub enum ParseError {
    #[error("Expected a JSON object, got {0}")]
    ExpectedObject(String),
    
    #[error("Missing required field \"{0}\" in {1}")]
    MissingField(String, String),
    
    #[error("Invalid type \"{0}\" - expected \"section\", \"inset\", \"quote\", \"list\", \"table\", or other known type")] 
    UnknownType(String),
    
    #[error("Failed to parse nested entry: {0}")]
    NestedParseError(String),
    
    #[error("Duplicate source ID \"{0}\" in meta.sources")]
    DuplicateSourceId(String),
}

#[derive(Error, Debug)]
pub enum ValidationError {
    #[error("Missing required field \"{0}\" in {1}")]
    MissingRequiredField(String, String),
    
    #[error("Field \"{0}\" cannot be empty in {1}")]
    EmptyField(String, String),
    
    #[error("Field \"{0}\" must be a string in {1}")]
    InvalidFieldType(String, String),
    
    #[error("Invalid ID format \"{0}\" in {1}")]
    InvalidIdFormat(String, String),
}

impl InsetEntry {
    pub fn validate(&self) -> Result<(), ValidationError> {
        if self.text.is_empty() {
            return Err(ValidationError::EmptyField("text".to_string(), "inset".to_string()));
        }
        
        if let Some(id) = &self.id {
            if id.is_empty() {
                return Err(ValidationError::EmptyField("id".to_string(), "inset".to_string()));
            }
        }
        
        Ok(())
    }
}

impl QuoteEntry {
    pub fn validate(&self) -> Result<(), ValidationError> {
        if self.text.is_empty() {
            return Err(ValidationError::EmptyField("text".to_string(), "quote".to_string()));
        }
        
        if let Some(id) = &self.id {
            if id.is_empty() {
                return Err(ValidationError::EmptyField("id".to_string(), "quote".to_string()));
            }
        }
        
        Ok(())
    }
}

impl SectionEntry {
    pub fn validate(&self) -> Result<(), ValidationError> {
        if let Some(id) = &self.id {
            if id.is_empty() {
                return Err(ValidationError::EmptyField("id".to_string(), "section".to_string()));
            }
        }
        
        Ok(())
    }
}

impl ListEntry {
    pub fn validate(&self) -> Result<(), ValidationError> {
        if let Some(id) = &self.id {
            if id.is_empty() {
                return Err(ValidationError::EmptyField("id".to_string(), "list".to_string()));
            }
        }
        
        Ok(())
    }
}

impl TableEntry {
    pub fn validate(&self) -> Result<(), ValidationError> {
        if self.headers.is_empty() {
            return Err(ValidationError::MissingRequiredField("headers".to_string(), "table".to_string()));
        }
        
        if self.rows.is_empty() {
            return Err(ValidationError::MissingRequiredField("rows".to_string(), "table".to_string()));
        }
        
        // Ensure all rows have the same length as headers
        let header_count = self.headers.len();
        for (i, row) in self.rows.iter().enumerate() {
            if row.len() != header_count {
                return Err(ValidationError::InvalidFieldType(
                    format!("row {}", i + 1).to_string(), 
                    "table".to_string()
                ));
            }
        }
        
        if let Some(id) = &self.id {
            if id.is_empty() {
                return Err(ValidationError::EmptyField("id".to_string(), "table".to_string()));
            }
        }
        
        Ok(())
    }
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct TocEntry {
    pub name: String,
    pub id: String,
    pub depth: u8,
    pub page: Option<i32>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct TocHeader {
    pub header: String,
    pub depth: u8,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct HomebrewAdventure {
    pub _meta: Meta,
    pub data: Vec<Entry>,
    pub toc: Vec<TocEntry>,
    pub headers: Vec<TocHeader>,
}

impl HomebrewAdventure {
    pub fn build(meta: Meta, data: Vec<Entry>) -> Result<HomebrewAdventure, String> {
        // Validate that data entries are properly structured
        if data.is_empty() {
            return Err("Adventure data cannot be empty".to_string());
        }
        
        // Build TOC from section hierarchy
        let mut toc_entries = Vec::new();
        let mut headers = Vec::new();
        
        for entry in &data {
            if let Entry::Section(section) = entry {
                // Top-level section
                let section_name = section.name.clone().unwrap_or_else(|| "Untitled Section".to_string());
                let section_id = section.id.clone().unwrap_or_else(|| {
                    // Generate a simple ID from name if none provided
                    section_name.chars()
                        .map(|c| if c.is_alphanumeric() { c } else { '_' })
                        .collect()
                });
                
                toc_entries.push(TocEntry {
                    name: section_name.clone(),
                    id: section_id.clone(),
                    depth: 1,
                    page: section.page,
                });
                
                // Add any headers from the section's entries
                for sub_entry in &section.entries {
                    match sub_entry {
                        Entry::Section(_) => {
                            // Nested sections will be handled as top-level entries
                            // in the data array, not as headers
                        }
                        Entry::Inset(inset) => {
                            if let Some(name) = &inset.name {
                                headers.push(TocHeader {
                                    header: name.clone(),
                                    depth: 2,
                                });
                            }
                        }
                        Entry::Quote(quote) => {
                            if let Some(name) = &quote.name {
                                headers.push(TocHeader {
                                    header: name.clone(),
                                    depth: 2,
                                });
                            }
                        }
                        Entry::List(list) => {
                            if let Some(name) = &list.name {
                                headers.push(TocHeader {
                                    header: name.clone(),
                                    depth: 2,
                                });
                            }
                        }
                        Entry::Table(table) => {
                            if let Some(name) = &table.name {
                                headers.push(TocHeader {
                                    header: name.clone(),
                                    depth: 2,
                                });
                            }
                        }
                        Entry::Image(_image) => {
                            // Image entries don't have names for TOC
                        }
                        Entry::Generic(_) => {
                            // Generic entries don't have names for TOC
                        }
                    }
                }
            }
        }
        
        // Debug: Print what we found
        println!("DEBUG: Found {} TocEntries", toc_entries.len());
        for (i, toc) in toc_entries.iter().enumerate() {
            println!("DEBUG: TocEntry[{}] = {{name: \"{}\", id: \"{}\", depth: {}}}", 
                i, toc.name, toc.id, toc.depth);
        }
        println!("DEBUG: Found {} TocHeaders", headers.len());
        for (i, header) in headers.iter().enumerate() {
            println!("DEBUG: TocHeader[{}] = {{header: \"{}\", depth: {}}}", 
                i, header.header, header.depth);
        }
        
        Ok(HomebrewAdventure {
            _meta: meta,
            data,
            toc: toc_entries,
            headers,
        })
    }
}