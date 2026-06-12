use regex::Regex;
use crate::validation::BuildContext;

// Known tags from 5etools render.js (derived from validate_adventure.py)
pub const KNOWN_TAGS: [&str; 111] = [
    "5etools", "5etoolsImg", "ability", "actResponse", "actSave",
    "actSaveFail", "actSaveFailBy", "actSaveSuccess", "actSaveSuccessOrFail",
    "actTrigger", "action", "adventure", "area", "atk", "atkr",
    "autodice", "b", "background", "bold", "book", "boon", "card",
    "chance", "charoption", "cite", "class", "classFeature", "code",
    "coinflip", "color", "comic", "comicH1", "comicH2", "comicH3",
    "comicH4", "comicNote", "condition", "creature", "creatureFluff",
    "cult", "d20", "damage", "dc", "dcYourSpellSave", "deck", "deity",
    "dice", "disease", "facility", "feat", "filter", "font", "footnote",
    "h", "hazard", "help", "highlight", "hit", "hitYourSpellAttack",
    "hom", "homebrew", "i", "initiative", "italic", "item",
    "itemMastery", "itemProperty", "kbd", "language", "legroup", "link",
    "loader", "m", "note", "object", "optfeature", "psionic",
    "quickref", "race", "raceFluff", "recharge", "recipe", "reward",
    "s", "s2", "savingThrow", "scaledamage", "scaledice", "sense",
    "skill", "skillCheck", "spell", "status", "strike", "strikeDouble",
    "style", "sub", "subclass", "subclassFeature", "sup", "table",
    "tip", "trap", "u", "u2", "underline", "underlineDouble", "unit",
    "variantrule", "vehicle", "vehupgrade",
];

// Tag regex pattern: {@tagname ...}
lazy_static::lazy_static! {
    pub static ref TAG_RE: Regex = Regex::new(r"\{@(\w+)([^}]*)\}").unwrap();
}

/// Check {@tag} references and brace balance in a string.
pub fn validate_tags(text: &str, path: &str, ctx: &mut BuildContext) {
    // Check for unknown tags
    for cap in TAG_RE.captures_iter(text) {
        let tag = &cap[1];
        if !KNOWN_TAGS.contains(&tag) {
            ctx.error(format!(
                "{}: unknown tag '{{@{}}}' in: ...{}...",
                path, tag, cap.get(0).map(|m| m.as_str()).unwrap_or("")
            ));
        }
    }

    // Check for unbalanced braces
    let mut depth = 0;
    for ch in text.chars() {
        if ch == '{' {
            depth += 1;
        } else if ch == '}' {
            depth -= 1;
            if depth < 0 {
                ctx.warn(format!("{}: unbalanced closing brace", path));
                break;
            }
        }
    }
    if depth > 0 {
        ctx.warn(format!("{}: unbalanced opening brace ({} unclosed)", path, depth));
    }
}

/// Validate a string field for tags.
pub fn validate_string_field(text: Option<&str>, field_name: &str, path: &str, ctx: &mut BuildContext) {
    if let Some(text) = text {
        validate_tags(text, &format!("{}.{}", path, field_name), ctx);
    }
}
