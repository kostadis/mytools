# Graph Feature

An interactive force-directed network that visualizes semantic similarity between books in the library. Each node is a book; each edge connects two books that share significant tags.

## Setup (one-time, after enrichment)

```bash
# 1. Ensure the book_relations table exists
python wiki_setup.py rpg_library.db

# 2. Build similarity scores (run after any bulk enrichment)
python relation_builder.py rpg_library.db
python relation_builder.py rpg_library.db --min-score 0.15 --top-k 10
```

`relation_builder.py` must re-run after adding or re-enriching books. The graph API reads from `book_relations`, which is a snapshot — it does not update automatically.

## How Relations Are Built (`relation_builder.py`)

1. Load all enriched books (excludes old versions, drafts, duplicates) with their tag lists.
2. Build an inverted index: `tag → [book_ids]`.
3. Skip tags that appear in more than 500 books (too common to be discriminating).
4. For each pair of books sharing at least one tag, compute Jaccard similarity:
   ```
   score = |tags_A ∩ tags_B| / |tags_A ∪ tags_B|
   ```
5. Keep the top-K relations per book (default 10) above `--min-score` (default 0.1).
6. Write both directions (A→B and B→A) to `book_relations(book_id_a, book_id_b, score, shared_tags_count)`.

**Why both directions?** Storing A→B and B→A avoids bidirectional queries at read time and makes lookups O(1).

**Why skip high-frequency tags?** Tags like `adventure` appear in thousands of books and would create a near-complete graph with no useful signal. The 500-book threshold keeps edges meaningful.

## API

```
GET /api/library/graph
  ?min_score=0.25    # float 0–1, filter edges below threshold (default 0.25)
  ?limit=300         # int 10–1000, max nodes to return (default 300)
  ?game_system=...   # optional, restrict nodes and edges to one system
```

**Response:**
```json
{
  "nodes": [{"id": 123, "label": "Curse of Strahd", "group": "D&D 5e"}, ...],
  "edges": [{"source": 123, "target": 456, "score": 0.67}, ...]
}
```

**Node selection algorithm:** The backend fetches `limit * 3` candidate edges above `min_score`, counts how many edges touch each book (degree), then selects the top `limit` books by degree. This prioritizes well-connected hubs over isolated books. Edges are then filtered to only those between selected nodes.

## Frontend (`frontend/src/views/GraphView.vue`)

A D3 force-directed simulation rendered on `<canvas>`. Controls:

| Control | Range | Default | Effect |
|---|---|---|---|
| Min similarity | 0.1–0.9 | 0.25 | Hides edges below threshold |
| Max nodes | 50–500 | 200 | Caps graph size |
| System filter | text | (all) | Restricts to one game system |

**Interactions:**
- **Hover** — tooltip shows book title and game system
- **Click node** — navigates to the book's detail page
- **Drag node** — pins node position (D3 alpha restart on release)
- **Scroll** — zoom (0.1–4×)
- **Drag canvas** — pan

Node color encodes game system (D&D 5e = blue, Pathfinder 1e = orange, OSR = green, etc.) with a legend in the corner. Edge thickness is proportional to similarity score.

## Data Flow

```
relation_builder.py
  → book_relations table (Jaccard scores, both directions)
      → GET /api/library/graph (db.get_graph())
          → GraphResponse {nodes, edges}
              → GraphView.vue (D3 force simulation)
```

## Data Models

```python
class GraphNode:
    id: int        # book_id
    label: str     # display_title or filename
    group: str     # game_system (for color coding)

class GraphEdge:
    source: int    # book_id_a
    target: int    # book_id_b
    score: float   # Jaccard similarity

class GraphResponse:
    nodes: list[GraphNode]
    edges: list[GraphEdge]
```

## Limitations

- **Level/CR range** is not encoded in tags and therefore not reflected in similarity.
- **Cross-system edges** are possible — two books about `horror` + `investigation` may connect even if they use different rule systems. Use the system filter to isolate one system.
- **Graph is a snapshot.** Re-run `relation_builder.py` after enriching new books.
- The frontend fetches the entire graph payload at load time; very large limits (500 nodes) can be slow on initial render.
