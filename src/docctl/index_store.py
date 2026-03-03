"""Chroma persistence wrapper used by docctl services."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import chromadb
from chromadb.api.types import Documents, Embeddable, EmbeddingFunction, Metadata, Where

from .errors import ChunkNotFoundError, IndexNotInitializedError
from .models import ChunkMetadata, ChunkRecord


def _as_int(value: object, *, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _as_optional_str(value: object) -> str | None:
    if isinstance(value, str):
        return value
    return None


class ChromaStore:
    """Small adapter around Chroma PersistentClient and one collection."""

    def __init__(
        self,
        *,
        index_path: Path,
        collection_name: str,
        embedding_function: EmbeddingFunction[Documents] | None,
        create_collection: bool,
        embedding_model: str,
    ) -> None:
        self.index_path = index_path
        self.collection_name = collection_name
        self.chroma_path = index_path / "chroma"

        if create_collection:
            self.chroma_path.mkdir(parents=True, exist_ok=True)
        elif not self.chroma_path.exists():
            raise IndexNotInitializedError(
                "index is not initialized at "
                f"{self.chroma_path}. "
                "Run `docctl ingest <path>` first, or set `--index-path` to an existing index."
            )

        self.client = chromadb.PersistentClient(path=str(self.chroma_path))
        chroma_embedding_fn = cast(EmbeddingFunction[Embeddable] | None, embedding_function)

        if create_collection:
            self.collection = self.client.get_or_create_collection(
                name=collection_name,
                embedding_function=chroma_embedding_fn,
                metadata={"embedding_model": embedding_model},
            )
            return

        existing_names = {
            collection.name if hasattr(collection, "name") else str(collection)
            for collection in self.client.list_collections()
        }
        if collection_name not in existing_names:
            raise IndexNotInitializedError(f"collection not found: {collection_name}")

        self.collection = self.client.get_collection(
            name=collection_name,
            embedding_function=chroma_embedding_fn,
        )

    def count(self) -> int:
        return int(self.collection.count())

    def upsert_chunks(self, records: list[ChunkRecord]) -> None:
        if not records:
            return
        self.collection.upsert(
            ids=[record.id for record in records],
            documents=[record.text for record in records],
            metadatas=[
                {
                    "doc_id": record.metadata.doc_id,
                    "source": record.metadata.source,
                    "title": record.metadata.title,
                    "page": record.metadata.page,
                    "section": record.metadata.section,
                }
                for record in records
            ],
        )

    def delete_by_doc_id(self, doc_id: str) -> None:
        self.collection.delete(where={"doc_id": doc_id})

    def query(
        self, *, query: str, top_k: int, where: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.collection.query(
                query_texts=[query],
                n_results=top_k,
                where=cast(Where | None, where),
                include=["documents", "metadatas", "distances"],
            ),
        )

    def get_chunk(self, *, chunk_id: str) -> ChunkRecord:
        result = self.collection.get(ids=[chunk_id], include=["documents", "metadatas"])
        ids = cast(list[str], result.get("ids") or [])
        if not ids:
            raise ChunkNotFoundError(f"chunk not found: {chunk_id}")

        documents = cast(list[str], result.get("documents") or [])
        metadatas = cast(list[Mapping[str, object]], result.get("metadatas") or [])
        metadata: Mapping[str, object] = metadatas[0] if metadatas else cast(Metadata, {})

        return ChunkRecord(
            id=ids[0],
            text=documents[0] if documents else "",
            metadata=ChunkMetadata(
                doc_id=str(metadata.get("doc_id", "")),
                source=str(metadata.get("source", "")),
                title=str(metadata.get("title", "")),
                page=_as_int(metadata.get("page"), default=0),
                section=_as_optional_str(metadata.get("section")),
            ),
        )

    def metadata(self) -> dict[str, Any]:
        return dict(self.collection.metadata or {})
