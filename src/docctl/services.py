"""Facade service layer for docctl commands."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .config import CliConfig
from .embeddings import create_embedding_function
from .index_store import ChromaStore
from .models import DoctorReport
from .reranking import create_reranker
from .service_doctor import run_doctor as run_doctor_impl
from .service_ingest import ingest_path as ingest_path_impl
from .service_manifest import catalog_documents, load_manifest, manifest_documents
from .service_query import search_chunks as search_chunks_impl
from .service_query import show_chunk as show_chunk_impl
from .service_session import run_session_requests as run_session_requests_impl
from .service_types import (
    DoctorRequest,
    IngestRequest,
    SearchRequest,
    ServiceDependencies,
    SessionStreamRequest,
    ShowRequest,
)


def _dependencies() -> ServiceDependencies:
    """Resolve injectable runtime dependencies.

    Returns:
        Dependency bundle used by internal service submodules.
    """
    return ServiceDependencies(
        embedding_factory=create_embedding_function,
        store_factory=ChromaStore,
        reranker_factory=create_reranker,
    )


def ingest_path(  # noqa: PLR0913
    *,
    config: CliConfig,
    input_path: Path,
    recursive: bool,
    glob_pattern: str,
    force: bool,
    approve_write: bool,
    allow_model_download: bool,
) -> dict[str, object]:
    """Ingest one supported path or directory into the local vector index.

    Args:
        config: Resolved CLI configuration.
        input_path: Supported file or directory to ingest.
        recursive: Whether directory traversal is recursive.
        glob_pattern: Glob used for file discovery in directories.
        force: Whether existing documents should be reingested.
        approve_write: Explicit user approval for mutating writes.
        allow_model_download: Whether missing embedding models may be downloaded.

    Returns:
        Summary payload describing ingested, skipped, and failed documents.
    """
    request = IngestRequest(
        config=config,
        input_path=input_path,
        recursive=recursive,
        glob_pattern=glob_pattern,
        force=force,
        approve_write=approve_write,
        allow_model_download=allow_model_download,
    )
    return ingest_path_impl(request=request, deps=_dependencies())


def search_chunks(  # noqa: PLR0913
    *,
    config: CliConfig,
    query: str,
    top_k: int,
    doc_id: str | None,
    source: str | None,
    title: str | None,
    min_score: float | None,
    rerank: bool,
    rerank_candidates: int | None,
    allow_model_download: bool,
) -> dict[str, object]:
    """Search indexed chunks with optional metadata filters.

    Args:
        config: Resolved CLI configuration.
        query: Natural-language query text.
        top_k: Maximum number of hits to return.
        doc_id: Optional document id filter.
        source: Optional source path filter.
        title: Optional document title filter.
        min_score: Optional minimum similarity score in `[0.0, 1.0]`.
        rerank: Whether second-stage reranking is enabled.
        rerank_candidates: Candidate depth used before reranking.
        allow_model_download: Whether missing embedding models may be downloaded.

    Returns:
        Search payload containing ranked hits and query metadata.
    """
    request = SearchRequest(
        config=config,
        query=query,
        top_k=top_k,
        doc_id=doc_id,
        source=source,
        title=title,
        min_score=min_score,
        allow_model_download=allow_model_download,
        rerank=rerank,
        rerank_candidates=rerank_candidates,
    )
    return search_chunks_impl(request=request, deps=_dependencies())


def show_chunk(
    *, config: CliConfig, chunk_id: str, allow_model_download: bool
) -> dict[str, object]:
    """Return one indexed chunk by id.

    Args:
        config: Resolved CLI configuration.
        chunk_id: Chunk identifier to retrieve.
        allow_model_download: Unused compatibility flag for command parity.

    Returns:
        Serialized chunk record payload.
    """
    request = ShowRequest(
        config=config,
        chunk_id=chunk_id,
        allow_model_download=allow_model_download,
    )
    return show_chunk_impl(request=request, deps=_dependencies())


def collect_stats(*, config: CliConfig) -> dict[str, object]:
    """Collect collection-level statistics and manifest details.

    Args:
        config: Resolved CLI configuration.

    Returns:
        Stats payload with counts, paths, and ingest metadata.
    """
    store = ChromaStore(
        index_path=config.index_path,
        collection_name=config.collection,
        embedding_function=None,
        create_collection=False,
        embedding_model=config.embedding_model,
    )
    manifest = load_manifest(config.index_path)
    documents = manifest_documents(manifest)
    return {
        "collection": config.collection,
        "chunk_count": store.count(),
        "document_count": len(documents),
        "embedding_model": manifest.get("embedding_model", config.embedding_model),
        "index_path": str(config.index_path),
        "last_ingest_at": manifest.get("last_ingest_at"),
    }


def collect_catalog(*, config: CliConfig) -> dict[str, object]:
    """Collect index summary plus per-document catalog entries.

    Args:
        config: Resolved CLI configuration.

    Returns:
        Catalog payload containing summary stats and per-document manifest rows.
    """
    store = ChromaStore(
        index_path=config.index_path,
        collection_name=config.collection,
        embedding_function=None,
        create_collection=False,
        embedding_model=config.embedding_model,
    )
    manifest = load_manifest(config.index_path)
    documents = catalog_documents(manifest_documents(manifest))
    return {
        "collection": config.collection,
        "embedding_model": manifest.get("embedding_model", config.embedding_model),
        "index_path": str(config.index_path),
        "summary": {
            "document_count": len(documents),
            "chunk_count": store.count(),
            "units_total": sum(document["units"] for document in documents),
            "last_ingest_at": manifest.get("last_ingest_at"),
        },
        "documents": documents,
    }


def run_session_requests(
    *,
    config: CliConfig,
    request_lines: Iterable[str],
    allow_model_download: bool,
) -> Iterable[dict[str, Any]]:
    """Process NDJSON session requests and yield response payloads.

    Args:
        config: Resolved CLI configuration.
        request_lines: Incoming NDJSON request lines.
        allow_model_download: Whether missing embedding models may be downloaded.

    Returns:
        Iterable of response dictionaries for each valid input line.
    """
    request = SessionStreamRequest(
        config=config,
        request_lines=request_lines,
        allow_model_download=allow_model_download,
    )
    return run_session_requests_impl(request=request, deps=_dependencies())


def run_doctor(*, config: CliConfig, allow_model_download: bool) -> DoctorReport:
    """Run repository-local health checks for index and embedding readiness.

    Args:
        config: Resolved CLI configuration.
        allow_model_download: Whether missing embedding models may be downloaded.

    Returns:
        Structured doctor report with checks, warnings, and errors.
    """
    request = DoctorRequest(config=config, allow_model_download=allow_model_download)
    return run_doctor_impl(request=request, deps=_dependencies())
