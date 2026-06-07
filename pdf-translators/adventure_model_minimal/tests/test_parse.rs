use adventure_model_minimal::{parse_entry};
use adventure_model_minimal::parser::parse_document;

#[test]
fn test_parse_section() {
    let json_str = r#"
    {
      "type": "section",
      "name": "The Dungeon",
      "entries": [
        {
          "type": "inset",
          "text": "A dark and damp cave."
        },
            {
              "type": "quote",
              "text": "The forest remembers what you do.",
              "by": "The Old Druid",
              "from": "Whispering Woods, Page 12",
              "name": "Prophecy"
            },
        {
          "type": "list",
          "name": "Quest Objectives",
          "items": [
            {
              "text": "Find the lost amulet",
              "type": "text"
            },
            {
              "type": "inset",
              "text": "The amulet is hidden in the ancient temple"
            },
            {
              "type": "quote",
              "text": "Only the worthy may claim it.",
              "by": "The Oracle"
            }
          ],
          "id": "quest-objectives-1"
        },
        {
          "type": "table",
          "name": "Monster Statistics",
          "headers": ["Name", "AC", "HP", "Speed"],
          "rows": [
            ["Orc", "13", "15", "40"],
            ["Goblin", "15", "7", "30"],
            ["Troll", "17", "45", "30"]
          ],
          "id": "monster-stats-1"
        }
      ],
      "id": "dungeon-1"
    }
    "#;

    let value: serde_json::Value = serde_json::from_str(json_str).unwrap();
    let entry = parse_entry(&value).unwrap();

    if let adventure_model_minimal::Entry::Section(section) = entry {
        assert_eq!(section.name, Some("The Dungeon".to_string()));
        assert_eq!(section.id, Some("dungeon-1".to_string()));
        assert_eq!(section.entries.len(), 4);
        
        // Check first entry is inset
        if let adventure_model_minimal::Entry::Inset(inset) = &section.entries[0] {
            assert_eq!(inset.text, "A dark and damp cave.".to_string());
        } else {
            panic!("Expected first entry to be inset");
        }
        
        // Check second entry is quote
        if let adventure_model_minimal::Entry::Quote(quote) = &section.entries[1] {
            assert_eq!(quote.text, "The forest remembers what you do.".to_string());
            assert_eq!(quote.by, Some("The Old Druid".to_string()));
            println!("DEBUG: quote.from = {:?}", quote.from);
            assert_eq!(quote.from, Some("Whispering Woods, Page 12".to_string()));
            assert_eq!(quote.name, Some("Prophecy".to_string()));
        } else {
            panic!("Expected second entry to be quote");
        }
        
        // Check third entry is list
        if let adventure_model_minimal::Entry::List(list) = &section.entries[2] {
            assert_eq!(list.name, Some("Quest Objectives".to_string()));
            assert_eq!(list.id, Some("quest-objectives-1".to_string()));
            assert_eq!(list.items.len(), 3);
            
            // Check first item is text
            if let adventure_model_minimal::Entry::Generic(_) = &list.items[0] {
                // OK - text is parsed as Generic
            } else {
                panic!("Expected first list item to be Generic (text)");
            }
            
            // Check second item is inset
            if let adventure_model_minimal::Entry::Inset(inset) = &list.items[1] {
                assert_eq!(inset.text, "The amulet is hidden in the ancient temple".to_string());
            } else {
                panic!("Expected second list item to be inset");
            }
            
            // Check third item is quote
            if let adventure_model_minimal::Entry::Quote(quote) = &list.items[2] {
                assert_eq!(quote.text, "Only the worthy may claim it.".to_string());
                assert_eq!(quote.by, Some("The Oracle".to_string()));
            } else {
                panic!("Expected third list item to be quote");
            }
        } else {
            panic!("Expected third entry to be list");
        }
        
        // Check fourth entry is table
        if let adventure_model_minimal::Entry::Table(table) = &section.entries[3] {
            assert_eq!(table.name, Some("Monster Statistics".to_string()));
            assert_eq!(table.id, Some("monster-stats-1".to_string()));
            assert_eq!(table.headers.len(), 4);
            assert_eq!(table.headers[0], "Name");
            assert_eq!(table.headers[1], "AC");
            assert_eq!(table.headers[2], "HP");
            assert_eq!(table.headers[3], "Speed");
            assert_eq!(table.rows.len(), 3);
            assert_eq!(table.rows[0][0], "Orc");
            assert_eq!(table.rows[0][1], "13");
            assert_eq!(table.rows[0][2], "15");
            assert_eq!(table.rows[0][3], "40");
        } else {
            panic!("Expected fourth entry to be table");
        }
    } else {
        panic!("Expected Section entry");
    }
}

