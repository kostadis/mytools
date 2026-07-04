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

3. Decide categories. Every category is ONE facet: a single aesthetic, genre, \
content-type, or subject. A file usually has SEVERAL facets, so give it several \
separate one-facet tags - e.g. a whimsical adventure module about talking cats \
gets "Absurdist", "Adventures", "Feline". PREFER REUSING existing categories \
whenever they fit so the taxonomy stays coherent. Only \
`create_category(name, description)` when no existing category names a facet this \
file has - name it as a single facet in one or two words, with a one-sentence \
description. Assign the richest set of one-facet tags that describe the file.

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

# The curated facet vocabulary — ONE controlled list, maintained by the human.
# Each category is a single facet on one of four orthogonal axes; a document
# usually spans several axes and so gets several one-facet tags. Seeded from the
# accepted canonicals in reports/consolidation/tail_decisions.json plus the live
# high-count atomic facets. These are EXAMPLES per axis, not a closed set: the
# model reuses these and the runtime-injected EXISTING CATEGORIES list first, and
# only mints a new single-facet tag for a genuinely uncovered theme. Curating
# this list (adding/renaming axis values) is the durable lever on tag quality.
#
# Qwen note: this block is stated positively (only the shape we want, with no
# named anti-example), per the negation-blindness finding.
FACET_VOCABULARY = """\
- Aesthetic / tone: Absurdist, Gothic, Cosmic, Weird, Noir, Epic, Mythic, Dark
- Genre / setting: Horror, Fantasy, Sci-Fi, Cyberpunk, Post-Apocalyptic, \
Feywild, Underwater, Arcane, Infernal, Elemental
- Content-type: Adventures, Adventure Modules, Campaign, Encounters, Spells, \
Feats, Maps, Playbooks, Magic Items, Tomes, Archetypes, Mechanics, Progression, \
System, RPG, Class Homebrew
- Subject: Monsters, Races, Constructs, Aberrations, Artifacts, Cults, Mythos, \
Lore, Setting, Combat, Class, Necromancy, Traps, Villains"""

JUDGE_PROMPT = (
    """\
You are a librarian organizing a Google Drive of tabletop RPG documents into a \
rich, interconnected taxonomy.

In this taxonomy every category is ONE facet: a single aesthetic, genre, \
content-type, or subject. A document usually has SEVERAL facets, so it gets \
several separate one-facet tags. For example, a whimsical adventure module about \
talking cats gets three tags: "Absurdist", "Adventures", "Feline" - one tag per \
facet.

Example facets, grouped by axis (reuse these and the categories in the EXISTING \
CATEGORIES list before creating anything new):
"""
    + FACET_VOCABULARY
    + """

You will be given the complete list of existing categories, then the file's \
most similar already-stored files (its neighbors) with their categories, and \
finally the file itself (name and content snippet).

Decide:

1. Which facets this file has. List every fitting facet as its own tag. PREFER \
REUSING existing categories whenever they fit so the taxonomy stays coherent. \
Give the file the richest set of one-facet tags that describe it.

2. Whether any genuinely new facet is needed. Only when no existing category \
names a facet this file has, create one new tag - name it as a single facet in \
one or two words, with a one-sentence description.

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
)


def build_judge_user_msg(
    name: str,
    mime_type: str,
    snippet: str,
    neighbors: list[dict],
    categories: list[dict],
) -> str:
    """Assemble the judge's user message from harness-gathered context.

    Section order matters for vLLM prefix caching: the stable content
    (category list) leads so consecutive calls share the longest possible
    prefix; the per-file content (snippet) goes last.
    """
    # No member counts here: they change on nearly every assignment, which
    # would invalidate the cached prefix on every call.
    lines = ["EXISTING CATEGORIES:"]
    if categories:
        for c in categories:
            desc = c.get("description") or ""
            entry = f"- {c['name']}"
            if desc:
                entry += f": {desc}"
            lines.append(entry)
    else:
        lines.append("(none yet - you are starting the taxonomy)")
    lines += ["", "NEIGHBORS (most similar already-stored files):"]
    if neighbors:
        for n in neighbors:
            cats = ", ".join(n.get("categories") or []) or "(none)"
            lines.append(
                f"- id={n['id']}  name={n.get('name', '')}  "
                f"distance={n.get('distance', '')}  categories: {cats}"
            )
    else:
        lines.append("(none stored yet)")
    lines += [
        "",
        f"FILE: {name}",
        f"MIME: {mime_type}",
        "",
        "CONTENT SNIPPET:",
        snippet,
    ]
    return "\n".join(lines)
