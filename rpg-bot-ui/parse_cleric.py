#!/usr/bin/env python3
"""Parse the Cleric text file and generate JSON for the builder."""

import re
import json

# Find the 2nd occurrence of each section (which is the actual content)
def get_content_section(text, section_name):
    """Get the text of a section from the 2nd occurrence onwards."""
    positions = [m.start() for m in re.finditer(re.escape(section_name), text)]
    if len(positions) >= 2:
        start = positions[1]
        next_sections = [
            'Cleric Class Features', '2024 Cleric Changes from 2014 Rules',
            'Cleric Backgrounds', 'Dragonmark Backgrounds', 'Cleric Species',
            'Lorwyn Species', 'Cleric Ability Scores', 'Divine Order (Protector)',
            'Divine Order (Thaumaturge)', 'Cleric Skills', 'Cleric Feats',
            'Origin Feats', 'Dragonmark Feats', 'General Feats', 'Epic Boons',
            'Cleric Weapons', 'Cleric Armor', 'Cleric Multiclassing'
        ]
        end = len(text)
        for next_sec in next_sections:
            pos = text.find(next_sec, start + len(section_name))
            if pos != -1 and pos < end:
                end = pos
        return text[start:end]
    return None

def get_rating(desc):
    """Determine rating based on description text."""
    desc_lower = desc.lower()
    if 'fantastic' in desc_lower or 'absolutely' in desc_lower or 'essential' in desc_lower or 'amazing' in desc_lower:
        return 'blue'
    elif 'good' in desc_lower or 'great' in desc_lower or 'useful' in desc_lower:
        return 'green'
    elif 'bad' in desc_lower or 'useless' in desc_lower or 'terrible' in desc_lower:
        return 'red'
    elif 'decent' in desc_lower or 'some' in desc_lower:
        return 'orange'
    return 'orange'