#[test]
fn test_parse_quote() {
    let json_str = r#"
    {
      "type": "quote",
      "text": "The stars are watching you, traveler.",
      "by": "The Starlight Oracle",
      "from": "Prophecies of the Void, Page 7",
      "name": "Prophecy",
      "id": "prophecy-1"
    }
    "#;

    let value: serde_json::Value = serde_json::from_str(json_str).unwrap();
    let entry = parse_entry(&value).unwrap();

    if let adventure_model_minimal::Entry::Quote(quote) = entry {
        assert_eq!(quote.text, "The stars are watching you, traveler.".to_string());
        assert_eq!(quote.by, Some("The Starlight Oracle".to_string()));
        assert_eq!(quote.from, Some("Prophecies of the Void, Page 7".to_string()));
        assert_eq!(quote.name, Some("Prophecy".to_string()));
        assert_eq!(quote.id, Some("prophecy-1".to_string()));
    } else {
        panic!("Expected Quote entry");
    }
}

#[test]
fn test_validation_empty_text_inset() {
    let json_str = r#"
    {
      "type": "inset",
      "text": "",
      "name": "Empty Text",
      "id": "empty-1"
    }
    "#;

    let value: serde_json::Value = serde_json::from_str(json_str).unwrap();
    let result = parse_entry(&value);
    
    assert!(result.is_err());
    match result.unwrap_err() {
        adventure_model_minimal::ParseError::NestedParseError(msg) => {
            assert!(msg.contains("Inset validation failed: Field \"text\" cannot be empty in inset"));
        }
        _ => panic!("Expected NestedParseError for validation failure"),
    }
}

#[test]
fn test_validation_empty_text_quote() {
    let json_str = r#"
    {
      "type": "quote",
      "text": "",
      "by": "Anonymous",
      "id": "empty-quote-1"
    }
    "#;

    let value: serde_json::Value = serde_json::from_str(json_str).unwrap();
    let result = parse_entry(&value);
    
    assert!(result.is_err());
    match result.unwrap_err() {
        adventure_model_minimal::ParseError::NestedParseError(msg) => {
            assert!(msg.contains("Quote validation failed: Field \"text\" cannot be empty in quote"));
        }
        _ => panic!("Expected NestedParseError for validation failure"),
    }
}

#[test]
fn test_validation_empty_id_section() {
    let json_str = r#"
    {
      "type": "section",
      "name": "Empty ID Section",
      "entries": [],
      "id": ""
    }
    "#;

    let value: serde_json::Value = serde_json::from_str(json_str).unwrap();
    let result = parse_entry(&value);
    
    assert!(result.is_err());
    match result.unwrap_err() {
        adventure_model_minimal::ParseError::NestedParseError(msg) => {
            assert!(msg.contains("Section validation failed: Field \"id\" cannot be empty in section"));
        }
        _ => panic!("Expected NestedParseError for validation failure"),
    }
}

#[test]
fn test_validation_empty_id_list() {
    let json_str = r#"
    {
      "type": "list",
      "name": "Empty ID List",
      "items": [
        {
          "text": "Item 1",
          "type": "text"
        }
      ],
      "id": ""
    }
    "#;

    let value: serde_json::Value = serde_json::from_str(json_str).unwrap();
    let result = parse_entry(&value);
    
    assert!(result.is_err());
    match result.unwrap_err() {
        adventure_model_minimal::ParseError::NestedParseError(msg) => {
            assert!(msg.contains("List validation failed: Field \"id\" cannot be empty in list"));
        }
        _ => panic!("Expected NestedParseError for validation failure"),
    }
}

