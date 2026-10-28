//! Splits a preview section's Markdown into the runs the preview draws
//! differently: prose that wraps to the pane, and top-level tables and code
//! blocks that keep their lines whole and scroll sideways on their own. Pure
//! core logic with no egui dependency; the source text is never changed.
