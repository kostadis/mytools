# Evidence from text and other sessions

## Reference normalization

Build training records with `session`, `cue_index`, `speaker`, `timing`, and
`text`. Store each reference path and SHA-256 separately. Use exactly one
selected original per session and inspect content for duplicate exports or
concatenation; filenames and different hashes alone do not prove independence.
Never train on the target's newly guessed labels.

Use an explicit alias mapping, for example `Kostadis Roussos -> Kostadis` and
`Nikhil Reddy Mettupally -> Nikhil`. These are examples, not defaults. Remove only
recognized label metadata before style analysis. WebVTT voice tags may need a
separate extractor. Unmapped labels and channels such as `Audio shared by ...`
are excluded and counted, not silently assigned to the account owner. Exclude
ambiguous or multiple-speaker reference cues from single-person training.

The helper's `read_vtt(Path(...))` returns `(raw_text, lines, header_end, cues)`;
each cue has `cue_index`, `cue_id`, `timing`, and `text`. It does not normalize
reference speaker names. Detect recognized prefixes in the first payload line,
strip only that prefix in training text, and preserve subsequent lines. Read
sample excerpts to check the export format before processing all references.

The summary may clarify that the GM is speaking an NPC, but its prose may itself
have inferred dialogue ownership. Treat it as context, never ground truth for
exact utterances or a substitute for reading the target.

## Optional style classifier

Use this only when it adds a useful second opinion. The original workflow used
scikit-learn with the following estimator (import only if already available):

```python
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.linear_model import LogisticRegression

def make_classifier():
    return Pipeline([
        ("features", FeatureUnion([
            ("word", TfidfVectorizer(ngram_range=(1, 2), min_df=2,
                                     sublinear_tf=True)),
            ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5),
                                     min_df=3, sublinear_tf=True)),
        ])),
        ("classifier", LogisticRegression(C=2, class_weight="balanced",
                                          max_iter=1000, random_state=0)),
    ])
```

Fit on label-stripped reference text and canonical human names. Save the most
likely name and `max(predict_proba(...))` separately as `style_hint` and
`style_score`, not as the final speaker or contextual confidence. These scores
are uncalibrated. Do not let content-word overlap, NPC names, or rules vocabulary
override a coherent exchange.

For cross-session checks, hold out each entire session in turn. Refit both
vectorizers and the classifier only on the other sessions; splitting adjacent
cues randomly leaks similar phrases and context across train and test sets.
Skip folds with insufficient training classes or vocabulary and disclose them.
With fewer than two usable sessions, report cross-session validation unavailable.
Use the full reference set for target hints only after the held-out checks.

For each held-out session report sample count, agreement with existing labels,
per-speaker performance where useful, and a baseline that predicts the most
common **training** label on every test cue. An optional selected subset uses
at least five whitespace-delimited words and style score >= 0.8; report both
its size/coverage and its agreement. Never turn a selected subset's performance
into a claim about every cue, or confuse the class distribution with measured
accuracy. Existing Zoom labels can also be wrong.

## Contextual traps demonstrated by session 001

The two people were Kostadis (GM) and Nikhil (Zenvon's player). References from
002, 003, 005, 006, and 011 supplied 5,661 labeled cues after excluding 93
screen-share cues. These facts illustrate the method and are not prerequisites
or a reusable roster.

- GM descriptive prose sometimes resembled the player's lexical patterns.
  Follow the ongoing scene narration rather than the classifier.
- “Does this belong to one of you?” was the player addressing companions;
  a question addressed to a group did not make the speaker the GM.
- A character's first-person “I know…” was GM-voiced dialogue. Character
  perspective and physical speaker are separate decisions.
- Repeated “I know, I know” in map troubleshooting belonged to the GM despite
  the apparent phrasing match to the player. Short repetition is weak evidence.
- A source cue could combine GM narration and a brief player interruption.
  The final best-guess output used the dominant speaker for the cue and retained
  uncertainty in its record rather than inventing sub-cue timing.

The initial draft left 80 cues unknown and 6 possibly mixed. After the user said
“these are unimportant - use your best guess,” the working copy assigned all
1,389 cues (910 Kostadis, 479 Nikhil). Its weak guesses stayed weak, while the
review stopped being pending. This is the intended distinction between
**accepted for use** and **independently confirmed identity**.
