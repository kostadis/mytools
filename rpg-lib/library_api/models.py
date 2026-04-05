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
