"""Chroma persistence wrapper used by docctl services."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import chromadb
from chromadb.api.types import Documents, EmbeddingFunction

from .errors import ChunkNotFoundError, IndexNotInitializedError
from .models import ChunkMetadata, ChunkRecord


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
            raise IndexNotInitializedError(f"missing index directory: {self.chroma_path}")

        self.client = chromadb.PersistentClient(path=str(self.chroma_path))

        if create_collection:
            self.collection = self.client.get_or_create_collection(
                name=collection_name,
                embedding_function=embedding_function,
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
            embedding_function=embedding_function,
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

    def query(self, *, query: str, top_k: int, where: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.collection.query(
            query_texts=[query],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

    def get_chunk(self, *, chunk_id: str) -> ChunkRecord:
        result = self.collection.get(ids=[chunk_id], include=["documents", "metadatas"])
        ids = result.get("ids") or []
        if not ids:
            raise ChunkNotFoundError(f"chunk not found: {chunk_id}")

        documents = result.get("documents") or []
        metadatas = result.get("metadatas") or []
        metadata = metadatas[0] if metadatas else {}

        return ChunkRecord(
            id=str(ids[0]),
            text=str(documents[0] if documents else ""),
            metadata=ChunkMetadata(
                doc_id=str(metadata.get("doc_id", "")),
                source=str(metadata.get("source", "")),
                title=str(metadata.get("title", "")),
                page=int(metadata.get("page", 0)),
                section=metadata.get("section"),
            ),
        )

    def metadata(self) -> dict[str, Any]:
        return dict(self.collection.metadata or {})