#[test]
fn test_parse_list() {
    let json_str = r#"
    {
      "type": "list",
      "name": "Treasure",
      "items": [
        {
          "type": "text",
          "text": "100 gold pieces"
        },
        {
          "type": "inset",
          "text": "A magical dagger that glows in the presence of danger"
        }
      ],
      "id": "treasure-1"
    }
    "#;

    let value: serde_json::Value = serde_json::from_str(json_str).unwrap();
    let entry = parse_entry(&value).unwrap();

    if let adventure_model_minimal::Entry::List(list) = entry {
        assert_eq!(list.name, Some("Treasure".to_string()));
        assert_eq!(list.id, Some("treasure-1".to_string()));
        assert_eq!(list.items.len(), 2);
        
        // Check first item is text
        if let adventure_model_minimal::Entry::Generic(_) = &list.items[0] {
            // OK - text is parsed as Generic
        } else {
            panic!("Expected first list item to be Generic (text)");
        }
        
        // Check second item is inset
        if let adventure_model_minimal::Entry::Inset(inset) = &list.items[1] {
            assert_eq!(inset.text, "A magical dagger that glows in the presence of danger".to_string());
        } else {
            panic!("Expected second list item to be inset");
        }
    } else {
        panic!("Expected List entry");
    }
}

#[test]
fn test_parse_table() {
    let json_str = r#"
    {
      "type": "table",
      "name": "Spell Components",
      "headers": ["Spell", "Verbal", "Somatic", "Material"],
      "rows": [
        ["Fireball", "Yes", "Yes", "A tiny ball of bat guano and sulfur"],
        ["Lightning Bolt", "Yes", "Yes", "A bit of fur"],
        ["Cure Wounds", "Yes", "Yes", "None"]
      ],
      "id": "spell-components-1"
    }
    "#;

    let value: serde_json::Value = serde_json::from_str(json_str).unwrap();
    let entry = parse_entry(&value).unwrap();

    if let adventure_model_minimal::Entry::Table(table) = entry {
        assert_eq!(table.name, Some("Spell Components".to_string()));
        assert_eq!(table.id, Some("spell-components-1".to_string()));
        assert_eq!(table.headers.len(), 4);
        assert_eq!(table.headers[0], "Spell");
        assert_eq!(table.headers[1], "Verbal");
        assert_eq!(table.headers[2], "Somatic");
        assert_eq!(table.headers[3], "Material");
        assert_eq!(table.rows.len(), 3);
        assert_eq!(table.rows[0][0], "Fireball");
        assert_eq!(table.rows[0][1], "Yes");
        assert_eq!(table.rows[0][2], "Yes");
        assert_eq!(table.rows[0][3], "A tiny ball of bat guano and sulfur");
    } else {
        panic!("Expected Table entry");
    }
}

#[test]
fn test_validation_empty_headers_table() {
    let json_str = r#"
    {
      "type": "table",
      "name": "Empty Headers",
      "headers": [],
      "rows": [
        ["Orc", "13", "15", "40"]
      ],
      "id": "empty-headers-1"
    }
    "#;

    let value: serde_json::Value = serde_json::from_str(json_str).unwrap();
    let result = parse_entry(&value);
    
    assert!(result.is_err());
    match result.unwrap_err() {
        adventure_model_minimal::ParseError::NestedParseError(msg) => {
            assert!(msg.contains("Table validation failed: Missing required field \"headers\" in table"));
        }
        _ => panic!("Expected NestedParseError for validation failure"),
    }
}

#[test]
fn test_validation_empty_rows_table() {
    let json_str = r#"
    {
      "type": "table",
      "name": "Empty Rows",
      "headers": ["Name", "AC"],
      "rows": [],
      "id": "empty-rows-1"
    }
    "#;

    let value: serde_json::Value = serde_json::from_str(json_str).unwrap();
    let result = parse_entry(&value);
    
    assert!(result.is_err());
    match result.unwrap_err() {
        adventure_model_minimal::ParseError::NestedParseError(msg) => {
            assert!(msg.contains("Table validation failed: Missing required field \"rows\" in table"));
        }
        _ => panic!("Expected NestedParseError for validation failure"),
    }
}

#[test]
fn test_validation_mismatched_row_length_table() {
    let json_str = r#"
    {
      "type": "table",
      "name": "Mismatched Rows",
      "headers": ["Name", "AC", "HP"],
      "rows": [
        ["Orc", "13", "15", "40"],
        ["Goblin", "15", "7"]
      ],
      "id": "mismatched-rows-1"
    }
    "#;

    let value: serde_json::Value = serde_json::from_str(json_str).unwrap();
    let result = parse_entry(&value);
    
    assert!(result.is_err());
    match result.unwrap_err() {
        adventure_model_minimal::ParseError::NestedParseError(msg) => {
            assert!(msg.contains("Table validation failed: Field \"row 1\" must be a string in table"));
        }
        _ => panic!("Expected NestedParseError for validation failure"),
    }
}

