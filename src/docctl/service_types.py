"""Typed internal contracts for service orchestration modules."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from chromadb.api.types import Documents, EmbeddingFunction

from .config import CliConfig
from .models import ChunkRecord


class EmbeddingFactory(Protocol):
    """Create an embedding function from CLI configuration values."""

    def __call__(  # noqa: PLR0913
        self,
        *,
        model_name: str,
        allow_download: bool,
        verbose: bool = False,
    ) -> EmbeddingFunction[Documents]:
        """Build and return an embedding function instance."""


class Reranker(Protocol):
    """Score query/text candidate pairs for second-stage ranking."""

    def score(self, *, query: str, texts: list[str]) -> list[float]:
        """Return one reranker score per candidate text."""


class RerankerFactory(Protocol):
    """Create a reranker from CLI configuration values."""

    def __call__(
        self,
        *,
        model_name: str,
        allow_download: bool,
        verbose: bool = False,
    ) -> Reranker:
        """Build and return a reranker instance."""


class Store(Protocol):
    """Subset of store operations required by service modules."""

    def count(self) -> int:
        """Return chunk count for the active collection."""

    def query(
        self,
        *,
        query: str,
        top_k: int,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute semantic query with optional metadata filter."""

    def get_chunk(self, *, chunk_id: str) -> ChunkRecord:
        """Return one chunk record by identifier."""

    def upsert_chunks(self, records: list[ChunkRecord]) -> None:
        """Persist chunk records."""

    def delete_by_doc_id(self, doc_id: str) -> None:
        """Delete all chunks for one document id."""


class StoreFactory(Protocol):
    """Construct a collection-scoped store instance."""

    def __call__(
        self,
        *,
        index_path: Path,
        collection_name: str,
        embedding_function: EmbeddingFunction[Documents] | None,
        create_collection: bool,
        embedding_model: str,
    ) -> Store:
        """Build and return a store adapter instance."""


@dataclass(slots=True, frozen=True)
class ServiceDependencies:
    """Inject seams used by service orchestration flows."""

    embedding_factory: EmbeddingFactory
    store_factory: StoreFactory
    reranker_factory: RerankerFactory | None = None


@dataclass(slots=True, frozen=True)
class IngestRequest:
    """Inputs required for one ingest command execution."""

    config: CliConfig
    input_path: Path
    recursive: bool
    glob_pattern: str
    force: bool
    approve_write: bool
    allow_model_download: bool


@dataclass(slots=True, frozen=True)
class SearchRequest:
    """Inputs required for one search command execution."""

    config: CliConfig
    query: str
    top_k: int
    doc_id: str | None
    source: str | None
    title: str | None
    min_score: float | None
    allow_model_download: bool
    rerank: bool = False
    rerank_candidates: int | None = None


@dataclass(slots=True, frozen=True)
class ShowRequest:
    """Inputs required for one show command execution."""

    config: CliConfig
    chunk_id: str
    allow_model_download: bool


@dataclass(slots=True, frozen=True)
class DoctorRequest:
    """Inputs required for one doctor command execution."""

    config: CliConfig
    allow_model_download: bool


@dataclass(slots=True, frozen=True)
class SessionStreamRequest:
    """Inputs required for one NDJSON session run."""

    config: CliConfig
    request_lines: Iterable[str]
    allow_model_download: bool
