"""Query and serialization helpers for search/show service operations."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .config import CliConfig
from .errors import ChunkNotFoundError, DocctlError, EmptyIndexSearchError, InternalDocctlError
from .models import ChunkMetadata, ChunkRecord, SearchHit
from .service_types import SearchRequest, ServiceDependencies, ShowRequest, Store
from .text_sanitize import sanitize_text

RERANK_DEFAULT_MIN_CANDIDATES = 20
RERANK_DEFAULT_MULTIPLIER = 4
RERANK_MAX_CANDIDATES = 100


def build_where_filter(
    *,
    doc_id: str | None,
    source: str | None,
    title: str | None,
) -> dict[str, Any] | None:
    """Build Chroma metadata filter for optional search fields.

    Args:
        doc_id: Optional document identifier filter.
        source: Optional source path filter.
        title: Optional title filter.

    Returns:
        `None` when no filters are provided, one condition mapping for single
        filters, or an `$and` compound filter for multiple conditions.
    """
    conditions: list[dict[str, Any]] = []
    if doc_id:
        conditions.append({"doc_id": doc_id})
    if source:
        conditions.append({"source": source})
    if title:
        conditions.append({"title": title})

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def chunk_record_to_dict(record: ChunkRecord) -> dict[str, Any]:
    """Serialize chunk record into command output payload.

    Args:
        record: Chunk record from storage.

    Returns:
        Deterministic dictionary containing id, sanitized text, and metadata.
    """
    metadata = record.metadata
    metadata_dict = dict(metadata) if isinstance(metadata, dict) else asdict(metadata)
    return {
        "id": record.id,
        "text": sanitize_text(record.text),
        "metadata": metadata_dict,
    }


def search_hits_from_result(
    *,
    result: dict[str, Any],
    min_score: float | None,
) -> list[dict[str, Any]]:
    """Convert raw Chroma query results into ranked search hit payloads.

    Args:
        result: Raw Chroma query result.
        min_score: Optional minimum score threshold in `[0.0, 1.0]`.

    Returns:
        Ranked list of serialized search hit dictionaries.
    """
    ids = (result.get("ids") or [[]])[0]
    texts = (result.get("documents") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]

    hits: list[dict[str, Any]] = []
    for index, chunk_id in enumerate(ids):
        distance = (
            float(distances[index])
            if index < len(distances) and distances[index] is not None
            else 0.0
        )
        score = 1.0 / (1.0 + distance)
        if min_score is not None and score < min_score:
            continue

        metadata_raw = metadatas[index] if index < len(metadatas) else {}
        metadata = ChunkMetadata(
            doc_id=str(metadata_raw.get("doc_id", "")),
            source=str(metadata_raw.get("source", "")),
            title=str(metadata_raw.get("title", "")),
            section=metadata_raw.get("section"),
        )
        hit = SearchHit(
            rank=len(hits) + 1,
            id=str(chunk_id),
            text=sanitize_text(str(texts[index] if index < len(texts) else "")),
            distance=distance,
            score=score,
            metadata=metadata,
        )
        hits.append(asdict(hit))

    return hits


def resolve_rerank_candidate_count(*, top_k: int, rerank_candidates: int | None) -> int:
    """Resolve vector candidate depth used before second-stage reranking.

    Args:
        top_k: Final number of hits requested by caller.
        rerank_candidates: Optional explicit candidate depth.

    Returns:
        Candidate count used for vector retrieval before reranking.

    Raises:
        DocctlError: If explicit candidate depth is smaller than `top_k`.
    """
    if rerank_candidates is None:
        return min(
            max(top_k * RERANK_DEFAULT_MULTIPLIER, RERANK_DEFAULT_MIN_CANDIDATES),
            RERANK_MAX_CANDIDATES,
        )
    if rerank_candidates < top_k:
        raise DocctlError(
            message="invalid rerank candidate count: rerank_candidates must be >= top_k",
            exit_code=50,
        )
    return min(rerank_candidates, RERANK_MAX_CANDIDATES)


def rerank_hits(  # noqa: PLR0913
    *,
    hits: list[dict[str, Any]],
    query: str,
    top_k: int,
    config: CliConfig,
    allow_model_download: bool,
    deps: ServiceDependencies,
) -> list[dict[str, Any]]:
    """Apply second-stage reranking to vector candidates.

    Args:
        hits: Candidate hits from vector retrieval.
        query: Query used for candidate retrieval.
        top_k: Final result count.
        config: Resolved CLI configuration.
        allow_model_download: Whether missing model artifacts may be downloaded.
        deps: Injected dependency seams.

    Returns:
        Reranked hit list trimmed to `top_k`.
    """
    if not hits:
        return []

    reranker_factory = deps.reranker_factory
    if reranker_factory is None:
        raise InternalDocctlError("reranker factory is not configured")

    reranker = reranker_factory(
        model_name=config.rerank_model,
        allow_download=allow_model_download,
        verbose=config.verbose,
    )
    scores = reranker.score(query=query, texts=[str(hit.get("text", "")) for hit in hits])
    if len(scores) != len(hits):
        raise InternalDocctlError("reranker returned an invalid score count")

    enriched_hits: list[dict[str, Any]] = []
    for index, (hit, rerank_score) in enumerate(zip(hits, scores, strict=True), start=1):
        enriched = dict(hit)
        enriched["vector_rank"] = index
        enriched["rerank_score"] = float(rerank_score)
        enriched_hits.append(enriched)

    ordered = sorted(
        enriched_hits,
        key=lambda item: (-float(item["rerank_score"]), int(item["vector_rank"])),
    )
    final_hits = ordered[:top_k]
    for rank, hit in enumerate(final_hits, start=1):
        hit["rank"] = rank
    return final_hits


def search_hits(  # noqa: PLR0913
    *,
    store: Store,
    query: str,
    top_k: int,
    where: dict[str, Any] | None,
    min_score: float | None,
    rerank: bool,
    rerank_candidates: int | None,
    config: CliConfig,
    allow_model_download: bool,
    deps: ServiceDependencies,
) -> list[dict[str, Any]]:
    """Search vector index and optionally apply second-stage reranking.

    Args:
        store: Collection-scoped storage adapter.
        query: Natural-language query text.
        top_k: Final number of hits to return.
        where: Optional metadata filter.
        min_score: Optional minimum vector similarity score threshold.
        rerank: Whether second-stage reranking should run.
        rerank_candidates: Optional candidate depth for rerank stage.
        config: Resolved CLI configuration.
        allow_model_download: Whether missing model artifacts may be downloaded.
        deps: Injected dependency seams.

    Returns:
        Ranked search hits.
    """
    candidate_top_k = (
        resolve_rerank_candidate_count(top_k=top_k, rerank_candidates=rerank_candidates)
        if rerank
        else top_k
    )
    result = store.query(query=query, top_k=candidate_top_k, where=where)
    hits = search_hits_from_result(result=result, min_score=min_score)
    if not rerank:
        return hits[:top_k]
    return rerank_hits(
        hits=hits,
        query=query,
        top_k=top_k,
        config=config,
        allow_model_download=allow_model_download,
        deps=deps,
    )


def search_chunks(*, request: SearchRequest, deps: ServiceDependencies) -> dict[str, object]:
    """Search indexed chunks with optional metadata filters.

    Args:
        request: Search command request payload.
        deps: Injected factory dependencies.

    Returns:
        Search payload containing ranked hits and query metadata.

    Raises:
        EmptyIndexSearchError: If the target collection has zero chunks.
    """
    embedding_fn = deps.embedding_factory(
        model_name=request.config.embedding_model,
        allow_download=request.allow_model_download,
        verbose=request.config.verbose,
    )
    store = deps.store_factory(
        index_path=request.config.index_path,
        collection_name=request.config.collection,
        embedding_function=embedding_fn,
        create_collection=False,
        embedding_model=request.config.embedding_model,
    )

    if store.count() == 0:
        raise EmptyIndexSearchError("search cannot run on an empty index")

    where = build_where_filter(
        doc_id=request.doc_id,
        source=request.source,
        title=request.title,
    )
    hits = search_hits(
        store=store,
        query=request.query,
        top_k=request.top_k,
        where=where,
        min_score=request.min_score,
        rerank=request.rerank,
        rerank_candidates=request.rerank_candidates,
        config=request.config,
        allow_model_download=request.allow_model_download,
        deps=deps,
    )

    return {
        "collection": request.config.collection,
        "hits": hits,
        "index_path": str(request.config.index_path),
        "query": request.query,
        "top_k": request.top_k,
    }


def show_chunk(*, request: ShowRequest, deps: ServiceDependencies) -> dict[str, object]:
    """Return one indexed chunk by id.

    Args:
        request: Show command request payload.
        deps: Injected factory dependencies.

    Returns:
        Serialized chunk record payload.
    """
    _ = request.allow_model_download
    store = deps.store_factory(
        index_path=request.config.index_path,
        collection_name=request.config.collection,
        embedding_function=None,
        create_collection=False,
        embedding_model=request.config.embedding_model,
    )

    record = store.get_chunk(chunk_id=request.chunk_id)
    if not record:
        raise ChunkNotFoundError(f"chunk not found: {request.chunk_id}")

    return chunk_record_to_dict(record)