def parse_text_file():
    with open('cleric.txt', 'r') as f:
        text = f.read()
    
    data = {
        "name": "Cleric",
        "edition": "2024",
        "ui": {
            "skillPicks": 2,
            "hasExpertise": False,
            "optionalTitle": "Divine Order Options",
            "optionalDesc": "Choose your Divine Order at level 1",
            "subclassDesc": "Chosen at level 1. Divine Orders split clerics between front-line and back-line roles.",
            "featDesc": "General Feats fill your ASI slots. Origin Feats come from your Background.",
            "backgroundNote": "In 2024 D&D, your Background sets ability scores (+2/+1) and grants an Origin Feat. Wisdom is non-negotiable.",
            "multiclassNote": "Clerics can multiclass well with many classes, but the healing focus works best alone.",
            "weaponNote": "Clerics don't get Weapon Mastery slots. Simple or martial weapons depending on Divine Order.",
            "armorNote": "Clerics are proficient in light, medium, and (if Protector) heavy armor, plus shields."
        },
        "subclasses": [],
        "species": [],
        "arrays": [],
        "abilityNotes": [],
        "skills": [],
        "backgrounds": [],
        "feats": [],
        "epicBoons": [],
        "classFeatures": [],
        "weapons": [],
        "armor": []
    }
    
    # ============ SUBCLASSES (Divine Orders) ============
    prot_content = get_content_section(text, 'Divine Order (Protector)')
    thaum_content = get_content_section(text, 'Divine Order (Thaumaturge)')
    
    if prot_content:
        desc_match = re.search(r'Divine Order \(Protector\)\s+(.*?)(?=\n\n|$)', prot_content, re.DOTALL)
        if desc_match:
            desc = desc_match.group(1).strip().replace('\n', ' ')
            data["subclasses"].append({"name": "Protector", "r": "green", "d": desc[:250]})
    
    if thaum_content:
        desc_match = re.search(r'Divine Order \(Thaumaturge\)\s+(.*?)(?=\n\nCleric|$)', thaum_content, re.DOTALL)
        if desc_match:
            desc = desc_match.group(1).strip().replace('\n', ' ')
            data["subclasses"].append({"name": "Thaumaturge", "r": "blue", "d": desc[:250]})
    
    print(f"Subclasses: {len(data['subclasses'])}")
    
    # ============ CLASS FEATURES ============
    cf_content = get_content_section(text, 'Cleric Class Features')
    if cf_content:
        # Parse numbered features first: "1. Spellcasting:", "5. Sear Undead:", etc.
        # Pattern: number followed by period, then feature name with rating
        feat_pattern = r'(\d+)\.\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+):\s*(.*?)(?=\n\n\d+\.|\Z)'
        for match in re.finditer(feat_pattern, cf_content, re.DOTALL):
            level = int(match.group(1))
            name = match.group(2).strip()
            desc = match.group(3).strip().replace('\n', ' ')[:300]
            data["classFeatures"].append({
                "lv": level,
                "n": name,
                "r": get_rating(desc),
                "d": desc
            })
        
        # Also parse unnumbered features: "Hit Points:", "Saves:", "Proficiencies:"
        unnumbered_pattern = r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+):\s*(.*?)(?=\n\n\d+\.|\Z)'
        for match in re.finditer(unnumbered_pattern, cf_content, re.DOTALL):
            name = match.group(1).strip()
            # Skip if it's a numbered feature that we already parsed
            if name in ['Spellcasting', 'Sear Undead', 'Blessed Strikes', 'Divine Intervention', 'Improved Blessed Strikes', 'Greater Divine Intervention']:
                continue
            desc = match.group(2).strip().replace('\n', ' ')[:200]
            # Check if this is one of the unnumbered features
            if name in ['Hit Points', 'Saves', 'Proficiencies', 'Channel Divinity', 'Divine Spark', 'Turn Undead']:
                data["classFeatures"].append({
                    "lv": 0,  # Not a level-based feature
                    "n": name,
                    "r": get_rating(desc),
                    "d": desc
                })
    
    print(f"Class Features: {len(data['classFeatures'])}")
    
    # ============ BACKGROUNDS ============
    bg_content = get_content_section(text, 'Cleric Backgrounds')
    if bg_content:
        bg_end = bg_content.find('Dragonmark Backgrounds')
        if bg_end != -1:
            bg_content = bg_content[:bg_end]
        
        bg_lines = bg_content.split('\n')
        current_bg = None
        current_rating = 'orange'
        current_desc = []
        
        for line in bg_lines:
            line = line.strip()
            if not line:
                continue
            bg_match = re.match(r'^([A-Z][a-zA-Z ]+)\s*\((?:PHB|EFotA|ABoH|FRHoF|LFL)\)\s*:\s*(.+)$', line)
            if bg_match:
                if current_bg:
                    data["backgrounds"].append({"n": current_bg, "r": current_rating, "d": ' '.join(current_desc)[:200]})
                current_bg = bg_match.group(1).strip()
                current_desc = [bg_match.group(2).strip()]
                if 'fantastic' in current_desc[0].lower() or 'perfect' in current_desc[0].lower():
                    current_rating = 'blue'
                elif 'good' in current_desc[0].lower():
                    current_rating = 'green'
                elif 'bad' in current_desc[0].lower():
                    current_rating = 'red'
                else:
                    current_rating = 'orange'
            elif current_bg:
                current_desc.append(line)
        
        if current_bg:
            data["backgrounds"].append({"n": current_bg, "r": current_rating, "d": ' '.join(current_desc)[:200]})
    
    print(f"Backgrounds: {len(data['backgrounds'])}")
    
    # ============ SPECIES ============
    sp_content = get_content_section(text, 'Cleric Species')
    if sp_content:
        sp_end = sp_content.find('Lorwyn Species')
        if sp_end != -1:
            sp_content = sp_content[:sp_end]
        
        sp_lines = sp_content.split('\n')
        current_sp = None
        current_rating = 'orange'
        current_desc = []
        
        for line in sp_lines:
            line = line.strip()
            if not line:
                continue
            sp_match = re.match(r'^([A-Z][a-zA-Z ]+)\s+((?:PHB|EFotA|ABoH|FRHoF|LFL))\s*:\s*(.+)$', line)
            if sp_match:
                if current_sp:
                    data["species"].append({"n": current_sp, "src": current_src, "r": current_rating, "d": ' '.join(current_desc)[:200]})
                current_sp = sp_match.group(1).strip()
                current_src = sp_match.group(2).strip()
                current_desc = [sp_match.group(3).strip()]
                if 'fantastic' in current_desc[0].lower() or 'best' in current_desc[0].lower():
                    current_rating = 'blue'
                elif 'good' in current_desc[0].lower():
                    current_rating = 'green'
                elif 'bad' in current_desc[0].lower():
                    current_rating = 'red'
                else:
                    current_rating = 'orange'
            elif current_sp:
                current_desc.append(line)
        
        if current_sp:
            data["species"].append({"n": current_sp, "src": current_src, "r": current_rating, "d": ' '.join(current_desc)[:200]})
    
    print(f"Species: {len(data['species'])}")
    
    # ============ ABILITY NOTES ============
    ab_content = get_content_section(text, 'Cleric Ability Scores')
    if ab_content:
        prot_end = ab_content.find('Divine Order (Protector)')
        if prot_end != -1:
            ab_content = ab_content[:prot_end]
        
        ab_pattern = r'\n(Str|Dex|Con|Int|Wis|Cha):\s*(.+?)(?=\n[A-Z]|\Z)'
        for match in re.finditer(ab_pattern, ab_content):
            stat = match.group(1)
            desc = match.group(2).strip()
            rating = 'orange'
            if 'primary' in desc.lower() or 'crucial' in desc.lower():
                rating = 'blue'
            elif 'dump' in desc.lower():
                rating = 'red'
            elif 'good' in desc.lower() or 'important' in desc.lower():
                rating = 'green'
            data["abilityNotes"].append({"s": stat, "r": rating, "n": desc})
    
    print(f"Ability Notes: {len(data['abilityNotes'])}")
    
    # ============ SKILLS ============
    sk_content = get_content_section(text, 'Cleric Skills')
    if sk_content:
        sk_end = sk_content.find('Cleric Feats')
        if sk_end != -1:
            sk_content = sk_content[:sk_end]
        
        sk_pattern = r'\n([A-Z][a-z]+) \([A-Z]{3}\):\s*(.+?)(?=\n[A-Z][a-z]+ \([A-Z]{3}\)|\Z)'
        for match in re.finditer(sk_pattern, sk_content):
            name = match.group(1)
            desc = match.group(2).strip()
            rating = 'orange'
            if 'crucial' in desc.lower() or 'best' in desc.lower():
                rating = 'blue'
            elif 'good' in desc.lower() or 'important' in desc.lower() or 'great' in desc.lower():
                rating = 'green'
            elif 'skip' in desc.lower() or 'useless' in desc.lower():
                rating = 'red'
            data["skills"].append({"n": name, "r": rating, "d": desc})
    
    print(f"Skills: {len(data['skills'])}")
    
    # ============ FEATS ============
    feats_content = get_content_section(text, 'Cleric Feats')
    if feats_content:
        origin_start = feats_content.find('Origin Feats')
        general_start = feats_content.find('General Feats')
        dragonmark_start = feats_content.find('Dragonmark Feats')
        epic_start = feats_content.find('Epic Boons')
        
        if origin_start != -1:
            origin_end = general_start if general_start != -1 else dragonmark_start if dragonmark_start != -1 else epic_start if epic_start != -1 else len(feats_content)
            origin_section = feats_content[origin_start:origin_end]
            feat_pattern = r'\n([A-Z][a-zA-Z ]+)\s+((?:PHB|EFotA|ABoH|FRHoF|LFL)):\s*(.+?)(?=\n[A-Z][a-zA-Z ]+ \((?:PHB|EFotA|ABoH|FRHoF|LFL)\)|\Z)'
            for match in re.finditer(feat_pattern, origin_section):
                name = match.group(1).strip()
                source = match.group(2).strip()
                desc = match.group(3).strip()
                data["feats"].append({"n": name, "r": get_rating(desc), "cat": "origin", "d": desc})
        
        if general_start != -1:
            general_end = dragonmark_start if dragonmark_start != -1 else epic_start if epic_start != -1 else len(feats_content)
            general_section = feats_content[general_start:general_end]
            for match in re.finditer(feat_pattern, general_section):
                name = match.group(1).strip()
                source = match.group(2).strip()
                desc = match.group(3).strip()
                data["feats"].append({"n": name, "r": get_rating(desc), "cat": "general", "d": desc})
    
    print(f"Feats: {len(data['feats'])}")
    
    # ============ EPIC BOONS ============
    if epic_start != -1:
        epic_section = feats_content[epic_start:]
        boon_pattern = r'\n([A-Z][a-zA-Z ]+\s+[A-Z][a-zA-Z ]+)\s+((?:PHB|EFotA|ABoH|FRHoF|LFL)):\s*(.+?)(?=\n[A-Z][a-zA-Z ]+ \((?:PHB|EFotA|ABoH|FRHoF|LFL)\)|\Z)'
        for match in re.finditer(boon_pattern, epic_section):
            name = match.group(1).strip()
            source = match.group(2).strip()
            desc = match.group(3).strip()
            data["epicBoons"].append({"n": name, "r": get_rating(desc), "d": desc})
    
    print(f"Epic Boons: {len(data['epicBoons'])}")
    
    # ============ WEAPONS ============
    wp_content = get_content_section(text, 'Cleric Weapons')
    if wp_content:
        wp_end = wp_content.find('Cleric Armor')
        if wp_end != -1:
            wp_content = wp_content[:wp_end]
        
        wp_pattern = r'\n([A-Z][a-z]+(?:, [A-Z][a-z]+)?)\s*:\s*(.+?)(?=\n[A-Z][a-z]+(?:, [A-Z][a-z]+)?\s*:|\Z)'
        for match in re.finditer(wp_pattern, wp_content):
            name = match.group(1).strip()
            desc = match.group(2).strip()
            rating = 'green'
            if 'good' in desc.lower() or 'great' in desc.lower() or 'best' in desc.lower():
                rating = 'green'
            elif 'iconic' in desc.lower():
                rating = 'green'
            data["weapons"].append({"n": name, "r": rating, "d": desc})
    
    print(f"Weapons: {len(data['weapons'])}")
    
    # ============ ARMOR ============
    ar_content = get_content_section(text, 'Cleric Armor')
    if ar_content:
        ar_end = ar_content.find('Cleric Multiclassing')
        if ar_end != -1:
            ar_content = ar_content[:ar_end]
        
        ar_pattern = r'\n([A-Z][a-zA-Z ]+)\s*:\s*(.+?)(?=\n[A-Z][a-zA-Z ]+|\Z)'
        for match in re.finditer(ar_pattern, ar_content):
            name = match.group(1).strip()
            desc = match.group(2).strip()
            rating = 'orange'
            if 'good' in desc.lower() or 'great' in desc.lower():
                rating = 'green'
            elif 'essential' in desc.lower():
                rating = 'blue'
            data["armor"].append({"n": name, "r": rating, "d": desc})
    
    print(f"Armor: {len(data['armor'])}")
    
    return data


if __name__ == "__main__":
    data = parse_text_file()
    
    # Write JSON
    with open('data/cleric-2024.json', 'w') as f:
        json.dump(data, f, indent=2)
    
    print("\n=== Summary ===")
    print(f"Subclasses: {len(data['subclasses'])}")
    print(f"Species: {len(data['species'])}")
    print(f"Arrays: {len(data['arrays'])}")
    print(f"Ability Notes: {len(data['abilityNotes'])}")
    print(f"Skills: {len(data['skills'])}")
    print(f"Backgrounds: {len(data['backgrounds'])}")
    print(f"Feats: {len(data['feats'])}")
    print(f"Epic Boons: {len(data['epicBoons'])}")
    print(f"Class Features: {len(data['classFeatures'])}")
    print(f"Weapons: {len(data['weapons'])}")
    print(f"Armor: {len(data['armor'])}")
    print("\nWritten to: data/cleric-2024.json")
