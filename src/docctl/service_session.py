"""NDJSON session runtime and request dispatch helpers."""

from __future__ import annotations

import io
import json
from collections.abc import Callable, Iterable
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from dataclasses import asdict, dataclass
from typing import Any

from chromadb.api.types import Documents, EmbeddingFunction

from .coerce import (
    parse_optional_bool,
    parse_optional_float,
    parse_optional_int,
    parse_optional_str,
)
from .errors import DocctlError, EmptyIndexSearchError, InternalDocctlError
from .service_doctor import run_doctor
from .service_manifest import catalog_documents, load_manifest, manifest_documents
from .service_query import build_where_filter, chunk_record_to_dict, search_hits
from .service_types import DoctorRequest, Reranker, ServiceDependencies, SessionStreamRequest, Store


@dataclass(slots=True, frozen=True)
class _SessionSearchRequest:
    """Validated search request payload used by session runtime."""

    query: str
    top_k: int
    doc_id: str | None
    source: str | None
    title: str | None
    min_score: float | None
    rerank: bool = False
    rerank_candidates: int | None = None


@contextmanager
def suppress_external_output(*, enabled: bool):
    """Suppress stdout/stderr produced by external libraries when requested.

    Args:
        enabled: Whether suppression should be active.
    """
    if not enabled:
        yield
        return
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        yield


class SessionRuntime:
    """Cache session dependencies and execute read-only session operations."""

    def __init__(
        self,
        *,
        request: SessionStreamRequest,
        deps: ServiceDependencies,
    ) -> None:
        """Initialize runtime with stable config and dependency seams.

        Args:
            request: Session request payload.
            deps: Injected dependency factories.
        """
        self._request = request
        self._deps = deps
        self._embedding_fn: EmbeddingFunction[Documents] | None = None
        self._search_store: Store | None = None
        self._readonly_store: Store | None = None
        self._reranker: Reranker | None = None

    def _get_embedding_fn(self) -> EmbeddingFunction[Documents]:
        """Return cached embedding function for session search requests."""
        if self._embedding_fn is None:
            self._embedding_fn = self._deps.embedding_factory(
                model_name=self._request.config.embedding_model,
                allow_download=self._request.allow_model_download,
                verbose=self._request.config.verbose,
            )
        return self._embedding_fn

    def _get_search_store(self) -> Store:
        """Return cached search-capable store for session queries."""
        if self._search_store is None:
            self._search_store = self._deps.store_factory(
                index_path=self._request.config.index_path,
                collection_name=self._request.config.collection,
                embedding_function=self._get_embedding_fn(),
                create_collection=False,
                embedding_model=self._request.config.embedding_model,
            )
        return self._search_store

    def _get_readonly_store(self) -> Store:
        """Return cached read-only store for show/stats/catalog operations."""
        if self._readonly_store is None:
            self._readonly_store = self._deps.store_factory(
                index_path=self._request.config.index_path,
                collection_name=self._request.config.collection,
                embedding_function=None,
                create_collection=False,
                embedding_model=self._request.config.embedding_model,
            )
        return self._readonly_store

    def _get_reranker(self) -> Reranker:
        """Return cached reranker for session search requests."""
        if self._reranker is None:
            reranker_factory = self._deps.reranker_factory
            if reranker_factory is None:
                raise InternalDocctlError("reranker factory is not configured")
            self._reranker = reranker_factory(
                model_name=self._request.config.rerank_model,
                allow_download=self._request.allow_model_download,
                verbose=self._request.config.verbose,
            )
        return self._reranker

    def search(self, *, request: _SessionSearchRequest) -> dict[str, object]:
        """Execute a session search operation.

        Args:
            request: Validated search request payload.

        Returns:
            Session search result payload.

        Raises:
            EmptyIndexSearchError: If the target collection is empty.
        """
        store = self._get_search_store()
        if store.count() == 0:
            raise EmptyIndexSearchError("search cannot run on an empty index")
        where = build_where_filter(
            doc_id=request.doc_id,
            source=request.source,
            title=request.title,
        )
        session_deps = self._deps
        if request.rerank:
            session_deps = ServiceDependencies(
                embedding_factory=self._deps.embedding_factory,
                store_factory=self._deps.store_factory,
                reranker_factory=lambda **_: self._get_reranker(),
            )
        hits = search_hits(
            store=store,
            query=request.query,
            top_k=request.top_k,
            where=where,
            min_score=request.min_score,
            rerank=request.rerank,
            rerank_candidates=request.rerank_candidates,
            config=self._request.config,
            allow_model_download=self._request.allow_model_download,
            deps=session_deps,
        )
        return {
            "collection": self._request.config.collection,
            "hits": hits,
            "index_path": str(self._request.config.index_path),
            "query": request.query,
            "top_k": request.top_k,
        }

    def show(self, *, chunk_id: str) -> dict[str, object]:
        """Execute a session show operation.

        Args:
            chunk_id: Chunk identifier.

        Returns:
            Serialized chunk payload.
        """
        record = self._get_readonly_store().get_chunk(chunk_id=chunk_id)
        return chunk_record_to_dict(record)

    def stats(self) -> dict[str, object]:
        """Execute a session stats operation.

        Returns:
            Stats payload for the active collection.
        """
        manifest = load_manifest(self._request.config.index_path)
        documents = manifest_documents(manifest)
        store = self._get_readonly_store()
        return {
            "collection": self._request.config.collection,
            "chunk_count": store.count(),
            "document_count": len(documents),
            "embedding_model": manifest.get(
                "embedding_model", self._request.config.embedding_model
            ),
            "index_path": str(self._request.config.index_path),
            "last_ingest_at": manifest.get("last_ingest_at"),
        }

    def catalog(self) -> dict[str, object]:
        """Execute a session catalog operation.

        Returns:
            Catalog payload containing summary and document rows.
        """
        manifest = load_manifest(self._request.config.index_path)
        documents = catalog_documents(manifest_documents(manifest))
        return {
            "collection": self._request.config.collection,
            "embedding_model": manifest.get(
                "embedding_model", self._request.config.embedding_model
            ),
            "index_path": str(self._request.config.index_path),
            "summary": {
                "document_count": len(documents),
                "chunk_count": self._get_readonly_store().count(),
                "units_total": sum(document["units"] for document in documents),
                "last_ingest_at": manifest.get("last_ingest_at"),
            },
            "documents": documents,
        }

    def doctor(self) -> dict[str, object]:
        """Execute a session doctor operation.

        Returns:
            Serialized doctor report payload.
        """
        report = run_doctor(
            request=DoctorRequest(
                config=self._request.config,
                allow_model_download=self._request.allow_model_download,
            ),
            deps=self._deps,
        )
        return asdict(report)


