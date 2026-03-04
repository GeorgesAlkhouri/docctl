"""Chroma persistence wrapper used by docctl services."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import chromadb
from chromadb.api.types import Documents, Embeddable, EmbeddingFunction, Metadata, Where

from .coerce import to_int, to_optional_str
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
        """Return the number of chunks currently stored in the collection."""
        return int(self.collection.count())

    def upsert_chunks(self, records: list[ChunkRecord]) -> None:
        """Insert or update chunk records in the backing Chroma collection.

        Args:
            records: Chunk records to persist.
        """
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
        """Delete all chunks belonging to one document id.

        Args:
            doc_id: Document identifier to delete.
        """
        self.collection.delete(where={"doc_id": doc_id})

    def query(
        self, *, query: str, top_k: int, where: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Run a semantic query and return raw Chroma response payload.

        Args:
            query: Natural-language query text.
            top_k: Maximum number of hits to return.
            where: Optional metadata filter expression.

        Returns:
            Raw query result including ids, documents, metadata, and distances.
        """
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
        """Fetch one chunk record by id.

        Args:
            chunk_id: Chunk identifier to retrieve.

        Returns:
            Resolved chunk record including text and metadata.

        Raises:
            ChunkNotFoundError: If the chunk id does not exist in the collection.
        """
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
                page=to_int(metadata.get("page"), default=0),
                section=to_optional_str(metadata.get("section")),
            ),
        )

    def metadata(self) -> dict[str, Any]:
        """Return collection metadata as a plain dictionary."""
        return dict(self.collection.metadata or {})