#[test]
fn test_validation_empty_id_table() {
    let json_str = r#"
    {
      "type": "table",
      "name": "Empty ID Table",
      "headers": ["Name", "AC"],
      "rows": [
        ["Orc", "13"]
      ],
      "id": ""
    }
    "#;

    let value: serde_json::Value = serde_json::from_str(json_str).unwrap();
    let result = parse_entry(&value);
    
    assert!(result.is_err());
    match result.unwrap_err() {
        adventure_model_minimal::ParseError::NestedParseError(msg) => {
            assert!(msg.contains("Table validation failed: Field \"id\" cannot be empty in table"));
        }
        _ => panic!("Expected NestedParseError for validation failure"),
    }
}

#[test]
fn test_parse_document() {
    let json_str = r#"
    {
      "_meta": {
        "sources": [
          {
            "id": "TOWORLDS",
            "name": "Tales of the World",
            "url": "https://example.com"
          }
        ]
      },
      "data": [
        {
          "type": "section",
          "name": "The Dungeon",
          "entries": [
            {
              "type": "inset",
              "text": "A dark and damp cave."
            },
            {
              "type": "quote",
              "text": "The forest remembers what you do.",
              "by": "The Old Druid",
              "from": "Whispering Woods, Page 12",
              "name": "Prophecy"
            },
            {
              "type": "list",
              "name": "Quest Objectives",
              "items": [
                {
                  "text": "Find the lost amulet",
                  "type": "text"
                },
                {
                  "type": "inset",
                  "text": "The amulet is hidden in the ancient temple"
                },
                {
                  "type": "quote",
                  "text": "Only the worthy may claim it.",
                  "by": "The Oracle"
                }
              ],
              "id": "quest-objectives-1"
            }
          ],
          "id": "dungeon-1"
        }
      ]
    }
    "#;

    let value: serde_json::Value = serde_json::from_str(json_str).unwrap();
    let adventure = parse_document(&value).unwrap();

    assert_eq!(adventure._meta.sources.len(), 1);
    assert_eq!(adventure._meta.sources[0].id, "TOWORLDS");
    assert_eq!(adventure._meta.sources[0].name, "Tales of the World");
    assert_eq!(adventure._meta.sources[0].url, "https://example.com");
    
    assert_eq!(adventure.data.len(), 1);
    if let adventure_model_minimal::Entry::Section(section) = &adventure.data[0] {
        assert_eq!(section.name, Some("The Dungeon".to_string()));
        assert_eq!(section.id, Some("dungeon-1".to_string()));
    } else {
        panic!("Expected first data entry to be Section");
    }
    
    assert_eq!(adventure.toc.len(), 1);
    assert_eq!(adventure.toc[0].name, "The Dungeon");
    assert_eq!(adventure.toc[0].id, "dungeon-1");
    assert_eq!(adventure.toc[0].depth, 1);
    
    assert_eq!(adventure.headers.len(), 2);
    assert_eq!(adventure.headers[0].header, "Prophecy");
    assert_eq!(adventure.headers[0].depth, 2);
    assert_eq!(adventure.headers[1].header, "Quest Objectives");
    assert_eq!(adventure.headers[1].depth, 2);
}

#[test]
fn test_parse_document_duplicate_source_id() {
    let json_str = r#"
    {
      "_meta": {
        "sources": [
          {
            "id": "TOWORLDS",
            "name": "Tales of the World",
            "url": "https://example.com"
          },
          {
            "id": "TOWORLDS",
            "name": "Tales of the World (Duplicate)",
            "url": "https://example.com/duplicate"
          }
        ]
      },
      "data": [
        {
          "type": "section",
          "name": "The Dungeon",
          "entries": [
            {
              "type": "inset",
              "text": "A dark and damp cave."
            }
          ],
          "id": "dungeon-1"
        }
      ]
    }
    "#;

    let value: serde_json::Value = serde_json::from_str(json_str).unwrap();
    let result = parse_document(&value);
    
    assert!(result.is_err());
    match result.unwrap_err() {
        adventure_model_minimal::ParseError::DuplicateSourceId(id) => {
            assert_eq!(id, "TOWORLDS");
        }
        _ => panic!("Expected DuplicateSourceId error"),
    }
}
