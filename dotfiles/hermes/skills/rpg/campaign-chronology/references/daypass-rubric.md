# Day-Pass Detection Rubric (subagent prompt content)

Use this verbatim block inside each per-chapter day-pass subagent prompt. Goal: find every
moment where one or more in-world days elapse between events, so we can infer a running date.

## Assumptions for continuity
- Assume the chapter BEGINS where the previous chapter left off (0 days gap) UNLESS the text states an explicit gap (e.g. "a week later").
- A 'long rest' or overnight = 1 day passes. A 'short rest' (≈1 hr) = 0 days.
- 'the next day' / 'next morning' / 'following day' / 'following morning' = 1 day.
- 'two days later' = 2; 'a few days' = 3 (estimate); 'several days' / 'several days of travel' = 3–4 (estimate, confidence 'estimated'); use stated travel-day numbers when present.
- Continuous action within a single day with no break = 0 days.
- Forward-looking plans ("we'll rest at the lodge") and undepicted future intent are NOT counted.

## Procedure
1. Read the whole chapter (large chapters ~72KB: read in chunks, cover all sections).
2. Walk it section by section (sections marked `## N.NN` or `## Name ...`).
3. For each transition where time elapses, record the marker.

## Output schema (write to <out_path>)
    {
      "chapter": <int>,
      "assumed_start_continuous": true,
      "intervals": [
        {"idx": 1, "marker": "<short verbatim quote>",
         "section": "<section header>",
         "days_elapsed": <int|null>,
         "confidence": "explicit"|"inferred"|"estimated",
         "note": "<why a day passes / uncertainty>"},
        ...
      ],
      "total_days_estimated": <int, sum of days_elapsed across intervals>
    }
- Order intervals by document order. If zero day-passes, write empty intervals array `[]`.
- Verify with `python json.load`.
- IMPORTANT: the `marker` must be a VERBATIM substring of the chapter text so the parent can locate the exact insertion line. If the real phrase differs (e.g. curly quotes), note the fallback token in `note`.
