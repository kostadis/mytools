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

#[test]
fn overprinted_glyphs_are_searchable_without_collapsing_real_letters() {
    let mut d = fixture(None, false);
    let page_id = *d.get_pages().get(&1).unwrap();
    let id = d
        .get_dictionary(page_id)
        .unwrap()
        .get(b"Contents")
        .unwrap()
        .as_reference()
        .unwrap();
    let stream = d.get_object_mut(id).unwrap().as_stream_mut().unwrap();
    stream.content.extend_from_slice(b" BT /F1 12 Tf 20 580 Td (Bookkeeper 100) Tj ET BT /F1 12 Tf 20 560 Td (Shadow) Tj ET BT /F1 12 Tf 20.05 560.05 Td (Shadow) Tj ET BT /F1 12 Tf 20.1 560.1 Td (Shadow) Tj ET");
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("shadow.pdf");
    d.save(&path).unwrap();
    let out = Command::new(env!("CARGO_BIN_EXE_rpg-pdf-reader"))
        .arg("extract")
        .arg(path)
        .output()
        .unwrap();
    assert!(out.status.success());
    let records: Vec<Value> = String::from_utf8(out.stdout)
        .unwrap()
        .lines()
        .map(|s| serde_json::from_str(s).unwrap())
        .collect();
    let text = records[1]["text"].as_str().unwrap();
    assert!(text.contains("Bookkeeper 100"));
    assert_eq!(text.matches("Shadow").count(), 1, "{text}");
}

#[test]
fn embedded_truetype_cmap_recovers_cid_digits_without_tounicode() {
    // A minimal SFNT with a Unicode cmap: '0' -> glyph 2, '1' -> glyph 3.
    // RawFace's table reader needs no copyrighted font outline data.
    let mut cmap = vec![0, 0, 0, 1, 0, 3, 0, 1, 0, 0, 0, 12, 0, 0, 1, 6, 0, 0];
    let mut glyphs = vec![0u8; 256];
    glyphs[b'0' as usize] = 2;
    glyphs[b'1' as usize] = 3;
    cmap.extend(glyphs);
    let mut ttf = vec![0, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0];
    ttf.extend(b"cmap");
    ttf.extend([0, 0, 0, 0]);
    ttf.extend(28u32.to_be_bytes());
    ttf.extend((cmap.len() as u32).to_be_bytes());
    ttf.extend(cmap);
    let mut d = fixture(None, false);
    let file = d.add_object(Stream::new(dictionary! {}, ttf));
    let descriptor=d.add_object(dictionary!{"Type"=>"FontDescriptor","FontName"=>"TestFont","Flags"=>4,"FontBBox"=>vec![0.into(),0.into(),1000.into(),1000.into()],"Ascent"=>1000,"Descent"=>0,"CapHeight"=>1000,"StemV"=>80,"FontFile2"=>file});
    let descendant=d.add_object(dictionary!{"Type"=>"Font","Subtype"=>"CIDFontType2","BaseFont"=>"TestFont","CIDSystemInfo"=>dictionary!{"Registry"=>Object::string_literal("Adobe"),"Ordering"=>Object::string_literal("Identity"),"Supplement"=>0},"FontDescriptor"=>descriptor,"DW"=>500,"CIDToGIDMap"=>"Identity"});
    let font=d.add_object(dictionary!{"Type"=>"Font","Subtype"=>"Type0","BaseFont"=>"TestFont","Encoding"=>"Identity-H","DescendantFonts"=>vec![descendant.into()]});
    let content = d.add_object(Stream::new(
        dictionary! {},
        b"BT /Fc 12 Tf 20 700 Td <0003000200020002> Tj ET".to_vec(),
    ));
    let page_id = *d.get_pages().get(&1).unwrap();
    let page = d.get_object_mut(page_id).unwrap().as_dict_mut().unwrap();
    page.set("Resources", dictionary! {"Font"=>dictionary!{"Fc"=>font}});
    page.set("Contents", content);
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("cmap.pdf");
    d.save(&path).unwrap();
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
    assert_eq!(records[1]["text"], "1000");
}

