use adventure_model_minimal::{parse_entry, parse_document};
use serde_json;

fn main() {
    println!("=== Testing Section Entry ===");
    let section_json = r#"
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
          "from": "Whispering Woods, Page 12"
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

    let value: serde_json::Value = serde_json::from_str(section_json).unwrap();
    match parse_entry(&value) {
        Ok(entry) => println!("Parsed: {:?}", entry),
        Err(e) => println!("Error: {}", e),
    }

    println!("\n=== Testing Inset Entry ===");
    let inset_json = r#"
    {
      "type": "inset",
      "text": "The air is thick with the scent of damp earth and ancient stone.",
      "name": "Flavor Text",
      "id": "flavor-1"
    }
    "#;

    let inset_value: serde_json::Value = serde_json::from_str(inset_json).unwrap();
    match parse_entry(&inset_value) {
        Ok(entry) => println!("Parsed: {:?}", entry),
        Err(e) => println!("Error: {}", e),
    }

    println!("\n=== Testing Quote Entry ===");
    let quote_json = r#"
    {
      "type": "quote",
      "text": "The stars are watching you, traveler.",
      "by": "The Starlight Oracle",
      "from": "Prophecies of the Void, Page 7",
      "name": "Prophecy",
      "id": "prophecy-1"
    }
    "#;

    let quote_value: serde_json::Value = serde_json::from_str(quote_json).unwrap();
    match parse_entry(&quote_value) {
        Ok(entry) => println!("Parsed: {:?}", entry),
        Err(e) => println!("Error: {}", e),
    }

    println!("\n=== Testing List Entry ===");
    let list_json = r#"
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

    let list_value: serde_json::Value = serde_json::from_str(list_json).unwrap();
    match parse_entry(&list_value) {
        Ok(entry) => println!("Parsed: {:?}", entry),
        Err(e) => println!("Error: {}", e),
    }

    println!("\n=== Testing Table Entry ===");
    let table_json = r#"
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

    let table_value: serde_json::Value = serde_json::from_str(table_json).unwrap();
    match parse_entry(&table_value) {
        Ok(entry) => println!("Parsed: {:?}", entry),
        Err(e) => println!("Error: {}", e),
    }

    println!("\n=== Testing Document Metadata ===");
    let doc_json = r#"
    {
      "_meta": {
        "sources": [
          {
            "id": "TOWORLDS",
            "name": "Tales of the World",
            "url": "https://example.com"
          }
        ]
      }
    }
    "#;
    let doc_value: serde_json::Value = serde_json::from_str(doc_json).unwrap();
    match parse_document(&doc_value) {
        Ok(meta) => println!("Parsed meta: {:?}", meta),
        Err(e) => println!("Meta error: {}", e),
    }
}