def session_error(*, request_id: Any, error: Exception) -> dict[str, Any]:
    """Serialize a session error response from raised exceptions.

    Args:
        request_id: Request identifier from input payload.
        error: Raised exception.

    Returns:
        NDJSON response payload with stable `exit_code` and message.
    """
    if isinstance(error, DocctlError):
        exit_code = error.exit_code
        message = str(error)
    else:
        fallback = InternalDocctlError("unexpected internal error")
        exit_code = fallback.exit_code
        message = str(error)
    return {
        "id": request_id,
        "ok": False,
        "error": {"message": message, "exit_code": exit_code},
    }


def _parse_payload(line: str) -> dict[str, Any]:
    """Parse one NDJSON request line into a dictionary payload.

    Args:
        line: Raw NDJSON line.

    Returns:
        Decoded request payload.

    Raises:
        DocctlError: If decoded payload is not a dictionary.
        json.JSONDecodeError: If line is invalid JSON.
    """
    payload = json.loads(line)
    if not isinstance(payload, dict):
        raise DocctlError(message="invalid session request payload", exit_code=50)
    return payload


def _parse_operation(payload: dict[str, Any]) -> str:
    """Extract and validate operation name from request payload.

    Args:
        payload: Decoded request payload.

    Returns:
        Requested operation name.

    Raises:
        DocctlError: If operation is absent or not a string.
    """
    op = payload.get("op")
    if not isinstance(op, str):
        raise DocctlError(message="invalid session request field 'op'", exit_code=50)
    return op