#[test]
fn unmapped_cid_is_a_reviewable_error_not_missing_text() {
    let mut d = fixture(None, false);
    let descriptor=d.add_object(dictionary!{"Type"=>"FontDescriptor","FontName"=>"Unknown","Flags"=>4,"FontBBox"=>vec![0.into(),0.into(),1000.into(),1000.into()],"Ascent"=>1000,"Descent"=>0,"CapHeight"=>1000,"StemV"=>80});
    let cid=d.add_object(dictionary!{"Type"=>"Font","Subtype"=>"CIDFontType2","BaseFont"=>"Unknown","CIDSystemInfo"=>dictionary!{"Registry"=>Object::string_literal("Adobe"),"Ordering"=>Object::string_literal("Identity"),"Supplement"=>0},"FontDescriptor"=>descriptor,"DW"=>500});
    let font=d.add_object(dictionary!{"Type"=>"Font","Subtype"=>"Type0","BaseFont"=>"Unknown","Encoding"=>"Identity-H","DescendantFonts"=>vec![cid.into()]});
    let content = d.add_object(Stream::new(
        dictionary! {},
        b"BT /Fc 12 Tf 20 700 Td <1234> Tj ET".to_vec(),
    ));
    let id = *d.get_pages().get(&1).unwrap();
    let page = d.get_object_mut(id).unwrap().as_dict_mut().unwrap();
    page.set("Resources", dictionary! {"Font"=>dictionary!{"Fc"=>font}});
    page.set("Contents", content);
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("unknown.pdf");
    d.save(&path).unwrap();
    let out = Command::new(env!("CARGO_BIN_EXE_rpg-pdf-reader"))
        .arg("extract")
        .arg(path)
        .output()
        .unwrap();
    assert_eq!(out.status.code(), Some(1));
}

#[test]
fn same_form_at_distinct_positions_is_not_mistaken_for_overprint() {
    let mut d = fixture(None, false);
    let id = *d.get_pages().get(&1).unwrap();
    let content = d
        .get_dictionary(id)
        .unwrap()
        .get(b"Contents")
        .unwrap()
        .as_reference()
        .unwrap();
    d.get_object_mut(content)
        .unwrap()
        .as_stream_mut()
        .unwrap()
        .content
        .extend_from_slice(b" q 1 0 0 1 0 -100 cm /Fm Do Q q 1 0 0 1 100 -100 cm /Fm Do Q");
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("forms.pdf");
    d.save(&path).unwrap();
    let out = Command::new(env!("CARGO_BIN_EXE_rpg-pdf-reader"))
        .arg("extract")
        .arg(path)
        .output()
        .unwrap();
    assert!(out.status.success());
    let records: Vec<Value> = String::from_utf8(out.stdout)
        .unwrap()
        .lines()
        .map(|s| serde_json::from_str(s).unwrap())
        .collect();
    assert_eq!(
        records[1]["text"]
            .as_str()
            .unwrap()
            .matches("Inside Form 123")
            .count(),
        3
    );
}

#[test]
fn forms_can_reuse_a_font_resource_name_with_different_encodings() {
    let mut d = fixture(None, false);
    let font=d.add_object(dictionary!{"Type"=>"Font","Subtype"=>"Type1","BaseFont"=>"Helvetica","Encoding"=>dictionary!{"BaseEncoding"=>"WinAnsiEncoding","Differences"=>vec![65.into(),"Z".into()]}});
    let form=d.add_object(Stream::new(dictionary!{"Type"=>"XObject","Subtype"=>"Form","BBox"=>vec![0.into(),0.into(),612.into(),792.into()],"Resources"=>dictionary!{"Font"=>dictionary!{"F1"=>font}}},b"BT /F1 12 Tf 50 500 Td (A) Tj ET".to_vec()));
    let id = *d.get_pages().get(&1).unwrap();
    let page = d.get_object_mut(id).unwrap().as_dict_mut().unwrap();
    let content = page.get(b"Contents").unwrap().as_reference().unwrap();
    page.get_mut(b"Resources")
        .unwrap()
        .as_dict_mut()
        .unwrap()
        .get_mut(b"XObject")
        .unwrap()
        .as_dict_mut()
        .unwrap()
        .set("Other", form);
    d.get_object_mut(content)
        .unwrap()
        .as_stream_mut()
        .unwrap()
        .content
        .extend_from_slice(b" /Other Do");
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("fonts.pdf");
    d.save(&path).unwrap();
    let out = Command::new(env!("CARGO_BIN_EXE_rpg-pdf-reader"))
        .arg("extract")
        .arg(path)
        .output()
        .unwrap();
    assert!(out.status.success());
    let records: Vec<Value> = String::from_utf8(out.stdout)
        .unwrap()
        .lines()
        .map(|s| serde_json::from_str(s).unwrap())
        .collect();
    assert!(
        records[1]["text"].as_str().unwrap().contains('Z'),
        "{:?}",
        records[1]
    );
}

#[test]
fn decompression_limits_have_resource_failure_code() {
    let error = pdf_extract::OutputError::PdfError(lopdf::Error::Decompress(
        lopdf::DecompressError::MemoryLimitExceeded { limit: 64 },
    ));
    assert_eq!(
        rpg_pdf_reader::reader::content_error_code(&error),
        "resource_failure"
    );
}

#[test]
fn unreadable_existing_input_is_not_misreported_as_malformed_pdf() {
    let error = lopdf::Error::IO(std::io::Error::new(
        std::io::ErrorKind::PermissionDenied,
        "permission denied",
    ));
    let (code, message) = rpg_pdf_reader::reader::load_error(&error);
    assert_eq!(code, "unreadable_input");
    assert!(message.contains("permission denied"));
}
