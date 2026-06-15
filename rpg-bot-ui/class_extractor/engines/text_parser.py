"""Text-based class extractor for parsed RPGBOT articles."""

import re
from typing import Dict, List, Optional, Any

from class_extractor.base import ClassExtractor, ClassConfig, ClassData
from class_extractor.utils import find_section, clean_description, parse_rating_from_text


class TextClassExtractor(ClassExtractor):
    """Extracts class data from text files (parsed RPGBOT articles)."""
    
    def __init__(self, config: ClassConfig):
        super().__init__(config)
        self._section_names = [
            'Class Features', 'Backgrounds', 'Dragonmark Backgrounds',
            'Species', 'Lorwyn Species', 'Ability Scores',
            'Subclasses', 'Skills', 'Feats', 'Origin Feats',
            'Dragonmark Feats', 'General Feats', 'Epic Boons',
            'Weapons', 'Armor', 'Multiclassing'
        ]
    
    def extract(self, content: str) -> ClassData:
        """Extract class data from text content."""
        # Extract each section
        self._extract_subclasses(content)
        self._extract_class_features(content)
        self._extract_backgrounds(content)
        self._extract_species(content)
        self._extract_ability_scores(content)
        self._extract_skills(content)
        self._extract_feats(content)
        self._extract_epic_boons(content)
        self._extract_weapons(content)
        self._extract_armor(content)
        
        return self.data
    
    def _extract_subclasses(self, content: str):
        """Extract subclass/subclass data."""
        # Look for section headers like "Divine Order (Protector)" that appear as standalone lines
        # These appear after the actual content starts (2nd occurrence in the file)
        
        # Find the 2nd occurrence of "Divine Order (Protector)" or "Divine Order (Thaumaturge)"
        for subclass_name in ['Divine Order (Protector)', 'Divine Order (Thaumaturge)']:
            positions = [m.start() for m in re.finditer(re.escape(subclass_name), content)]
            if len(positions) >= 2:
                # Get content after the 2nd occurrence
                start = positions[1]
                # Find next section
                next_sections = ['Cleric Skills', 'Cleric Feats', 'Cleric Ability Scores']
                end = len(content)
                for next_sec in next_sections:
                    pos = content.find(next_sec, start)
                    if pos != -1 and pos < end:
                        end = pos
                
                section_text = content[start:end]
                # Extract description (first paragraph after header)
                desc_match = re.search(r'\n+(.+?)(?=\n\n|\Z)', section_text, re.DOTALL)
                if desc_match:
                    desc = clean_description(desc_match.group(1), max_length=250)
                    rating = self.get_rating(desc)
                    
                    # Extract just the subclass name (e.g., "Protector" from "Divine Order (Protector)")
                    name_match = re.search(r'\(([^)]+)\)', subclass_name)
                    name = name_match.group(1) if name_match else subclass_name
                    
                    self.data.subclasses.append({
                        "name": name,
                        "r": rating,
                        "d": desc
                    })
    
    def _extract_class_features(self, content: str):
        """Extract class features."""
        # Find the 2nd occurrence of "Cleric Class Features"
        positions = [m.start() for m in re.finditer(r'Cleric Class Features', content)]
        if len(positions) < 2:
            return
        
        start = positions[1]
        # Find next section
        next_sections = ['2024 Cleric Changes', 'Cleric Backgrounds', 'Cleric Skills']
        end = len(content)
        for next_sec in next_sections:
            pos = content.find(next_sec, start)
            if pos != -1 and pos < end:
                end = pos
        
        section = content[start:end]
        
        # Parse numbered features: "1. Spellcasting:", "5. Sear Undead:"
        feat_pattern = r'(\d+)\.\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+):\s*(.*?)(?=\n\n\d+\.|\Z)'
        for match in re.finditer(feat_pattern, section, re.DOTALL):
            level = int(match.group(1))
            name = match.group(2).strip()
            desc = clean_description(match.group(3), max_length=300)
            
            self.data.class_features.append({
                "lv": level,
                "n": name,
                "r": self.get_rating(desc),
                "d": desc
            })
        
        # Parse unnumbered features: "Hit Points:", "Saves:"
        unnumbered_pattern = r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+):\s*(.*?)(?=\n\n\d+\.|\Z)'
        for match in re.finditer(unnumbered_pattern, section, re.MULTILINE | re.DOTALL):
            name = match.group(1).strip()
            # Skip if it's a numbered feature
            if name in ['Spellcasting', 'Sear Undead', 'Blessed Strikes', 'Divine Intervention', 
                       'Improved Blessed Strikes', 'Greater Divine Intervention']:
                continue
            
            desc = clean_description(match.group(2), max_length=200)
            if name in ['Hit Points', 'Saves', 'Proficiencies', 'Channel Divinity', 
                       'Divine Spark', 'Turn Undead']:
                self.data.class_features.append({
                    "lv": 0,
                    "n": name,
                    "r": self.get_rating(desc),
                    "d": desc
                })
    
    def _extract_backgrounds(self, content: str):
        """Extract background data."""
        # Find the 2nd occurrence of "Cleric Backgrounds"
        positions = [m.start() for m in re.finditer(r'Cleric Backgrounds', content)]
        if len(positions) < 2:
            return
        
        start = positions[1]
        # Find next section
        next_sections = ['Dragonmark Backgrounds', 'Cleric Species', 'Cleric Skills']
        end = len(content)
        for next_sec in next_sections:
            pos = content.find(next_sec, start)
            if pos != -1 and pos < end:
                end = pos
        
        section = content[start:end]
        
        bg_pattern = r'^([A-Z][a-zA-Z ]+)\s*\([^)]*\)\s*:\s*(.+)$'
        current_bg = None
        current_rating = 'orange'
        current_desc = []
        
        for line in section.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            bg_match = re.match(bg_pattern, line)
            if bg_match:
                # Save previous background
                if current_bg:
                    self.data.backgrounds.append({
                        "n": current_bg,
                        "r": current_rating,
                        "d": clean_description(' '.join(current_desc), max_length=200)
                    })
                
                current_bg = bg_match.group(1).strip()
                current_desc = [bg_match.group(2).strip()]
                current_rating = self.get_rating(current_desc[0])
            elif current_bg:
                current_desc.append(line)
        
        # Don't forget the last one
        if current_bg:
            self.data.backgrounds.append({
                "n": current_bg,
                "r": current_rating,
                "d": clean_description(' '.join(current_desc), max_length=200)
            })
    
    def _extract_species(self, content: str):
        """Extract species data."""
        # Find the 2nd occurrence of "Cleric Species"
        positions = [m.start() for m in re.finditer(r'Cleric Species', content)]
        if len(positions) < 2:
            return
        
        start = positions[1]
        # Find next section
        next_sections = ['Lorwyn Species', 'Cleric Ability Scores', 'Cleric Skills']
        end = len(content)
        for next_sec in next_sections:
            pos = content.find(next_sec, start)
            if pos != -1 and pos < end:
                end = pos
        
        section = content[start:end]
        
        # Pattern: "Species Name (Source): Description"
        sp_pattern = r'^([A-Z][a-zA-Z ]+)\s+\((PHB|EFotA|ABoH|FRHoF|LFL)\):\s*(.+)$'
        
        for line in section.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            sp_match = re.match(sp_pattern, line)
            if sp_match:
                name = sp_match.group(1).strip()
                source = sp_match.group(2).strip()
                desc = clean_description(sp_match.group(3), max_length=200)
                rating = self.get_rating(desc)
                
                self.data.species.append({
                    "n": name,
                    "src": source,
                    "r": rating,
                    "d": desc
                })
        
        sp_pattern = r'^([A-Z][a-zA-Z ]+)\s+(PHB|EFotA|ABoH|FRHoF|LFL)\s*:\s*(.+)$'
        current_sp = None
        current_src = None
        current_rating = 'orange'
        current_desc = []
        
        for line in section.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            sp_match = re.match(sp_pattern, line)
            if sp_match:
                # Save previous species
                if current_sp:
                    self.data.species.append({
                        "n": current_sp,
                        "src": current_src,
                        "r": current_rating,
                        "d": clean_description(' '.join(current_desc), max_length=200)
                    })
                
                current_sp = sp_match.group(1).strip()
                current_src = sp_match.group(2).strip()
                current_desc = [sp_match.group(3).strip()]
                current_rating = self.get_rating(current_desc[0])
            elif current_sp:
                current_desc.append(line)
        
        # Don't forget the last one
        if current_sp:
            self.data.species.append({
                "n": current_sp,
                "src": current_src,
                "r": current_rating,
                "d": clean_description(' '.join(current_desc), max_length=200)
            })
    
    def _extract_ability_scores(self, content: str):
        """Extract ability score notes."""
        # Look for ability score patterns in Divine Order sections
        # These appear as "Str: Description", "Dex: Description", etc.
        ab_pattern = r'^(Str|Dex|Con|Int|Wis|Cha):\s*(.+)$'
        
        # Search in both Divine Order sections
        # Note: We need to find the occurrence AFTER "Cleric Ability Scores" section
        for do_name in ['Divine Order (Protector)', 'Divine Order (Thaumaturge)']:
            # Find all occurrences
            positions = [m.start() for m in re.finditer(re.escape(do_name), content)]
            
            # Find the occurrence that comes after "Cleric Ability Scores"
            ab_scores_pos = [m.start() for m in re.finditer(r'Cleric Ability Scores', content)]
            if len(ab_scores_pos) < 2:
                continue
            
            # Get the 2nd occurrence of "Cleric Ability Scores"
            ab_start = ab_scores_pos[1]
            
            # Find the first Divine Order occurrence after that
            for pos in positions:
                if pos > ab_start:
                    start = pos
                    break
            else:
                continue
            
            # Find next section
            next_sections = ['Point Buy', 'Cleric Skills', 'Cleric Feats']
            end = len(content)
            for next_sec in next_sections:
                p = content.find(next_sec, start)
                if p != -1 and p < end:
                    end = p
            
            section = content[start:end]
            
            for line in section.split('\n'):
                line = line.strip()
                if not line:
                    continue
                
                ab_match = re.match(ab_pattern, line)
                if ab_match:
                    stat = ab_match.group(1)
                    desc = ab_match.group(2).strip()
                    rating = self.get_rating(desc)
                    
                    # Avoid duplicates
                    if not any(note['s'] == stat and note['n'] == desc for note in self.data.ability_notes):
                        self.data.ability_notes.append({
                            "s": stat,
                            "r": rating,
                            "n": desc
                        })
        
        ab_pattern = r'\n(Str|Dex|Con|Int|Wis|Cha):\s*(.+?)(?=\n[A-Z]|\Z)'
        for match in re.finditer(ab_pattern, section):
            stat = match.group(1)
            desc = match.group(2).strip()
            rating = self.get_rating(desc)
            
            self.data.ability_notes.append({
                "s": stat,
                "r": rating,
                "n": desc
            })
    
    def _extract_skills(self, content: str):
        """Extract skill data."""
        # Find the 2nd occurrence of "Cleric Skills"
        positions = [m.start() for m in re.finditer(r'Cleric Skills', content)]
        if len(positions) < 2:
            return
        
        start = positions[1]
        # Find next section
        next_sections = ['Cleric Feats', 'Divine Order (Protector)']
        end = len(content)
        for next_sec in next_sections:
            pos = content.find(next_sec, start)
            if pos != -1 and pos < end:
                end = pos
        
        section = content[start:end]
        
        # Pattern: "Skill Name (Abbrev): Description" where Abbrev is like "Int", "Wis", etc.
        sk_pattern = r'^([A-Z][a-z]+) \([A-Z][a-z]{2}\):\s*(.+)$'
        
        for line in section.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            sk_match = re.match(sk_pattern, line)
            if sk_match:
                name = sk_match.group(1)
                desc = sk_match.group(2).strip()
                rating = self.get_rating(desc)
                
                self.data.skills.append({
                    "n": name,
                    "r": rating,
                    "d": desc
                })
        
        sk_pattern = r'\n([A-Z][a-z]+) \([A-Z]{3}\):\s*(.+?)(?=\n[A-Z][a-z]+ \([A-Z]{3}\)|\Z)'
        for match in re.finditer(sk_pattern, section):
            name = match.group(1)
            desc = match.group(2).strip()
            rating = self.get_rating(desc)
            
            self.data.skills.append({
                "n": name,
                "r": rating,
                "d": desc
            })
    
    def _extract_feats(self, content: str):
        """Extract feat data."""
        # Find the 2nd occurrence of "Cleric Feats"
        positions = [m.start() for m in re.finditer(r'Cleric Feats', content)]
        if len(positions) < 2:
            return
        
        start = positions[1]
        # Find next section
        next_sections = ['Epic Boons', 'Cleric Weapons', 'Cleric Armor']
        end = len(content)
        for next_sec in next_sections:
            pos = content.find(next_sec, start)
            if pos != -1 and pos < end:
                end = pos
        
        section = content[start:end]
        
        feat_pattern = r'\n([A-Z][a-zA-Z ]+)\s+\((PHB|EFotA|ABoH|FRHoF|LFL)\):\s*(.+?)(?=\n[A-Z][a-zA-Z ]+ \((?:PHB|EFotA|ABoH|FRHoF|LFL)\)|\Z)'
        
        # Determine category based on section position
        origin_pos = section.find('Origin Feats')
        general_pos = section.find('General Feats')
        dragonmark_pos = section.find('Dragonmark Feats')
        
        for match in re.finditer(feat_pattern, section):
            name = match.group(1).strip()
            source = match.group(2).strip()
            desc = match.group(3).strip()
            
            # Determine category
            if origin_pos != -1 and (general_pos == -1 or match.start() < general_pos):
                category = "origin"
            elif dragonmark_pos != -1 and (general_pos == -1 or match.start() < general_pos):
                category = "dragonmark"
            else:
                category = "general"
            
            self.data.feats.append({
                "n": name,
                "r": self.get_rating(desc),
                "cat": category,
                "d": desc
            })
    
    def _extract_epic_boons(self, content: str):
        """Extract epic boon data."""
        # Find the 2nd occurrence of "Epic Boons"
        positions = [m.start() for m in re.finditer(r'Epic Boons', content)]
        if len(positions) < 2:
            return
        
        start = positions[1]
        # Find next section
        next_sections = ['Cleric Weapons', 'Cleric Armor', 'Cleric Multiclassing']
        end = len(content)
        for next_sec in next_sections:
            pos = content.find(next_sec, start)
            if pos != -1 and pos < end:
                end = pos
        
        section = content[start:end]
        
        boon_pattern = r'\n([A-Z][a-zA-Z ]+\s+[A-Z][a-zA-Z ]+)\s+\((PHB|EFotA|ABoH|FRHoF|LFL)\):\s*(.+?)(?=\n[A-Z][a-zA-Z ]+ \((?:PHB|EFotA|ABoH|FRHoF|LFL)\)|\Z)'
        
        for match in re.finditer(boon_pattern, section):
            name = match.group(1).strip()
            source = match.group(2).strip()
            desc = match.group(3).strip()
            
            self.data.epic_boons.append({
                "n": name,
                "r": self.get_rating(desc),
                "d": desc
            })
    
    def _extract_weapons(self, content: str):
        """Extract weapon data."""
        # Find the 2nd occurrence of "Cleric Weapons"
        positions = [m.start() for m in re.finditer(r'Cleric Weapons', content)]
        if len(positions) < 2:
            return
        
        start = positions[1]
        # Find next section
        next_sections = ['Cleric Armor', 'Cleric Multiclassing']
        end = len(content)
        for next_sec in next_sections:
            pos = content.find(next_sec, start)
            if pos != -1 and pos < end:
                end = pos
        
        section = content[start:end]
        
        wp_pattern = r'\n([A-Z][a-z]+(?:, [A-Z][a-z]+)?)\s*:\s*(.+?)(?=\n[A-Z][a-z]+(?:, [A-Z][a-z]+)?\s*:|\Z)'
        for match in re.finditer(wp_pattern, section):
            name = match.group(1).strip()
            desc = match.group(2).strip()
            rating = self.get_rating(desc)
            
            self.data.weapons.append({
                "n": name,
                "r": rating,
                "d": desc
            })
    
    def _extract_armor(self, content: str):
        """Extract armor data."""
        # Find the 2nd occurrence of "Cleric Armor"
        positions = [m.start() for m in re.finditer(r'Cleric Armor', content)]
        if len(positions) < 2:
            return
        
        start = positions[1]
        # Find next section
        next_sections = ['Cleric Multiclassing']
        end = len(content)
        for next_sec in next_sections:
            pos = content.find(next_sec, start)
            if pos != -1 and pos < end:
                end = pos
        
        section = content[start:end]
        
        ar_pattern = r'\n([A-Z][a-zA-Z ]+)\s*:\s*(.+?)(?=\n[A-Z][a-zA-Z ]+|\Z)'
        for match in re.finditer(ar_pattern, section):
            name = match.group(1).strip()
            desc = match.group(2).strip()
            rating = self.get_rating(desc)
            
            self.data.armor.append({
                "n": name,
                "r": rating,
                "d": desc
            })