def _handle_search(runtime: SessionRuntime, payload: dict[str, Any]) -> dict[str, object]:
    """Handle `search` session operation payload."""
    query = payload.get("query")
    if not isinstance(query, str) or not query.strip():
        raise DocctlError(message="invalid session request field 'query'", exit_code=50)

    top_k_value = payload.get("top_k", 5)
    if not isinstance(top_k_value, int) or top_k_value < 1 or top_k_value > 100:
        raise DocctlError(message="invalid session request field 'top_k'", exit_code=50)

    rerank_value = parse_optional_bool(payload.get("rerank"), field_name="rerank")
    rerank_enabled = rerank_value if rerank_value is not None else False
    rerank_candidates_value = parse_optional_int(
        payload.get("rerank_candidates"),
        field_name="rerank_candidates",
        minimum=1,
        maximum=100,
    )
    if rerank_candidates_value is not None and rerank_candidates_value < top_k_value:
        raise DocctlError(message="invalid session request field 'rerank_candidates'", exit_code=50)

    search_request = _SessionSearchRequest(
        query=query,
        top_k=top_k_value,
        doc_id=parse_optional_str(payload.get("doc_id"), field_name="doc_id"),
        source=parse_optional_str(payload.get("source"), field_name="source"),
        title=parse_optional_str(payload.get("title"), field_name="title"),
        min_score=parse_optional_float(
            payload.get("min_score"),
            field_name="min_score",
            minimum=0.0,
            maximum=1.0,
        ),
        rerank=rerank_enabled,
        rerank_candidates=rerank_candidates_value,
    )
    return runtime.search(request=search_request)


def _handle_show(runtime: SessionRuntime, payload: dict[str, Any]) -> dict[str, object]:
    """Handle `show` session operation payload."""
    chunk_id = payload.get("chunk_id")
    if not isinstance(chunk_id, str) or not chunk_id:
        raise DocctlError(message="invalid session request field 'chunk_id'", exit_code=50)
    return runtime.show(chunk_id=chunk_id)


def _handle_stats(runtime: SessionRuntime, payload: dict[str, Any]) -> dict[str, object]:
    """Handle `stats` session operation payload."""
    _ = payload
    return runtime.stats()


def _handle_catalog(runtime: SessionRuntime, payload: dict[str, Any]) -> dict[str, object]:
    """Handle `catalog` session operation payload."""
    _ = payload
    return runtime.catalog()


def _handle_doctor(runtime: SessionRuntime, payload: dict[str, Any]) -> dict[str, object]:
    """Handle `doctor` session operation payload."""
    _ = payload
    return runtime.doctor()


OperationHandler = Callable[[SessionRuntime, dict[str, Any]], dict[str, object]]
_OPERATION_HANDLERS: dict[str, OperationHandler] = {
    "search": _handle_search,
    "show": _handle_show,
    "stats": _handle_stats,
    "catalog": _handle_catalog,
    "doctor": _handle_doctor,
}


def run_session_requests(
    *,
    request: SessionStreamRequest,
    deps: ServiceDependencies,
) -> Iterable[dict[str, Any]]:
    """Process NDJSON session requests and yield response payloads.

    Args:
        request: Session stream request payload.
        deps: Injected dependency factories.

    Yields:
        Response dictionaries containing success results or structured errors.
    """
    runtime = SessionRuntime(request=request, deps=deps)
    yield from run_session_requests_with_runtime(
        runtime=runtime,
        request_lines=request.request_lines,
        verbose=request.config.verbose,
    )


def run_session_requests_with_runtime(
    *,
    runtime: SessionRuntime,
    request_lines: Iterable[str],
    verbose: bool,
) -> Iterable[dict[str, Any]]:
    """Process NDJSON request lines using an existing session runtime.

    Args:
        runtime: Reusable session runtime containing cached dependencies.
        request_lines: Incoming NDJSON request lines.
        verbose: Whether verbose mode is enabled.

    Yields:
        Response dictionaries containing success results or structured errors.
    """
    for raw_line in request_lines:
        response = run_session_request_line(runtime=runtime, raw_line=raw_line, verbose=verbose)
        if response is not None:
            yield response


def run_session_request_line(
    *,
    runtime: SessionRuntime,
    raw_line: str,
    verbose: bool,
) -> dict[str, Any] | None:
    """Process one NDJSON request line with a reusable runtime.

    Args:
        runtime: Reusable session runtime containing cached dependencies.
        raw_line: Raw NDJSON request line.
        verbose: Whether verbose mode is enabled.

    Returns:
        One response payload for non-empty lines, otherwise `None`.
    """
    line = raw_line.strip()
    if not line:
        return None

    request_id: Any = None
    try:
        payload = _parse_payload(line)
        request_id = payload.get("id")
        op = _parse_operation(payload)
        handler = _OPERATION_HANDLERS.get(op)
        if handler is None:
            raise DocctlError(message=f"unsupported session operation: {op}", exit_code=50)

        with suppress_external_output(enabled=not verbose):
            result = handler(runtime, payload)

        return {
            "id": request_id,
            "ok": True,
            "result": result,
        }
    except Exception as error:  # noqa: BLE001
        return session_error(request_id=request_id, error=error)
