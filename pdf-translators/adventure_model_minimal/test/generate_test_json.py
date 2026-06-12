import sys
sys.path.append('/home/kroussos/src/mytools/pdf-translators')
from adventure_model import *

# Create a test for QuoteEntry
ctx = BuildContext()
q = QuoteEntry(entries=["Test quote"], by="Author", from_="Source", _ctx=ctx, _path="x")
sec = SectionEntry(name="Ch1", entries=[q], _ctx=ctx, _path="data[0]")
doc = HomebrewAdventure.build(name="Test", source="TEST", sections=[sec], ctx=ctx)
with open('test/quote_test.json', 'w') as f:
    f.write(doc.to_json())

# SectionEntry
ctx2 = BuildContext()
sec2 = SectionEntry(name="Section2", entries=["Text"], _ctx=ctx2, _path="data[1]")
doc2 = HomebrewAdventure.build(name="Test2", source="TEST2", sections=[sec2], ctx=ctx2)
with open('test/section_test.json', 'w') as f:
    f.write(doc2.to_json())

# TableEntry
ctx3 = BuildContext()
table = TableEntry(colLabels=["Col1", "Col2"], rows=[["a", "b"]], _ctx=ctx3, _path="x")
sec3 = SectionEntry(name="Table Section", entries=[table], _ctx=ctx3, _path="data[2]")
doc3 = HomebrewAdventure.build(name="Test3", source="TEST3", sections=[sec3], ctx=ctx3)
with open('test/table_test.json', 'w') as f:
    f.write(doc3.to_json())

# ImageEntry
ctx4 = BuildContext()
img_href = ImageHref(type="internal", path="img.png")
img = ImageEntry(href=img_href, title="Image", _ctx=ctx4, _path="x")
sec4 = SectionEntry(name="Image Section", entries=[img], _ctx=ctx4, _path="data[3]")
doc4 = HomebrewAdventure.build(name="Test4", source="TEST4", sections=[sec4], ctx=ctx4)
with open('test/image_test.json', 'w') as f:
    f.write(doc4.to_json())

# ListEntry
ctx5 = BuildContext()
list_entry = ListEntry(items=["Item1", "Item2"], _ctx=ctx5, _path="x")
sec5 = SectionEntry(name="List Section", entries=[list_entry], _ctx=ctx5, _path="data[4]")
doc5 = HomebrewAdventure.build(name="Test5", source="TEST5", sections=[sec5], ctx=ctx5)
with open('test/list_test.json', 'w') as f:
    f.write(doc5.to_json())

# HrEntry
ctx6 = BuildContext()
hr = HrEntry(_ctx=ctx6, _path="x")
sec6 = SectionEntry(name="HR Section", entries=[hr], _ctx=ctx6, _path="data[5]")
doc6 = HomebrewAdventure.build(name="Test6", source="TEST6", sections=[sec6], ctx=ctx6)
with open('test/hr_test.json', 'w') as f:
    f.write(doc6.to_json())

# StatblockEntry
ctx7 = BuildContext()
statblock = StatblockEntry(tag="creature", source="Monster Manual", name="Goblin", _ctx=ctx7, _path="x")
sec7 = SectionEntry(name="Statblock Section", entries=[statblock], _ctx=ctx7, _path="data[6]")
doc7 = HomebrewAdventure.build(name="Test7", source="TEST7", sections=[sec7], ctx=ctx7)
with open('test/statblock_test.json', 'w') as f:
    f.write(doc7.to_json())

# SpellcastingEntry
ctx8 = BuildContext()
spellcasting = SpellcastingEntry(headerEntries=["Cantrips", "1st Level"], _ctx=ctx8, _path="x")
sec8 = SectionEntry(name="Spellcasting Section", entries=[spellcasting], _ctx=ctx8, _path="data[7]")
doc8 = HomebrewAdventure.build(name="Test8", source="TEST8", sections=[sec8], ctx=ctx8)
with open('test/spellcasting_test.json', 'w') as f:
    f.write(doc8.to_json())

# GenericEntry
ctx9 = BuildContext()
generic = GenericEntry(type="unknown", name="Test", _ctx=ctx9, _path="x")
sec9 = SectionEntry(name="Generic Section", entries=[generic], _ctx=ctx9, _path="data[8]")
doc9 = HomebrewAdventure.build(name="Test9", source="TEST9", sections=[sec9], ctx=ctx9)
with open('test/generic_test.json', 'w') as f:
    f.write(doc9.to_json())