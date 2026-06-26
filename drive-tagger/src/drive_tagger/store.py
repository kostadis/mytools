"""turbovecdb-backed store: the source of truth for documents and the category
taxonomy.

Two collections live under ``data/db``:

* ``documents``  - one row per Drive file (key = Drive file id). The document
  body is the extracted text; metadata holds name/mime/md5/links and the list of
  assigned category names.
* ``categories`` - one row per category (key = category name). The document body
  is the category description, so categories are themselves retrievable by
  semantic similarity.

Both collections share the same local embedder, so a document's vector can be
used to query either collection.
"""

from __future__ import annotations

import time
from typing import Optional

import turbovecdb

from .config import CONFIG
from .embed import embed


class Store:
    def __init__(self) -> None:
        CONFIG.ensure_dirs()
        self._db = turbovecdb.connect(str(CONFIG.db_dir))
        self.documents = self._db.collection(
            "documents", dim=CONFIG.embed_dim, embedder=embed, create=True
        )
        self.categories = self._db.collection(
            "categories", dim=CONFIG.embed_dim, embedder=embed, create=True
        )

    # -- documents ------------------------------------------------------------

    def has_unchanged(self, file_id: str, md5: Optional[str], modified_time: Optional[str]) -> bool:
        """True if the file is already stored with the same md5/modified_time."""
        res = self.documents.get(ids=[file_id], include=["metadatas"])
        if not res.ids:
            return False
        meta = res.metadatas[0]
        if md5 and meta.get("md5"):
            return meta["md5"] == md5
        if modified_time and meta.get("modified_time"):
            return meta["modified_time"] == modified_time
        # Stored but no comparable fingerprint -> treat as unchanged.
        return True

    def add_document(self, record: dict, text: str) -> None:
        """Embed and upsert a document, preserving any existing categories."""
        existing = self.get_document(record["id"])
        categories = existing.get("categories", []) if existing else []
        meta = {
            "name": record.get("name", ""),
            "mime_type": record.get("mime_type", ""),
            "modified_time": record.get("modified_time", ""),
            "md5": record.get("md5_checksum", "") or "",
            "web_view_link": record.get("web_view_link", "") or "",
            "categories": categories,
            "processed": existing.get("processed", False) if existing else False,
        }
        self.documents.upsert(ids=[record["id"]], documents=[text], metadatas=[meta])

    def get_document(self, file_id: str, *, include_vector: bool = False) -> Optional[dict]:
        include = ["documents", "metadatas"]
        if include_vector:
            include.append("vectors")
        res = self.documents.get(ids=[file_id], include=include)
        if not res.ids:
            return None
        out = dict(res.metadatas[0])
        out["id"] = res.ids[0]
        out["document"] = res.documents[0] if res.documents else ""
        if include_vector and res.vectors:
            out["vector"] = res.vectors[0]
        return out

    def _reupsert_metadata(self, file_id: str, meta: dict) -> None:
        """Update a document's metadata without re-embedding (reuses its vector)."""
        res = self.documents.get(ids=[file_id], include=["documents", "vectors"])
        if not res.ids:
            return
        self.documents.upsert(
            ids=[file_id],
            documents=[res.documents[0] if res.documents else ""],
            metadatas=[meta],
            vectors=[res.vectors[0]] if res.vectors else None,
        )

    def mark_processed(self, file_id: str) -> None:
        doc = self.get_document(file_id)
        if not doc:
            return
        meta = {k: v for k, v in doc.items() if k not in ("id", "document", "vector")}
        meta["processed"] = True
        self._reupsert_metadata(file_id, meta)

    def find_similar(self, file_id: str, k: int) -> list[dict]:
        """Return up to ``k`` documents most similar to ``file_id`` (excluding it)."""
        doc = self.get_document(file_id, include_vector=True)
        if not doc or "vector" not in doc:
            return []
        res = self.documents.query(
            vector=doc["vector"], k=k + 1, include=["documents", "metadatas", "distances"]
        )
        out = []
        for i, hit_id in enumerate(res.ids):
            if hit_id == file_id:
                continue
            meta = res.metadatas[i]
            out.append(
                {
                    "id": hit_id,
                    "name": meta.get("name", ""),
                    "distance": round(float(res.distances[i]), 4),
                    "categories": meta.get("categories", []),
                }
            )
            if len(out) >= k:
                break
        return out

    def count_documents(self) -> int:
        return self.documents.count()

    def all_documents(self) -> list[dict]:
        res = self.documents.get(include=["metadatas"])
        out = []
        for i, doc_id in enumerate(res.ids):
            meta = dict(res.metadatas[i])
            meta["id"] = doc_id
            out.append(meta)
        return out

    # -- categories -----------------------------------------------------------

    def create_category(self, name: str, description: str) -> dict:
        """Create or update a category (description is embedded for retrieval)."""
        name = name.strip()
        if not name:
            raise ValueError("category name must be non-empty")
        existing = self.categories.get(ids=[name], include=["metadatas"])
        member_count = existing.metadatas[0].get("member_count", 0) if existing.ids else 0
        meta = {
            "description": description,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "member_count": member_count,
        }
        self.categories.upsert(ids=[name], documents=[description or name], metadatas=[meta])
        return {"name": name, **meta}

    def category_exists(self, name: str) -> bool:
        return bool(self.categories.get(ids=[name.strip()], include=["metadatas"]).ids)

    def list_categories(self) -> list[dict]:
        res = self.categories.get(include=["documents", "metadatas"])
        out = []
        for i, name in enumerate(res.ids):
            meta = res.metadatas[i]
            out.append(
                {
                    "name": name,
                    "description": meta.get("description", res.documents[i] if res.documents else ""),
                    "member_count": meta.get("member_count", 0),
                }
            )
        out.sort(key=lambda c: c["name"].lower())
        return out

    def search_categories(self, file_id: str, k: int) -> list[dict]:
        """Return the categories most relevant to a document's content."""
        if self.categories.count() == 0:
            return []
        doc = self.get_document(file_id, include_vector=True)
        if not doc or "vector" not in doc:
            return []
        res = self.categories.query(
            vector=doc["vector"], k=k, include=["documents", "metadatas", "distances"]
        )
        out = []
        for i, name in enumerate(res.ids):
            meta = res.metadatas[i]
            out.append(
                {
                    "name": name,
                    "description": meta.get("description", ""),
                    "distance": round(float(res.distances[i]), 4),
                }
            )
        return out

    def _bump_category_count(self, name: str, delta: int) -> None:
        res = self.categories.get(ids=[name], include=["documents", "metadatas"])
        if not res.ids:
            return
        meta = dict(res.metadatas[0])
        meta["member_count"] = max(0, meta.get("member_count", 0) + delta)
        self.categories.upsert(
            ids=[name],
            documents=[res.documents[0] if res.documents else name],
            metadatas=[meta],
        )

    def assign_categories(self, file_id: str, names: list[str]) -> list[str]:
        """Attach categories to a document (union with existing). Returns the
        full category list. Unknown categories are auto-created as empty."""
        doc = self.get_document(file_id)
        if not doc:
            raise ValueError(f"unknown document id {file_id!r}; call next_file/embed first")
        current = set(doc.get("categories", []))
        clean = [n.strip() for n in names if n and n.strip()]
        newly_added = [n for n in clean if n not in current]

        for name in newly_added:
            if not self.category_exists(name):
                self.create_category(name, "")
            self._bump_category_count(name, +1)

        merged = sorted(current.union(clean))
        meta = {k: v for k, v in doc.items() if k not in ("id", "document", "vector")}
        meta["categories"] = merged
        self._reupsert_metadata(file_id, meta)
        return merged

    # -- lifecycle ------------------------------------------------------------

    def close(self) -> None:
        self._db.close()
