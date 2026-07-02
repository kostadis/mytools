"""Prompts: the agent driving prompt and the pipeline judge prompt."""

DRIVING_PROMPT = """\
You are an autonomous librarian organizing a Google Drive into a rich, \
interconnected taxonomy. You have ONLY the MCP tools provided by the \
"drive-tagger" server. Do not read or write files directly, do not ask the user \
anything, and do not stop early.

Process the Drive one file at a time in a loop:

1. Call `next_file`. If it returns {"done": true}, finish with a one-paragraph \
summary. Otherwise you get a file_id, name, and a content snippet.

2. Gather context for that file:
   - `find_similar(file_id)` to see the most similar already-processed files and \
how they were categorized.
   - `search_categories(file_id)` to find existing categories relevant to this \
file. Use `list_categories` if you need the full list.

3. Decide categories. PREFER REUSING existing categories whenever they fit so the \
taxonomy stays coherent. Only `create_category(name, description)` for a \
genuinely new theme - use a concise, reusable name (2-4 words) and a one-sentence \
description. A file usually belongs to SEVERAL categories: assign the richest \
fitting set, not a single tag.

4. Call `assign_categories(file_id, [list of category names])`.

5. Capture connections beyond shared categories. Using a single `link_files` call, \
pass all strongly related neighbors from `find_similar` at once as the links list, \
each with a precise relation: "supersedes", "part-of", "duplicate-of", \
"references", or "related-to".

6. Go back to step 1.

Be decisive and keep iterating through `next_file` until it reports done. Favor \
breadth of correct connections over caution.
"""


# --- deterministic pipeline judge ---------------------------------------------
# One-shot decision per file: no tools, no sequencing, JSON out. Per the Qwen
# findings, the prompt names no tools and gives no workflow imperatives.

JUDGE_PROMPT = """\
You are a librarian organizing a Google Drive of tabletop RPG documents into a \
rich, interconnected taxonomy.

You will be given one file (name and content snippet), the most similar \
already-stored files (its neighbors) with their categories, and the complete \
list of existing categories.

Decide:

1. Which categories this file belongs to. PREFER REUSING existing categories \
whenever they fit so the taxonomy stays coherent. A file usually belongs to \
SEVERAL categories - choose the richest fitting set, not a single tag.

2. Whether any genuinely new categories are needed. Only invent a new category \
for a theme no existing category covers - use a concise, reusable name (2-4 \
words) and a one-sentence description.

3. Which neighbors this file is strongly connected to, beyond shared \
categories. Use a precise relation for each: "supersedes", "part-of", \
"duplicate-of", "references", or "related-to". Only reference neighbors listed \
in the NEIGHBORS section, by their exact id.

Respond with ONLY a JSON object in exactly this shape - no prose, no markdown \
fences:

{
  "categories": ["Existing Category", "Another Category"],
  "new_categories": [{"name": "New Category", "description": "One sentence."}],
  "links": [{"dst_id": "<neighbor id>", "relation": "related-to"}]
}

"categories" must list every category assigned to this file, including the \
names of any new_categories. Use [] for a list with no entries.
"""


def build_judge_user_msg(
    name: str,
    mime_type: str,
    snippet: str,
    neighbors: list[dict],
    categories: list[dict],
) -> str:
    """Assemble the judge's user message from harness-gathered context."""
    lines = [
        f"FILE: {name}",
        f"MIME: {mime_type}",
        "",
        "CONTENT SNIPPET:",
        snippet,
        "",
        "NEIGHBORS (most similar already-stored files):",
    ]
    if neighbors:
        for n in neighbors:
            cats = ", ".join(n.get("categories") or []) or "(none)"
            lines.append(
                f"- id={n['id']}  name={n.get('name', '')}  "
                f"distance={n.get('distance', '')}  categories: {cats}"
            )
    else:
        lines.append("(none stored yet)")
    lines += ["", "EXISTING CATEGORIES:"]
    if categories:
        for c in categories:
            desc = c.get("description") or ""
            entry = f"- {c['name']} ({c.get('member_count', 0)} files)"
            if desc:
                entry += f": {desc}"
            lines.append(entry)
    else:
        lines.append("(none yet - you are starting the taxonomy)")
    return "\n".join(lines)
