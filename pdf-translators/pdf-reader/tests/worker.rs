use lopdf::{
    Document, EncryptionState, EncryptionVersion, Object, Permissions, Stream, dictionary,
};
use serde_json::Value;
use std::process::{Command, Output};

fn fixture(password: Option<&str>, malformed: bool) -> Document {
    let mut d = Document::with_version("1.5");
    let pages = d.new_object_id();
    let font =
        d.add_object(dictionary! {"Type"=>"Font","Subtype"=>"Type1","BaseFont"=>"Helvetica"});
    let resources = d.add_object(dictionary! {"Font"=>dictionary!{"F1"=>font}});
    let form=d.add_object(Stream::new(dictionary!{"Type"=>"XObject","Subtype"=>"Form","BBox"=>vec![0.into(),0.into(),612.into(),792.into()],"Resources"=>resources},b"BT /F1 12 Tf 20 680 Td (Inside Form 123) Tj ET".to_vec()));
    let image=d.add_object(Stream::new(dictionary!{"Type"=>"XObject","Subtype"=>"Image","Width"=>1,"Height"=>1,"ColorSpace"=>"DeviceRGB","BitsPerComponent"=>8}, vec![255,0,37]));
    let content = if malformed {
        b"BT (broken".to_vec()
    } else {
        b"BT /F1 12 Tf 20 700 Td (Hello World) Tj ET /Fm Do /Im Do BT /F1 18 Tf 20 650 Td (D) Tj 1 0 Td /F1 12 Tf (UNGEON) Tj ET BT /F1 12 Tf 20 620 Td (Armor) Tj 100 0 Td (17) Tj ET".to_vec()
    };
    let content = d.add_object(Stream::new(dictionary! {}, content));
    let p1=d.add_object(dictionary!{"Type"=>"Page","Parent"=>pages,"MediaBox"=>vec![0.into(),0.into(),612.into(),792.into()],"Resources"=>dictionary!{"Font"=>dictionary!{"F1"=>font},"XObject"=>dictionary!{"Fm"=>form,"Im"=>image}},"Contents"=>content});
    let p2=d.add_object(dictionary!{"Type"=>"Page","Parent"=>pages,"MediaBox"=>vec![0.into(),0.into(),612.into(),792.into()],"Resources"=>resources});
    d.objects.insert(
        pages,
        dictionary! {"Type"=>"Pages","Kids"=>vec![p1.into(),p2.into()],"Count"=>2}.into(),
    );
    let outlines = d.new_object_id();
    let group = d.new_object_id();
    let a = d.new_object_id();
    let b = d.new_object_id();
    d.objects.insert(
        outlines,
        dictionary! {"Type"=>"Outlines","First"=>group,"Last"=>group,"Count"=>3}.into(),
    );
    d.objects.insert(group,dictionary!{"Title"=>Object::string_literal("Group"),"Parent"=>outlines,"First"=>a,"Last"=>b,"Count"=>2}.into());
    d.objects.insert(a,dictionary!{"Title"=>Object::string_literal("Room"),"Parent"=>group,"Dest"=>vec![p1.into(),"Fit".into()],"Next"=>b}.into());
    d.objects.insert(b,dictionary!{"Title"=>Object::string_literal("Room"),"Parent"=>group,"Dest"=>vec![p2.into(),"Fit".into()],"Prev"=>a}.into());
    let catalog = d.add_object(dictionary! {"Type"=>"Catalog","Pages"=>pages,"Outlines"=>outlines});
    d.trailer.set("Root", catalog);
    if let Some(password) = password {
        d.trailer.set(
            "ID",
            vec![
                Object::string_literal("0123456789abcdef"),
                Object::string_literal("fedcba9876543210"),
            ],
        );
        let state = EncryptionState::try_from(EncryptionVersion::V2 {
            document: &d,
            owner_password: "owner",
            user_password: password,
            key_length: 128,
            permissions: Permissions::all(),
        })
        .unwrap();
        d.encrypt(&state).unwrap();
    }
    d
}
fn run(args: &[&str], password: Option<&str>, malformed: bool) -> (Output, Vec<Value>) {
    let dir = tempfile::tempdir().unwrap();
    let p = dir.path().join("fixture.pdf");
    fixture(password, malformed).save(&p).unwrap();
    let out = Command::new(env!("CARGO_BIN_EXE_rpg-pdf-reader"))
        .arg(args[0])
        .arg(&p)
        .args(&args[1..])
        .output()
        .unwrap();
    let records = String::from_utf8(out.stdout.clone())
        .unwrap()
        .lines()
        .map(|line| serde_json::from_str(line).unwrap())
        .collect();
    (out, records)
}
#[test]
fn inspect_keeps_structural_and_duplicate_outlines() {
    let (o, r) = run(&["inspect"], None, false);
    assert!(o.status.success(), "{:?}", o);
    assert_eq!(r[0]["protocol"], 1);
    assert_eq!(r[0]["page_count"], 2);
    assert_eq!(
        r[0]["outline"],
        serde_json::json!([{"level":1,"title":"Group","page":null},{"level":2,"title":"Room","page":1},{"level":2,"title":"Room","page":2}])
    );
    assert_eq!(r.len(), 2);
    assert_eq!(r[1]["complete"], true);
}
#[test]
fn extracts_forms_images_words_tables_and_empty_pages() {
    let (o, r) = run(&["extract"], None, false);
    assert!(o.status.success(), "{:?}", o);
    let text = r[1]["text"].as_str().unwrap();
    for needle in ["Hello World", "Inside Form 123", "DUNGEON", "Armor", "17"] {
        assert!(text.contains(needle), "missing {needle}: {text:?}");
    }
    assert_eq!(r[2]["text"], "");
    assert_eq!(r.last().unwrap()["emitted"], 2);
}
#[test]
fn selection_sorted_deduplicated() {
    let (o, r) = run(&["extract", "--pages", "2,1-2"], None, false);
    assert!(o.status.success());
    assert_eq!(r[0]["requested"], serde_json::json!([1, 2]));
    assert_eq!(r[1]["page"], 1);
    assert_eq!(r[2]["page"], 2);
}
#[test]
fn invalid_selection_is_exit_two_without_text() {
    for spec in ["0", "3", "2-1", "garbage", ""] {
        let (o, r) = run(&["extract", "--pages", spec], None, false);
        assert_eq!(o.status.code(), Some(2), "{spec}");
        assert!(!r.iter().any(|x| x["type"] == "page"));
    }
}
#[test]
fn empty_password_encryption_preserves_references_and_text() {
    let (o, r) = run(&["extract"], Some(""), false);
    assert!(o.status.success(), "{:?}", o);
    assert!(r[1]["text"].as_str().unwrap().contains("Inside Form 123"));
    assert_eq!(r[0]["outline"][2]["page"], 2);
}
#[test]
fn password_required_is_not_an_empty_success() {
    let (o, r) = run(&["extract"], Some("secret"), false);
    assert_eq!(o.status.code(), Some(1));
    assert!(r.iter().any(|x| x["code"] == "password_required"));
    assert_eq!(r.last().unwrap()["complete"], false);
}
#[test]
fn malformed_content_is_incomplete_not_panic_success() {
    let (o, r) = run(&["extract"], None, true);
    assert_eq!(o.status.code(), Some(1));
    assert!(r.iter().any(|x| x["type"] == "error"));
    assert_eq!(r.last().unwrap()["complete"], false);
}

