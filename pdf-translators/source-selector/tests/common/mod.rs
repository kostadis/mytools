#![allow(dead_code)]
use lopdf::{
    Document, Object, Stream,
    content::{Content, Operation},
    dictionary,
};
use std::path::Path;
pub fn pdf(path: &Path, text: &str, date: &str, image: bool) {
    let mut doc = Document::with_version("1.5");
    let pages = doc.new_object_id();
    let font =
        doc.add_object(dictionary! {"Type"=>"Font","Subtype"=>"Type1","BaseFont"=>"Helvetica"});
    let mut resources = dictionary! {"Font"=>dictionary!{"F1"=>font}};
    if image {
        let id=doc.add_object(Stream::new(dictionary!{"Type"=>"XObject","Subtype"=>"Image","Width"=>1,"Height"=>1,"ColorSpace"=>"DeviceRGB","BitsPerComponent"=>8},vec![255,0,0]));
        resources.set("XObject", dictionary! {"Img"=>id});
    }
    let content = Content {
        operations: vec![
            Operation::new("BT", vec![]),
            Operation::new("Tf", vec!["F1".into(), 12.into()]),
            Operation::new("Td", vec![30.into(), 700.into()]),
            Operation::new("Tj", vec![Object::string_literal(text)]),
            Operation::new("ET", vec![]),
        ],
    };
    let contents = doc.add_object(Stream::new(dictionary! {}, content.encode().unwrap()));
    let page=doc.add_object(dictionary!{"Type"=>"Page","Parent"=>pages,"Contents"=>contents,"Resources"=>resources,"MediaBox"=>vec![0.into(),0.into(),612.into(),792.into()]});
    doc.objects.insert(
        pages,
        dictionary! {"Type"=>"Pages","Kids"=>vec![page.into()],"Count"=>1}.into(),
    );
    let root = doc.add_object(dictionary! {"Type"=>"Catalog","Pages"=>pages});
    let date_id = doc.add_object(Object::string_literal(date));
    let info = doc
        .add_object(dictionary! {"Title"=>Object::string_literal("Test Book"),"ModDate"=>date_id});
    doc.trailer.set("Root", root);
    doc.trailer.set("Info", info);
    doc.save(path).unwrap();
}
