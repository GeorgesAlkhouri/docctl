"""Ingest orchestration for PDF discovery and index mutation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .chunking import chunk_document_pages
from .errors import (
    DocctlError,
    EmptyExtractedTextError,
    InputPathNotFoundError,
    WriteApprovalRequiredError,
)
from .ids import build_doc_id, file_sha256
from .pdf_extract import extract_pdf_pages
from .service_manifest import load_manifest, write_manifest
from .service_types import IngestRequest, ServiceDependencies, Store


@dataclass(slots=True)
class _IngestState:
    """Mutable ingest counters and error state for one command run."""

    indexed_files: int = 0
    skipped_files: int = 0
    indexed_pages: int = 0
    indexed_chunks: int = 0
    errors: list[dict[str, str]] = field(default_factory=list)
    first_docctl_error: DocctlError | None = None


@dataclass(slots=True, frozen=True)
class _DocumentContext:
    """Derived per-file ingest context used in the processing loop."""

    source: str
    doc_id: str
    title: str
    content_hash: str


def utc_now_iso() -> str:
    """Return current UTC timestamp with second precision as ISO-8601 string."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def relative_source(path: Path) -> str:
    """Return source path relative to current working directory when possible.

    Args:
        path: Input PDF path.

    Returns:
        Relative path when under cwd, otherwise absolute path.
    """
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path.resolve())


def discover_pdf_files(*, input_path: Path, recursive: bool, glob_pattern: str) -> list[Path]:
    """Discover PDF files from an input path.

    Args:
        input_path: PDF file or directory path.
        recursive: Whether directory traversal is recursive.
        glob_pattern: Glob pattern used for discovery.

    Returns:
        Sorted list of resolved PDF paths.

    Raises:
        InputPathNotFoundError: If path is invalid or no PDFs match.
    """
    if not input_path.exists():
        raise InputPathNotFoundError(f"input path does not exist: {input_path}")

    if input_path.is_file():
        if input_path.suffix.lower() != ".pdf":
            raise InputPathNotFoundError(f"input file is not a PDF: {input_path}")
        return [input_path.resolve()]

    iterator = input_path.rglob(glob_pattern) if recursive else input_path.glob(glob_pattern)
    files = sorted(
        path.resolve() for path in iterator if path.is_file() and path.suffix.lower() == ".pdf"
    )
    if not files:
        raise InputPathNotFoundError(f"no PDF files matched under: {input_path}")
    return files


def require_write_approval(*, require_approval: bool, approve_write: bool) -> None:
    """Validate explicit write approval requirement for mutating commands.

    Args:
        require_approval: Whether configuration requires explicit write approval.
        approve_write: CLI flag value for write approval.

    Raises:
        WriteApprovalRequiredError: If write approval is required but missing.
    """
    if require_approval and not approve_write:
        raise WriteApprovalRequiredError(
            "write approval is required. Re-run ingest with --approve-write or unset DOCCTL_REQUIRE_WRITE_APPROVAL."
        )


def _create_store(*, request: IngestRequest, deps: ServiceDependencies) -> Store:
    """Build ingest store with embedding function initialized."""
    embedding_fn = deps.embedding_factory(
        model_name=request.config.embedding_model,
        allow_download=request.allow_model_download,
        verbose=request.config.verbose,
    )
    return deps.store_factory(
        index_path=request.config.index_path,
        collection_name=request.config.collection,
        embedding_function=embedding_fn,
        create_collection=True,
        embedding_model=request.config.embedding_model,
    )


def _document_context(file_path: Path) -> _DocumentContext:
    """Build deterministic context values used for one file ingest."""
    source = relative_source(file_path)
    return _DocumentContext(
        source=source,
        doc_id=build_doc_id(source),
        title=file_path.stem,
        content_hash=file_sha256(file_path),
    )


def _should_skip_existing(
    *,
    context: _DocumentContext,
    force: bool,
    manifest_docs: dict[str, Any],
) -> bool:
    """Return whether existing manifest metadata allows skipping ingest."""
    existing = manifest_docs.get(context.doc_id)
    return bool(existing and not force and existing.get("content_hash") == context.content_hash)


def _ingest_document(
    *, file_path: Path, context: _DocumentContext, store: Store
) -> tuple[int, int]:
    """Extract, chunk, and index one PDF.

    Args:
        file_path: PDF path to ingest.
        context: Per-file derived metadata context.
        store: Collection store adapter.

    Returns:
        Tuple of `(pages_indexed, chunks_indexed)`.

    Raises:
        EmptyExtractedTextError: If no chunks were produced.
        Exception: Any extraction/chunking/storage failures.
    """
    pages = extract_pdf_pages(file_path)
    chunks = chunk_document_pages(
        doc_id=context.doc_id,
        source=context.source,
        title=context.title,
        pages=pages,
    )
    if not chunks:
        raise EmptyExtractedTextError(f"no chunks produced for file: {file_path}")

    store.delete_by_doc_id(context.doc_id)
    store.upsert_chunks(chunks)
    return len(pages), len(chunks)


