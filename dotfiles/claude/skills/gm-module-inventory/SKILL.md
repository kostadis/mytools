---
name: gm-module-inventory
description: Build a canonical proper-noun inventory for a published D&D module — NPCs, locations, items, factions, events/concepts. Output goes to docs/background/<module-name>-inventory.md. Invoke as /gm-module-inventory <module-name> [source_id] or /gm-module-inventory <module-name> [path/to/source.md].
tools: Read, Bash, Agent, Write, Workflow
---

# gm-module-inventory

Produces a `docs/background/<module-name>-inventory.md` file — a canonical proper-noun registry for a published module. Purpose: pass this to any LLM or tool as ground truth for names and spelling so confusions and hallucinated variants don't propagate.

## When to invoke

Trigger phrases:
- `/gm-module-inventory <module-name>`
- "build an inventory for {module}"
- "create a proper-noun list for {module}"
- "canonical name list for {module}"

## Inputs

- **Module name** — the slug used in the output filename, e.g. `out-of-the-abyss` → `out-of-the-abyss-inventory.md`
- **Source** — one of:
  - A 5etools source ID (e.g. `OotA`, `CoS`, `ToA`) — preferred for published modules
  - A path to a source markdown file (e.g. `docs/background/Out of the Abyss.md`)
  - If not supplied, try to infer the source ID from `mcp__5etools__list_sources` by matching the module name

## Output location

Always write to: `docs/background/<module-name>-inventory.md`

Relative to the campaign directory (detect from CWD or ask).

## Required format

Match the format of `notes/sessions/candlekeep_murders_module_inventory.md` exactly. Sections in order:

1. **NPCs** — grouped by race/role (Drow, Demon Lords, Prisoners, Duergar, etc. — use what the module's content naturally produces). Each entry: `- **Name** / **Alias** — brief identifying note (race, role, notable trait)`
2. **Deities** — named gods that appear in the module
3. **Locations** — grouped by geography/area. Nested under region → sub-location if the module has that structure
4. **Planes / cosmology** — named planes, realms, dimensions referenced
5. **Items / spells / artifacts** — named magic items, named spells, unique weapons, key objects
6. **Factions / titles / ranks** — organizations, formal titles, social structures
7. **Events / concepts / dates** — named events, holidays, in-fiction terms

### Formatting rules

- Use `**Bold**` for every proper noun on first occurrence in its section
- Use ` / ` to separate aliases/alternate spellings for the same entity on one line
- Keep descriptions tight (one clause), not summaries
- Do NOT include page numbers or section references — this is a name list, not a concordance
- Omit generic creature types (goblins, orcs) unless they have proper names or unique identifiers
- Include alternate spellings you've seen in the text — canonicalize to the most common form first

## Extraction strategy

### If using 5etools (preferred)

1. Call `mcp__5etools__get_toc` with the source ID to get the chapter list
2. Launch a Workflow that fans out `mcp__5etools__get_section` across all chapters in parallel — one agent per chapter
3. Each agent returns structured JSON (see schema below)
4. **Do all merging and file writing in the workflow JS or a direct Python/Bash script — never pass the raw extraction JSON blob to an agent.** A 20-chapter module produces ~1M tokens of raw extraction data; passing it to a single merge agent will exceed context and kill the response mid-stream.
5. Write the file via `Bash` (Python script inline) rather than via a Write-tool agent for large outputs

### If using a source markdown file

1. Check the file size. If > 200KB, use a Workflow to read in chunks (split by chapter headings)
2. Each agent reads one chunk and returns the same structured schema
3. Merge, deduplicate, sort, write — same rule: do it in JS or Bash, not in an agent

## Schema for per-chapter extraction agents

Each extraction agent should return JSON matching:

```json
{
  "npcs": [{"name": "...", "aliases": [], "note": "...", "group": "race or role label, e.g. drow / duergar / prisoner / demon lord / historical"}],
  "deities": [{"name": "...", "note": "..."}],
  "locations": [{"name": "...", "region": "parent location or area name", "note": "..."}],
  "planes": [{"name": "...", "note": "..."}],
  "items": [{"name": "...", "note": "..."}],
  "factions": [{"name": "...", "note": "..."}],
  "events": [{"name": "...", "note": "..."}]
}
```

**NPC `group` field**: instruct agents to use a **race or role label** (e.g. `drow`, `duergar`, `prisoner`, `demon lord`, `historical`), NOT a location name. LLMs naturally produce race labels; trying to force location-based grouping at extraction time produces inconsistent results. Map race labels → display groups in the merge step.

## Merge and dedup (do this in JS or Python, not in an agent)

```python
import re

def norm_key(name):
    return re.sub(r"['\s\-/]", '', name.lower()).strip()

def merge_list(arrays, extra_field=None):
    seen = {}
    for arr in arrays:
        for item in arr:
            k = norm_key(item['name'])
            if k in seen:
                ex = seen[k]
                existing_aliases = set(ex.get('aliases', []))
                for a in item.get('aliases', []): existing_aliases.add(a)
                ex['aliases'] = sorted(existing_aliases)
                if len(item.get('note', '')) > len(ex.get('note', '')):
                    ex['note'] = item['note']
                if extra_field and item.get(extra_field) and not ex.get(extra_field):
                    ex[extra_field] = item[extra_field]
            else:
                seen[k] = dict(item)
    return sorted(seen.values(), key=lambda x: x['name'].lower())
```

Rules:
- Case-insensitive name matching via `norm_key`
- Merge aliases; keep the longer/more specific note
- Do NOT merge locations that share only a word ("Candlekeep" ≠ "Candlekeep Gatehouse")
- After merging, build a race-label → display-group map for NPCs and write it as a Python dict before running (inspect what group labels the extractors actually produced — they vary by module)

## Writing the file

**Do not use a Write-tool agent for files > ~30KB.** The agent has to regenerate the full content as a tool-call argument (doubling the token cost) and will time out or die mid-stream on large outputs. Instead:

```bash
python3 << 'PYEOF'
# ... merge logic ...
with open('/path/to/output.md', 'w') as f:
    f.write(output)
PYEOF
```

## Header block

```markdown
# {Module Full Name} — module proper-noun inventory

Complete inventory of NPCs, locations, items, factions, and concepts
extracted from {source description}.

This is the **source-material list**, not any homebrew adaptation.
For campaign-specific NPC adjustments see relevant notes files.

---
```

## Steps

1. Resolve the source (5etools ID or file path)
2. Get the TOC / chapter list
3. Launch Workflow — fan out extraction across all chapters (one agent per chapter, structured JSON schema)
4. When workflow completes, **read the cached results from the journal** (type=`result` entries with `npcs` key) or from the workflow return value
5. Run merge/dedup in Python/Bash locally
6. Write the file via Python inline script
7. Report: file path, line count, counts per category

## What this skill is NOT for

- Campaign-specific NPC dossiers (use `gm-npc-build`)
- Tracking which NPCs are alive/dead in your campaign (use `campaign_state.md`)
- Session prep (use `gm-session-prep`)
- Anything homebrew — this is source-material only
