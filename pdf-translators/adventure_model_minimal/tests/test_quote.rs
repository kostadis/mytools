use adventure_model_minimal::{parse_entry, parse_document};

#[test]
fn test_quote_with_name() {
    let json_str = r#"
    {
      "type": "quote",
      "text": "The forest remembers what you do.",
      "by": "The Old Druid",
      "from": "Whispering Woods, Page 12",
      "name": "Prophecy",
      "id": "prophecy-1"
    }
    "#;

    let value: serde_json::Value = serde_json::from_str(json_str).unwrap();
    let entry = parse_entry(&value).unwrap();

    if let adventure_model_minimal::Entry::Quote(quote) = entry {
        assert_eq!(quote.text, "The forest remembers what you do.".to_string());
        assert_eq!(quote.by, Some("The Old Druid".to_string()));
        assert_eq!(quote.from, Some("Whispering Woods, Page 12".to_string()));
        assert_eq!(quote.name, Some("Prophecy".to_string()));
        assert_eq!(quote.id, Some("prophecy-1".to_string()));
    } else {
        panic!("Expected Quote entry");
    }
}