def _record_success(
    *,
    context: _DocumentContext,
    pages_indexed: int,
    chunks_indexed: int,
    manifest_docs: dict[str, Any],
    state: _IngestState,
) -> None:
    """Apply successful file ingest effects to counters and manifest."""
    state.indexed_files += 1
    state.indexed_pages += pages_indexed
    state.indexed_chunks += chunks_indexed
    manifest_docs[context.doc_id] = {
        "source": context.source,
        "title": context.title,
        "content_hash": context.content_hash,
        "pages": pages_indexed,
        "chunks": chunks_indexed,
        "last_ingest_at": utc_now_iso(),
    }


def _record_error(*, context: _DocumentContext, error: Exception, state: _IngestState) -> None:
    """Track first DocctlError and append serialized per-file error entry."""
    if state.first_docctl_error is None and isinstance(error, DocctlError):
        state.first_docctl_error = error
    state.errors.append({"file": context.source, "error": str(error)})


def _process_files(
    *,
    files: list[Path],
    request: IngestRequest,
    manifest_docs: dict[str, Any],
    store: Store,
) -> _IngestState:
    """Process all discovered files and return aggregate ingest state."""
    state = _IngestState()
    for file_path in files:
        context = _document_context(file_path)
        if _should_skip_existing(context=context, force=request.force, manifest_docs=manifest_docs):
            state.skipped_files += 1
            continue

        try:
            pages_indexed, chunks_indexed = _ingest_document(
                file_path=file_path,
                context=context,
                store=store,
            )
            _record_success(
                context=context,
                pages_indexed=pages_indexed,
                chunks_indexed=chunks_indexed,
                manifest_docs=manifest_docs,
                state=state,
            )
        except Exception as error:  # noqa: BLE001
            _record_error(context=context, error=error, state=state)
    return state


def _finalize_manifest(
    *, request: IngestRequest, manifest: dict[str, Any], state: _IngestState
) -> None:
    """Persist manifest updates only when files were indexed."""
    if state.indexed_files <= 0:
        return
    manifest["last_ingest_at"] = utc_now_iso()
    manifest["embedding_model"] = request.config.embedding_model
    write_manifest(request.config.index_path, manifest)


def _raise_if_no_indexed_files(*, state: _IngestState) -> None:
    """Raise deterministic ingest error when no files were indexed or skipped."""
    if state.indexed_files > 0 or state.skipped_files > 0:
        return
    if state.first_docctl_error is not None:
        raise state.first_docctl_error
    if state.errors:
        first_error = state.errors[0]["error"]
        raise EmptyExtractedTextError(f"no files were indexed. first failure: {first_error}")
    raise EmptyExtractedTextError("no files were indexed")


def _summary_payload(
    *, request: IngestRequest, files_discovered: int, state: _IngestState
) -> dict[str, object]:
    """Build command response payload from aggregate ingest state."""
    return {
        "collection": request.config.collection,
        "embedding_model": request.config.embedding_model,
        "errors": state.errors,
        "files_discovered": files_discovered,
        "files_indexed": state.indexed_files,
        "files_skipped": state.skipped_files,
        "index_path": str(request.config.index_path),
        "pages_indexed": state.indexed_pages,
        "chunks_indexed": state.indexed_chunks,
    }


def ingest_path(*, request: IngestRequest, deps: ServiceDependencies) -> dict[str, object]:
    """Ingest one PDF path or directory into the local vector index.

    Args:
        request: Ingest request payload.
        deps: Injected dependency factories.

    Returns:
        Summary payload describing ingested, skipped, and failed documents.
    """
    require_write_approval(
        require_approval=request.config.require_write_approval,
        approve_write=request.approve_write,
    )
    files = discover_pdf_files(
        input_path=request.input_path,
        recursive=request.recursive,
        glob_pattern=request.glob_pattern,
    )
    store = _create_store(request=request, deps=deps)
    manifest = load_manifest(request.config.index_path)
    manifest_docs: dict[str, Any] = manifest.setdefault("documents", {})

    state = _process_files(
        files=files,
        request=request,
        manifest_docs=manifest_docs,
        store=store,
    )
    _finalize_manifest(request=request, manifest=manifest, state=state)
    _raise_if_no_indexed_files(state=state)
    return _summary_payload(request=request, files_discovered=len(files), state=state)
