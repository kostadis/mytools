# PDF-to-5etools Pipeline Architecture

## Overview

This pipeline converts tabletop RPG PDFs into [5etools](https://5e.tools) homebrew JSON format, then provides a suite of tools to validate, repair, and refine the output.

## Core Conversion Pipeline

```mermaid
flowchart TB
    %% ── Input ──────────────────────────────────────────────
    PDF[/"📄 PDF File"/]

    %% ── Classifier ────────────────────────────────────────
    PDF --> classify{"What kind of PDF?"}

    classify -->|"Digital text,<br/>no bookmarks"| orig_digital["pdf_to_5etools.py"]
    classify -->|"Scanned / image-heavy,<br/>no bookmarks"| orig_ocr["pdf_to_5etools_ocr.py"]
    classify -->|"AD&D 1e/2e module,<br/>no bookmarks"| orig_1e["pdf_to_5etools_1e.py"]
    classify -->|"Digital text,<br/>has bookmarks"| toc_digital["pdf_to_5etools_toc.py"]
    classify -->|"Scanned / image-heavy,<br/>has bookmarks"| toc_ocr["pdf_to_5etools_ocr_toc.py"]
    classify -->|"AD&D 1e/2e module,<br/>has bookmarks"| toc_1e["pdf_to_5etools_1e_toc.py"]

    %% ── Shared infrastructure ──────────────────────────────
    subgraph shared ["Shared Infrastructure"]
        direction TB
        cli_args["cli_args.py<br/><i>shared argparse setup</i>"]
        claude_api["claude_api.py<br/><i>API calls, retry, validation</i>"]
        pdf_utils["pdf_utils.py<br/><i>TOC extraction, TocNode tree</i>"]
        adventure_model["adventure_model.py<br/><i>typed data model</i>"]
    end

    orig_digital --> shared
    orig_ocr --> shared
    orig_1e --> shared
    toc_digital --> shared
    toc_ocr --> shared
    toc_1e --> shared

    shared --> raw_json[/"adventure.json<br/>(raw conversion output)"/]

    %% ── Styling ────────────────────────────────────────────
    style PDF fill:#4a90d9,color:#fff,stroke:#2a6cb8
    style raw_json fill:#5cb85c,color:#fff,stroke:#3d8b3d
    style shared fill:#f0f0f0,stroke:#999
    style classify fill:#f5a623,color:#fff,stroke:#d4891a
```

## Original Converter Internals (page-count chunking)

```mermaid
flowchart LR
    PDF[/"PDF"/] --> extract["Text Extraction<br/><i>PyMuPDF / Tesseract</i>"]
    extract --> headers["Running-Header<br/>Detection<br/><i>remove repeating<br/>headers/footers</i>"]
    headers --> annotate["Annotation<br/><i>[H1] [H2] [H3]<br/>[italic] [bold]<br/>[TABLE] [INSET]</i>"]
    annotate --> chunk["Page-Count<br/>Chunking<br/><i>6 / 4 / 3 pages<br/>per chunk</i>"]
    chunk --> toc_hint["TOC Hint<br/>Injection<br/><i>prepend bookmarks<br/>to each chunk</i>"]
    toc_hint --> claude["Claude API<br/><i>JSON array of<br/>5etools entries</i>"]
    claude --> post["Post-Processing<br/><i>merge chunks,<br/>hoist stray entries,<br/>assign IDs, build TOC</i>"]
    post --> JSON[/"adventure.json"/]

    style PDF fill:#4a90d9,color:#fff
    style JSON fill:#5cb85c,color:#fff
    style claude fill:#7b68ee,color:#fff
```

## TOC-Driven Converter Internals (bookmark chunking)

```mermaid
flowchart LR
    PDF[/"PDF"/] --> extract["Text Extraction<br/><i>PyMuPDF / Tesseract</i>"]
    PDF --> toc_parse["TOC Parsing<br/><i>get_toc_tree() →<br/>TocNode tree with<br/>page ranges</i>"]
    extract --> toc_chunk["TOC-Driven<br/>Chunking<br/><i>one chunk per<br/>top-level bookmark;<br/>split oversized by<br/>children or pages</i>"]
    toc_parse --> toc_chunk
    toc_chunk --> claude["Claude API<br/><i>fills entries[] for<br/>a single chapter;<br/>validation retry on<br/>structural errors</i>"]
    claude --> assemble["Assembly<br/><i>SectionEntry objects<br/>from TocNode tree +<br/>Claude results</i>"]
    toc_parse --> build_toc["Build TOC<br/><i>from bookmarks,<br/>not Claude output</i>"]
    assemble --> model["adventure_model<br/><i>typed dataclasses,<br/>auto-assign IDs</i>"]
    build_toc --> model
    model --> JSON[/"adventure.json"/]

    style PDF fill:#4a90d9,color:#fff
    style JSON fill:#5cb85c,color:#fff
    style claude fill:#7b68ee,color:#fff
    style model fill:#e67e22,color:#fff
```

## Validation & Refinement Workflow

After conversion, the output is validated and iteratively refined using specialized tools. The typical workflow moves left-to-right, but any tool can be re-run at any point.

```mermaid
flowchart TB
    raw[/"adventure.json<br/>(raw conversion)"/]

    %% ── Phase 1: Validate ─────────────────────────────────
    subgraph validate ["Phase 1 — Validate"]
        direction TB
        va["validate_adventure.py<br/><i>structure, entry types,<br/>TOC alignment, ID uniqueness</i>"]
        vt["validate_tags.py<br/><i>unknown {@tag} references<br/>--fix replaces with plain text</i>"]
    end

    raw --> validate

    %% ── Phase 2: Structure repair ─────────────────────────
    subgraph structure ["Phase 2 — Structure Repair"]
        direction TB
        fix["fix_adventure_json.py<br/><i>normalize chapters,<br/>fix TOC/data index drift</i>"]
        toc_fixer["toc_fixer.py :5102<br/><i>heuristic nesting repair<br/>using PDF bookmarks +<br/>keyed-room patterns</i>"]
        toc_editor["toc_editor.py :5101<br/><i>manual TOC reordering,<br/>section demote/promote</i>"]
    end

    validate --> structure

    %% ── Phase 3: Content editing ──────────────────────────
    subgraph editing ["Phase 3 — Content Editing"]
        direction TB
        editor["adventure_editor.py :5104<br/><i>block tree editor with<br/>preview, undo, flags,<br/>multi-select, tag toolbar</i>"]
    end

    structure --> editing

    %% ── Phase 4: Monster extraction ───────────────────────
    subgraph monsters ["Phase 4 — Monster Extraction"]
        direction TB
        monster_ed["monster_editor.py :5103<br/><i>interactive stat block<br/>discovery & extraction</i>"]
        extract_m["extract_monsters.py<br/><i>CLI batch extraction</i>"]
    end

    editing --> monsters
    monsters --> bestiary[/"bestiary.json"/]

    %% ── Phase 5: 1e-specific post-processing ──────────────
    subgraph oneE ["Phase 5 — 1e Post-Processing (if applicable)"]
        direction TB
        convert_1e["convert_1e_to_5e.py<br/><i>rewrite 1e mechanics<br/>for 5e: AC, saves,<br/>encounter insets</i>"]
    end

    editing --> oneE

    %% ── Patch tools (re-enter pipeline) ────────────────────
    subgraph patch ["Patch Tools (re-convert specific sections)"]
        direction TB
        merge["merge_patch.py<br/><i>re-convert pages,<br/>splice into existing JSON</i>"]
        patch_ch["patch_5e_chapters.py<br/><i>re-convert chapters<br/>from 1e source</i>"]
    end

    editing --> patch
    patch -->|"re-enters pipeline<br/>at Phase 1"| validate

    %% ── Final output ──────────────────────────────────────
    validate --> final_check{All checks pass?}
    final_check -->|Yes| done[/"Final adventure.json<br/>+ bestiary.json<br/><i>ready for 5etools</i>"/]
    final_check -->|No| structure

    %% ── Styling ────────────────────────────────────────────
    style raw fill:#5cb85c,color:#fff
    style bestiary fill:#5bc0de,color:#fff
    style done fill:#2ecc71,color:#fff
    style final_check fill:#f5a623,color:#fff
    style validate fill:#fff3cd,stroke:#ffc107
    style structure fill:#d1ecf1,stroke:#0dcaf0
    style editing fill:#e2d9f3,stroke:#7b68ee
    style monsters fill:#d4edda,stroke:#28a745
    style oneE fill:#f8d7da,stroke:#dc3545
    style patch fill:#e2e3e5,stroke:#6c757d
```

## Shared Module Dependencies

```mermaid
flowchart TB
    %% ── Converters ─────────────────────────────────────────
    subgraph converters ["Converters"]
        direction LR
        c1["pdf_to_5etools"]
        c2["pdf_to_5etools_ocr"]
        c3["pdf_to_5etools_1e"]
        t1["pdf_to_5etools_toc"]
        t2["pdf_to_5etools_ocr_toc"]
        t3["pdf_to_5etools_1e_toc"]
    end

    %% ── Shared libraries ──────────────────────────────────
    cli["cli_args.py"]
    api["claude_api.py"]
    pdf["pdf_utils.py"]
    model["adventure_model.py"]
    va["validate_adventure.py"]
    fix["fix_adventure_json.py"]

    %% ── Original converters → shared ──────────────────────
    c1 --> cli
    c2 --> cli
    c3 --> cli
    c1 --> api
    c2 --> api
    c3 --> api
    c1 --> pdf
    c2 --> pdf
    c3 --> pdf

    %% ── TOC converters → shared ───────────────────────────
    t1 --> api
    t1 --> pdf
    t1 --> model
    t2 --> t1
    t2 --> api
    t2 --> pdf
    t2 --> model
    t3 --> t1
    t3 --> api
    t3 --> pdf
    t3 --> model

    %% ── Lazy imports (TOC → original for extraction) ──────
    t2 -.->|"lazy import<br/>extraction"| c2
    t3 -.->|"lazy import<br/>extraction"| c3

    %% ── Shared library dependencies ───────────────────────
    api --> model
    model --> va

    %% ── Editor tools → shared ─────────────────────────────
    subgraph editors ["Editor Tools"]
        direction LR
        ae["adventure_editor"]
        te["toc_editor"]
        tf["toc_fixer"]
        me["monster_editor"]
    end

    ae --> fix
    te --> fix
    tf --> fix
    tf --> pdf
    me --> api

    %% ── Styling ────────────────────────────────────────────
    style converters fill:#e8f4fd,stroke:#4a90d9
    style editors fill:#f3e8fd,stroke:#7b68ee
    style api fill:#fff3cd,stroke:#ffc107
    style model fill:#fde8d0,stroke:#e67e22
    style pdf fill:#d4edda,stroke:#28a745
    style cli fill:#e2e3e5,stroke:#6c757d
    style va fill:#f8d7da,stroke:#dc3545
    style fix fill:#d1ecf1,stroke:#0dcaf0
```

## Claude API Call Flow

```mermaid
sequenceDiagram
    participant C as Converter
    participant API as claude_api.py
    participant Model as adventure_model.py
    participant Claude as Claude API

    C->>API: call_claude(chunk_text, model, system_prompt)

    API->>Claude: messages.create(system, user_message)
    Claude-->>API: response (JSON text)

    API->>API: _parse_claude_response()

    alt Truncated (stop_reason = max_tokens)
        API->>API: _recover_partial_json()
        API->>Claude: Retry with partial output as context
        Claude-->>API: Continuation response
        API->>API: Merge partial + continuation
    end

    alt Malformed JSON
        API->>API: Split chunk in half
        API->>Claude: Retry first half
        API->>Claude: Retry second half
        Claude-->>API: Two valid responses
        API->>API: Merge halves
    end

    API->>Model: validate_entries(parsed_result)
    Model-->>API: error list

    alt Validation errors found
        API->>Claude: Retry with correction prompt<br/>(includes error list)
        Claude-->>API: Corrected response
        API->>API: _parse_claude_response()
    end

    API-->>C: list[entries]
```

## Web UI (app.py)

```mermaid
flowchart LR
    browser["Browser<br/>:5100"] -->|"upload PDF +<br/>select options"| app["app.py<br/><i>Flask</i>"]
    app -->|"subprocess"| converter["Converter<br/><i>(any of 6)</i>"]
    app -->|"SSE stream"| browser
    converter --> json[/"adventure.json"/]
    json -->|"download link"| browser

    style browser fill:#4a90d9,color:#fff
    style app fill:#e67e22,color:#fff
    style json fill:#5cb85c,color:#fff
```

## Quick Reference: Which Tool When

| Symptom | Tool | Command |
|---------|------|---------|
| Unknown `{@tag}` errors / blank pages | `validate_tags.py --fix` | `python3 validate_tags.py adventure.json --fix` |
| TOC sidebar navigation broken | `fix_adventure_json.py` | `python3 fix_adventure_json.py adventure.json` |
| Sections nested wrong (flat/too deep) | `toc_fixer.py` + PDF | `python3 toc_fixer.py adventure.json --pdf source.pdf` |
| TOC order wrong | `toc_editor.py` | `python3 toc_editor.py adventure.json` |
| Content errors (text, formatting) | `adventure_editor.py` | `python3 adventure_editor.py adventure.json` |
| Missing/bad pages in output | `merge_patch.py` | `python3 merge_patch.py adventure.json patch.json --at N` |
| Need bestiary file for stat blocks | `monster_editor.py` | `python3 monster_editor.py adventure.json` |
| 1e stats need 5e conversion | `convert_1e_to_5e.py` | `python3 convert_1e_to_5e.py input.json output.json` |
| Full structural audit | `validate_adventure.py` | `python3 validate_adventure.py adventure.json` |
