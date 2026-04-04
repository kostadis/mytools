---
description: Kostadis Tribunal (v10) — forensic architectural audit. Tests whether the author thinks in systems (Architecturalist) or syntax (Script Scribe). Issues PASS/FAIL verdicts on Truth, Silicon, Atomicity, IDM, and Entity Integrity.
argument-hint: [document, architecture description, or question]
---

From the perspective of the **Unified Kostadis Engine (v10)**, evaluate the provided content as a forensic audit of its architectural reasoning. Test the "Tribunal" (the ability to judge state), not just the "Scribe" (the ability to write syntax).

## PHASE 1: ARCHITECTURAL FACT-PATTERN

Ingest the Gravity Evidence across three vectors:
- **Identity Drift:** Does the document treat objects as Transient Objects in RAM, ignoring Management Gravity and Reconciliation Loops?
- **Metadata Orphans:** Does the document acknowledge Horcruxes (dangling state, orphaned references)?
- **Reconciliation Failure:** Does the document assume success at input[0] implies success at input[infinity]?

Also evaluate:
- **The Source of Truth:** Is it a Cached Lie (whiteboard/diagram) or a Silicon Truth?
- **The Ack Protocol:** Does it distinguish Software Ack ("Looks good") from hardware-confirmed state?
- **The Consistency Model:** Is it Single-threaded, synchronous, and local — or does it acknowledge distributed reality?

## PHASE 2: THE KOSTADIS VERDICT

**1. The Truth Audit (Federated vs. Replicated)**
- Does the document assume Global Visibility of data?
- In a production system, data is Sharded. Can you "access" it, or is it on a different continent?
- Verdict: PASS / FAIL

**2. The Silicon Check (Ack Protocol)**
- Does "success" mean returning the right value, or does it mean the hardware confirmed the write?
- Does it ignore the Transactional Boundary?
- Verdict: PASS / FAIL

**3. The Atomicity Review (Intent-Based Consistency)**
- Does the design create Lethal Gravity via centralized bottlenecks (e.g., central Redis counters)?
- Does it propose Federated Authority with asynchronous reconciliation?
- Verdict: PASS / FAIL

**4. The IDM Review (The Abstraction Check)**
- Does the document reason about Logical Datasets or just Infrastructure Proxies (strings, integers, arrays)?
- Does it demonstrate Management Gravity awareness?
- Verdict: PASS / FAIL

**5. The Entity Integrity Review (The Horcrux Check)**
- Does the design leave Metadata Orphans when entities move between shards?
- Is there a Reconciliation Protocol for entity migration?
- Verdict: PASS / FAIL

Output format:

```
## PHASE 1: ARCHITECTURAL FACT-PATTERN
[Findings on Identity Drift, Metadata Orphans, Reconciliation, Source of Truth, Ack Protocol, Consistency Model]

## PHASE 2: THE KOSTADIS VERDICT
### 1. Truth Audit — [Observation] · Verdict: PASS/FAIL
### 2. Silicon Check — [Observation] · Verdict: PASS/FAIL
### 3. Atomicity Review — [Observation] · Verdict: PASS/FAIL
### 4. IDM Review — [Observation] · Verdict: PASS/FAIL
### 5. Entity Integrity Review — [Observation] · Verdict: PASS/FAIL

## FINAL CONCLUSION
[Is this author a Script Scribe or an Architecturalist? Overall grade.]
```

---

$ARGUMENTS
