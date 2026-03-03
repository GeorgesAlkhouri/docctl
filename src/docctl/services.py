"""Service layer for docctl commands."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .chunking import chunk_document_pages
from .config import CliConfig
from .embeddings import create_embedding_function
from .errors import (
    ChunkNotFoundError,
    DocctlError,
    EmptyExtractedTextError,
    EmptyIndexSearchError,
    InputPathNotFoundError,
    WriteApprovalRequiredError,
)
from .ids import build_doc_id, file_sha256
from .index_store import ChromaStore
from .models import ChunkMetadata, ChunkRecord, DoctorCheck, DoctorReport, SearchHit
from .pdf_extract import extract_pdf_pages

_MANIFEST_FILENAME = "manifest.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _relative_source(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path.resolve())


def _discover_pdf_files(*, input_path: Path, recursive: bool, glob_pattern: str) -> list[Path]:
    if not input_path.exists():
        raise InputPathNotFoundError(f"input path does not exist: {input_path}")

    if input_path.is_file():
        if input_path.suffix.lower() != ".pdf":
            raise InputPathNotFoundError(f"input file is not a PDF: {input_path}")
        return [input_path.resolve()]

    iterator = input_path.rglob(glob_pattern) if recursive else input_path.glob(glob_pattern)
    files = sorted(path.resolve() for path in iterator if path.is_file() and path.suffix.lower() == ".pdf")
    if not files:
        raise InputPathNotFoundError(f"no PDF files matched under: {input_path}")
    return files


def _manifest_path(index_path: Path) -> Path:
    return index_path / _MANIFEST_FILENAME


def _load_manifest(index_path: Path) -> dict[str, Any]:
    path = _manifest_path(index_path)
    if not path.exists():
        return {
            "schema_version": 1,
            "last_ingest_at": None,
            "documents": {},
        }

    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if "documents" not in payload:
        payload["documents"] = {}
    return payload


def _write_manifest(index_path: Path, payload: dict[str, Any]) -> None:
    index_path.mkdir(parents=True, exist_ok=True)
    path = _manifest_path(index_path)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _require_write_approval(*, config: CliConfig, approve_write: bool) -> None:
    if config.require_write_approval and not approve_write:
        raise WriteApprovalRequiredError(
            "write approval is required. Re-run ingest with --approve-write or unset DOCCTL_REQUIRE_WRITE_APPROVAL."
        )


def _build_where_filter(*, doc_id: str | None, source: str | None, page: int | None) -> dict[str, Any] | None:
    conditions: list[dict[str, Any]] = []
    if doc_id:
        conditions.append({"doc_id": doc_id})
    if source:
        conditions.append({"source": source})
    if page:
        conditions.append({"page": int(page)})

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def _chunk_record_to_dict(record: ChunkRecord) -> dict[str, Any]:
    metadata = record.metadata
    if isinstance(metadata, dict):
        metadata_dict = dict(metadata)
    else:
        metadata_dict = asdict(metadata)
    return {
        "id": record.id,
        "text": record.text,
        "metadata": metadata_dict,
    }


def ingest_path(
    *,
    config: CliConfig,
    input_path: Path,
    recursive: bool,
    glob_pattern: str,
    force: bool,
    approve_write: bool,
    allow_model_download: bool,
) -> dict[str, object]:
    _require_write_approval(config=config, approve_write=approve_write)

    files = _discover_pdf_files(input_path=input_path, recursive=recursive, glob_pattern=glob_pattern)
    embedding_fn = create_embedding_function(
        model_name=config.embedding_model,
        allow_download=allow_model_download,
    )
    store = ChromaStore(
        index_path=config.index_path,
        collection_name=config.collection,
        embedding_function=embedding_fn,
        create_collection=True,
        embedding_model=config.embedding_model,
    )

    manifest = _load_manifest(config.index_path)
    manifest_docs: dict[str, Any] = manifest.setdefault("documents", {})

    indexed_files = 0
    skipped_files = 0
    indexed_pages = 0
    indexed_chunks = 0
    errors: list[dict[str, str]] = []
    first_docctl_error: DocctlError | None = None

    for file_path in files:
        source = _relative_source(file_path)
        doc_id = build_doc_id(source)
        title = file_path.stem
        content_hash = file_sha256(file_path)

        existing = manifest_docs.get(doc_id)
        if existing and not force and existing.get("content_hash") == content_hash:
            skipped_files += 1
            continue

        try:
            pages = extract_pdf_pages(file_path)
            chunks = chunk_document_pages(
                doc_id=doc_id,
                source=source,
                title=title,
                pages=pages,
            )
            if not chunks:
                raise EmptyExtractedTextError(f"no chunks produced for file: {file_path}")

            store.delete_by_doc_id(doc_id)
            store.upsert_chunks(chunks)

            indexed_files += 1
            indexed_pages += len(pages)
            indexed_chunks += len(chunks)

            manifest_docs[doc_id] = {
                "source": source,
                "title": title,
                "content_hash": content_hash,
                "pages": len(pages),
                "chunks": len(chunks),
                "last_ingest_at": _utc_now_iso(),
            }
        except Exception as error:  # noqa: BLE001
            if first_docctl_error is None and isinstance(error, DocctlError):
                first_docctl_error = error
            errors.append({"file": source, "error": str(error)})

    if indexed_files > 0:
        manifest["last_ingest_at"] = _utc_now_iso()
        manifest["embedding_model"] = config.embedding_model
        _write_manifest(config.index_path, manifest)

    if indexed_files == 0 and not skipped_files:
        if first_docctl_error is not None:
            raise first_docctl_error
        if errors:
            first_error = errors[0]["error"]
            raise EmptyExtractedTextError(f"no files were indexed. first failure: {first_error}")
        raise EmptyExtractedTextError("no files were indexed")

    return {
        "collection": config.collection,
        "embedding_model": config.embedding_model,
        "errors": errors,
        "files_discovered": len(files),
        "files_indexed": indexed_files,
        "files_skipped": skipped_files,
        "index_path": str(config.index_path),
        "pages_indexed": indexed_pages,
        "chunks_indexed": indexed_chunks,
    }


def search_chunks(
    *,
    config: CliConfig,
    query: str,
    top_k: int,
    doc_id: str | None,
    source: str | None,
    page: int | None,
    min_score: float | None,
    allow_model_download: bool,
) -> dict[str, object]:
    embedding_fn = create_embedding_function(
        model_name=config.embedding_model,
        allow_download=allow_model_download,
    )
    store = ChromaStore(
        index_path=config.index_path,
        collection_name=config.collection,
        embedding_function=embedding_fn,
        create_collection=False,
        embedding_model=config.embedding_model,
    )

    if store.count() == 0:
        raise EmptyIndexSearchError("search cannot run on an empty index")

    where = _build_where_filter(doc_id=doc_id, source=source, page=page)
    result = store.query(query=query, top_k=top_k, where=where)

    ids = (result.get("ids") or [[]])[0]
    texts = (result.get("documents") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]

    hits: list[dict[str, Any]] = []
    for index, chunk_id in enumerate(ids):
        distance = float(distances[index]) if index < len(distances) and distances[index] is not None else 0.0
        score = 1.0 / (1.0 + distance)
        if min_score is not None and score < min_score:
            continue

        metadata_raw = metadatas[index] if index < len(metadatas) else {}
        metadata = ChunkMetadata(
            doc_id=str(metadata_raw.get("doc_id", "")),
            source=str(metadata_raw.get("source", "")),
            title=str(metadata_raw.get("title", "")),
            page=int(metadata_raw.get("page", 0)),
            section=metadata_raw.get("section"),
        )
        hit = SearchHit(
            rank=len(hits) + 1,
            id=str(chunk_id),
            text=str(texts[index] if index < len(texts) else ""),
            distance=distance,
            score=score,
            metadata=metadata,
        )
        hits.append(asdict(hit))

    return {
        "collection": config.collection,
        "hits": hits,
        "index_path": str(config.index_path),
        "query": query,
        "top_k": top_k,
    }


def show_chunk(*, config: CliConfig, chunk_id: str, allow_model_download: bool) -> dict[str, object]:
    _ = allow_model_download
    store = ChromaStore(
        index_path=config.index_path,
        collection_name=config.collection,
        embedding_function=None,
        create_collection=False,
        embedding_model=config.embedding_model,
    )

    record = store.get_chunk(chunk_id=chunk_id)
    if not record:
        raise ChunkNotFoundError(f"chunk not found: {chunk_id}")

    return _chunk_record_to_dict(record)


def collect_stats(*, config: CliConfig) -> dict[str, object]:
    store = ChromaStore(
        index_path=config.index_path,
        collection_name=config.collection,
        embedding_function=None,
        create_collection=False,
        embedding_model=config.embedding_model,
    )

    manifest = _load_manifest(config.index_path)
    documents = manifest.get("documents", {})

    return {
        "collection": config.collection,
        "chunk_count": store.count(),
        "document_count": len(documents),
        "embedding_model": manifest.get("embedding_model", config.embedding_model),
        "index_path": str(config.index_path),
        "last_ingest_at": manifest.get("last_ingest_at"),
    }


def run_doctor(*, config: CliConfig, allow_model_download: bool) -> DoctorReport:
    checks: list[DoctorCheck] = []
    warnings: list[str] = []
    errors: list[str] = []

    path_target = config.index_path if config.index_path.exists() else config.index_path.parent
    path_ok = os.access(path_target, os.W_OK)
    checks.append(
        DoctorCheck(
            name="index_path_access",
            ok=path_ok,
            message=f"write access {'available' if path_ok else 'missing'} for {path_target}",
        )
    )
    if not path_ok:
        errors.append("index path is not writable")

    embedding_ok = False
    embedding_fn = None
    try:
        embedding_fn = create_embedding_function(
            model_name=config.embedding_model,
            allow_download=allow_model_download,
        )
        embedding_ok = True
        checks.append(
            DoctorCheck(
                name="embedding_configuration",
                ok=True,
                message=f"embedding model ready: {config.embedding_model}",
            )
        )
    except Exception as error:  # noqa: BLE001
        checks.append(
            DoctorCheck(
                name="embedding_configuration",
                ok=False,
                message=str(error),
            )
        )
        errors.append(str(error))

    collection_ok = False
    chunk_count = 0
    try:
        store = ChromaStore(
            index_path=config.index_path,
            collection_name=config.collection,
            embedding_function=embedding_fn if embedding_ok else None,
            create_collection=False,
            embedding_model=config.embedding_model,
        )
        chunk_count = store.count()
        collection_ok = True
        checks.append(
            DoctorCheck(
                name="collection_availability",
                ok=True,
                message=f"collection '{config.collection}' available with {chunk_count} chunks",
            )
        )
    except Exception as error:  # noqa: BLE001
        checks.append(DoctorCheck(name="collection_availability", ok=False, message=str(error)))
        warnings.append(str(error))

    query_ok = False
    if collection_ok and embedding_ok and chunk_count > 0:
        try:
            query_result = store.query(query="health check", top_k=1)
            query_ok = bool((query_result.get("ids") or [[]])[0])
            checks.append(
                DoctorCheck(
                    name="test_query",
                    ok=query_ok,
                    message="test query returned at least one hit" if query_ok else "test query returned no hits",
                )
            )
            if not query_ok:
                warnings.append("test query returned no hits")
        except Exception as error:  # noqa: BLE001
            checks.append(DoctorCheck(name="test_query", ok=False, message=str(error)))
            errors.append(str(error))
    else:
        checks.append(
            DoctorCheck(
                name="test_query",
                ok=False,
                message="test query skipped because collection is unavailable or empty",
            )
        )
        warnings.append("test query skipped")

    ok = all(check.ok for check in checks)
    return DoctorReport(ok=ok, checks=checks, warnings=warnings, errors=errors)
