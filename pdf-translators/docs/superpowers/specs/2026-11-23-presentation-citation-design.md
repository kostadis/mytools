# Presentation candidates and automatic reader citations

User request: fix the two pilot-01 workflow gaps and rerun a pilot on different files. Keep the five-page content budget, original preservation, cheap factual readers, Sol judgment, and deferred uncertainty. The background library hash scan continues untouched.

## Selected approach

Add a conservative presentation candidate key alongside existing filename keys. Strip recognized suffix labels (No Background, BW/black-and-white, Colour/Color, print variants, Digital, Interactive, Fillable), including labels before retained version/date qualifiers, but preserve language, game-system and volume labels. The new key retains numeric and dotted edition/version qualifiers instead of inheriting their removal from the older title key. Match nonempty remaining titles library-wide and attribute the new relationship as `presentation_candidate`. These relationships propose review, never equivalence, deletion, or chronology. Do not merge every member of a product indiscriminately.

Reader responses no longer need model-transcribed packet IDs. For each claim, Rust resolves the declared source/page/exact quote against an issued reader excerpt with the current group membership and the same recorded source hash. Distinct matching fragments are ambiguous; identical re-exported fragments may share one logical binding. Preserve strict explicit-packet support for existing clients and keep Sol/user decision gates unchanged. Record citation provenance separately from the factual claim. Literal matching does not establish semantic support; retain the Sol audit.

Empty claim arrays are no-ops. Reader fragments exclude mutable claim summaries so normal re-export does not shift their boundaries. Failed export publication cannot add issued packets. Replaying an identical claim retains its initial binding provenance. Database write stages remain sequential; parallel reader jobs consume immutable saved samples.

The alternatives were manually repairing packet IDs (does not scale), treating product siblings as duplicates (unsafe for bundles/languages), and using text matches to exclude files automatically (exceeds sampled evidence). The selected approach adds candidate discovery and deterministic attribution while retaining review boundaries.

## New pilot

Use only products, file paths and content hashes absent from pilot 01. Stage a small locally cached subset of already-hashed sources, preserve original fingerprints, verify copied SHA-256 values, and use independent pilot state. Include presentation labels affected by the fix and different RPG systems. Extract at most five pages per distinct byte content; run bounded cheaper-reader jobs, validate literal citations in Rust, and use Sol for semantic auditing/advisory assessment. Do not import model selection decisions or convert PDFs. Report limits and failures honestly.
