//! Which of the editor's three panes are shown, with the rule that at least
//! one always is. Pure core logic with no egui dependency.

#[derive(Clone, Copy, PartialEq, Debug)]
pub enum Pane {
    Outline,
    Source,
    Preview,
}

/// The shown/hidden state of the three panes. At least one is always shown:
/// the fields are private, so they change only through `set`, which refuses
/// to hide the last one.
#[derive(Clone, Copy, PartialEq, Debug)]
pub struct Panes {
    outline: bool,
    editor: bool,
    preview: bool,
}

impl Default for Panes {
    fn default() -> Self {
        Self {
            outline: true,
            editor: true,
            preview: true,
        }
    }
}

impl Panes {
    pub fn is_shown(&self, pane: Pane) -> bool {
        match pane {
            Pane::Outline => self.outline,
            Pane::Source => self.editor,
            Pane::Preview => self.preview,
        }
    }

    /// Whether `pane` may be hidden: false only when it is the one pane shown.
    pub fn can_hide(&self, pane: Pane) -> bool {
        !self.is_shown(pane) || self.shown_count() > 1
    }

    /// Shows or hides `pane`. Returns false, changing nothing, when that
    /// would hide the last shown pane.
    pub fn set(&mut self, pane: Pane, shown: bool) -> bool {
        if !shown && !self.can_hide(pane) {
            return false;
        }
        *match pane {
            Pane::Outline => &mut self.outline,
            Pane::Source => &mut self.editor,
            Pane::Preview => &mut self.preview,
        } = shown;
        true
    }

    fn shown_count(&self) -> usize {
        [self.outline, self.editor, self.preview]
            .iter()
            .filter(|&&shown| shown)
            .count()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const ALL: [Pane; 3] = [Pane::Outline, Pane::Source, Pane::Preview];

    #[test]
    fn all_panes_start_shown() {
        let panes = Panes::default();
        assert!(ALL.iter().all(|&p| panes.is_shown(p)));
    }

    #[test]
    fn hiding_the_editor_hides_only_the_editor() {
        let mut panes = Panes::default();
        assert!(panes.set(Pane::Source, false));
        assert!(!panes.is_shown(Pane::Source));
        assert!(panes.is_shown(Pane::Outline) && panes.is_shown(Pane::Preview));
    }

    #[test]
    fn the_last_shown_pane_cannot_be_hidden() {
        let mut panes = Panes::default();
        assert!(panes.set(Pane::Outline, false));
        assert!(panes.set(Pane::Source, false));
        assert!(!panes.can_hide(Pane::Preview));
        let before = panes;
        assert!(!panes.set(Pane::Preview, false));
        assert_eq!(panes, before);
        // Showing one that is already shown, or hiding one that is hidden,
        // is allowed and changes nothing.
        assert!(panes.set(Pane::Preview, true));
        assert!(panes.set(Pane::Outline, false));
        assert_eq!(panes, before);
    }

    /// Every non-empty combination reaches every other one a toggle at a
    /// time, and no sequence of toggles hides all three.
    #[test]
    fn every_combination_is_reachable_and_none_is_empty() {
        let combos: Vec<[bool; 3]> = (1..8)
            .map(|bits| [bits & 1 != 0, bits & 2 != 0, bits & 4 != 0])
            .collect();
        let reach = |from: [bool; 3]| -> Panes {
            let mut panes = Panes::default();
            for (i, &p) in ALL.iter().enumerate() {
                if !from[i] {
                    assert!(panes.set(p, false), "could not reach {from:?}");
                }
            }
            panes
        };
        for &from in &combos {
            for &to in &combos {
                let mut panes = reach(from);
                // Show first, then hide, so no step passes through all-hidden.
                for (i, &p) in ALL.iter().enumerate() {
                    if to[i] {
                        assert!(panes.set(p, true));
                    }
                }
                for (i, &p) in ALL.iter().enumerate() {
                    if !to[i] {
                        assert!(panes.set(p, false), "{from:?} -> {to:?}");
                    }
                }
                let got: Vec<bool> = ALL.iter().map(|&p| panes.is_shown(p)).collect();
                assert_eq!(got, to.to_vec());
            }
        }
        for &from in &combos {
            let mut panes = reach(from);
            for &p in &ALL {
                panes.set(p, false);
            }
            assert!(
                ALL.iter().any(|&p| panes.is_shown(p)),
                "all hidden from {from:?}"
            );
        }
    }
}