#[test]
fn encrypted_image_filter_and_indirect_references_survive() {
    for password in [None, Some("")] {
        let mut d = fixture(password, false);
        let mut bytes = vec![];
        d.save_to(&mut bytes).unwrap();
        let loaded = Document::load_mem_with_options(
            &bytes,
            lopdf::LoadOptions::with_filter(rpg_pdf_reader::reader::filter),
        )
        .unwrap();
        assert_eq!(loaded.get_pages().len(), 2);
        let mut images = 0;
        let mut forms = 0;
        for o in loaded.objects.values() {
            if let Ok(s) = o.as_stream() {
                match s.dict.get(b"Subtype").and_then(Object::as_name).ok() {
                    Some(b"Image") => {
                        images += 1;
                        assert!(s.content.is_empty());
                    }
                    Some(b"Form") => {
                        forms += 1;
                        assert!(!s.content.is_empty());
                    }
                    _ => {}
                }
            }
        }
        assert_eq!((images, forms), (1, 1));
    }
}
#[test]
fn compressed_objects_and_unicode_outlines() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("compressed.pdf");
    let mut d = fixture(None, false);
    let root = d
        .catalog()
        .unwrap()
        .get(b"Outlines")
        .unwrap()
        .as_reference()
        .unwrap();
    let group = d
        .get_dictionary(root)
        .unwrap()
        .get(b"First")
        .unwrap()
        .as_reference()
        .unwrap();
    let mut title = vec![0xfe, 0xff];
    for c in "Café 龍".encode_utf16() {
        title.extend(c.to_be_bytes());
    }
    d.get_object_mut(group)
        .unwrap()
        .as_dict_mut()
        .unwrap()
        .set("Title", Object::string_literal(title));
    let mut file = std::fs::File::create(&path).unwrap();
    d.save_modern(&mut file).unwrap();
    drop(file);
    let loaded = Document::load(&path).unwrap();
    assert!(
        loaded
            .reference_table
            .entries
            .values()
            .any(|e| matches!(e, lopdf::xref::XrefEntry::Compressed { .. }))
    );
    let out = Command::new(env!("CARGO_BIN_EXE_rpg-pdf-reader"))
        .arg("extract")
        .arg(path)
        .output()
        .unwrap();
    assert!(out.status.success(), "{:?}", out);
    let records: Vec<Value> = String::from_utf8(out.stdout)
        .unwrap()
        .lines()
        .map(|s| serde_json::from_str(s).unwrap())
        .collect();
    assert_eq!(records[0]["outline"][0]["title"], "Café 龍");
    assert!(records[1]["text"].as_str().unwrap().contains("Inside Form"));
}
