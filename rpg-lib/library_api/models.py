"""Pydantic models for the RPG Library API."""

from pydantic import BaseModel


class BookSummary(BaseModel):
    id: int
    display_title: str | None
    filename: str
    publisher: str | None
    collection: str | None
    game_system: str | None
    product_type: str | None
    tags: list[str] | None
    series: str | None
    source: str | None
    page_count: int | None
    has_bookmarks: bool
    description: str | None
    min_level: int | None = None
    max_level: int | None = None
    variant_count: int = 1
    variant_ids: list[int] = []


class Bookmark(BaseModel):
    level: int
    title: str
    page_number: int | None


class BookDetail(BookSummary):
    filepath: str
    relative_path: str
    pdf_title: str | None
    pdf_author: str | None
    pdf_creator: str | None
    first_page_text: str | None
    is_old_version: bool
    version_generation: int | None
    product_id: str | None
    product_version: str | None
    date_indexed: str | None
    date_enriched: str | None
    bookmarks: list[Bookmark]


class SearchResponse(BaseModel):
    results: list[BookSummary]
    total: int
    page: int
    per_page: int
    total_pages: int


class FilterValue(BaseModel):
    value: str
    count: int


class FilterOptions(BaseModel):
    game_system: list[FilterValue]
    product_type: list[FilterValue]
    publisher: list[FilterValue]
    series: list[FilterValue]
    tags: list[FilterValue]
    source: list[FilterValue]


class FacetsResponse(BaseModel):
    """Aggregations of search results by series / publisher / game_system / tag.

    Counts reflect the same WHERE clause as ``/search`` — i.e. they answer
    "which series contain books that match my current query?" rather than
    "which series exist in the whole library?"."""
    total: int
    series: list[FilterValue]
    publisher: list[FilterValue]
    game_system: list[FilterValue]
    tag: list[FilterValue]


class StatsResponse(BaseModel):
    total_books: int
    enriched_books: int
    books_with_bookmarks: int
    by_source: list[FilterValue]
    by_product_type: list[FilterValue]


class BookText(BaseModel):
    id: int
    display_title: str | None
    filename: str
    first_page_text: str | None
    bookmark_titles: list[str]


# ── Wiki / NLQ models ─────────────────────────────────────────────────────────

class NlqRequest(BaseModel):
    query: str


class NlqResponse(BaseModel):
    query_parsed: dict
    results: list[BookSummary]
    total: int


class TopicStats(BaseModel):
    total: int
    enriched: int
    by_product_type: list[FilterValue]
    top_publishers: list[FilterValue]   # empty for publisher topics
    top_tags: list[FilterValue]         # empty for tag topics
    top_series: list[FilterValue]       # empty for series topics
    top_game_systems: list[FilterValue] # empty for game_system topics


class TopicResponse(BaseModel):
    topic_type: str
    topic_name: str
    stats: TopicStats
    books: list[BookSummary]


class GraphNode(BaseModel):
    id: int
    label: str
    group: str | None   # game_system for color coding


class GraphEdge(BaseModel):
    source: int
    target: int
    score: float


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
