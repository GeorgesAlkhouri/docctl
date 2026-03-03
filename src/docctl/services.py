"""Service layer for docctl commands."""

from __future__ import annotations

from contextlib import contextmanager, redirect_stderr, redirect_stdout
import io
import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .chunking import chunk_document_pages
from .config import CliConfig
from .embeddings import create_embedding_function
from .errors import (
    ChunkNotFoundError,
    DocctlError,
    EmptyExtractedTextError,
    EmptyIndexSearchError,
    InternalDocctlError,
    InputPathNotFoundError,
    WriteApprovalRequiredError,
)
from .ids import build_doc_id, file_sha256
from .index_store import ChromaStore
from .models import ChunkMetadata, ChunkRecord, DoctorCheck, DoctorReport, SearchHit
from .pdf_extract import extract_pdf_pages
from .text_sanitize import sanitize_text

_MANIFEST_FILENAME = "manifest.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@contextmanager
def _suppress_external_output(*, enabled: bool):
    if not enabled:
        yield
        return
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        yield


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
        "text": sanitize_text(record.text),
        "metadata": metadata_dict,
    }


def _search_hits_from_result(
    *,
    result: dict[str, Any],
    min_score: float | None,
) -> list[dict[str, Any]]:
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
            text=sanitize_text(str(texts[index] if index < len(texts) else "")),
            distance=distance,
            score=score,
            metadata=metadata,
        )
        hits.append(asdict(hit))

    return hits


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
        verbose=config.verbose,
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
        verbose=config.verbose,
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
    hits = _search_hits_from_result(result=result, min_score=min_score)

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


class _SessionRuntime:
    def __init__(self, *, config: CliConfig, allow_model_download: bool) -> None:
        self._config = config
        self._allow_model_download = allow_model_download
        self._embedding_fn = None
        self._search_store: ChromaStore | None = None
        self._readonly_store: ChromaStore | None = None

    def _get_embedding_fn(self) -> Any:
        if self._embedding_fn is None:
            self._embedding_fn = create_embedding_function(
                model_name=self._config.embedding_model,
                allow_download=self._allow_model_download,
                verbose=self._config.verbose,
            )
        return self._embedding_fn

    def _get_search_store(self) -> ChromaStore:
        if self._search_store is None:
            self._search_store = ChromaStore(
                index_path=self._config.index_path,
                collection_name=self._config.collection,
                embedding_function=self._get_embedding_fn(),
                create_collection=False,
                embedding_model=self._config.embedding_model,
            )
        return self._search_store

    def _get_readonly_store(self) -> ChromaStore:
        if self._readonly_store is None:
            self._readonly_store = ChromaStore(
                index_path=self._config.index_path,
                collection_name=self._config.collection,
                embedding_function=None,
                create_collection=False,
                embedding_model=self._config.embedding_model,
            )
        return self._readonly_store

    def search(
        self,
        *,
        query: str,
        top_k: int,
        doc_id: str | None,
        source: str | None,
        page: int | None,
        min_score: float | None,
    ) -> dict[str, object]:
        store = self._get_search_store()
        if store.count() == 0:
            raise EmptyIndexSearchError("search cannot run on an empty index")
        where = _build_where_filter(doc_id=doc_id, source=source, page=page)
        result = store.query(query=query, top_k=top_k, where=where)
        hits = _search_hits_from_result(result=result, min_score=min_score)
        return {
            "collection": self._config.collection,
            "hits": hits,
            "index_path": str(self._config.index_path),
            "query": query,
            "top_k": top_k,
        }

    def show(self, *, chunk_id: str) -> dict[str, object]:
        record = self._get_readonly_store().get_chunk(chunk_id=chunk_id)
        return _chunk_record_to_dict(record)

    def stats(self) -> dict[str, object]:
        manifest = _load_manifest(self._config.index_path)
        documents = manifest.get("documents", {})
        store = self._get_readonly_store()
        return {
            "collection": self._config.collection,
            "chunk_count": store.count(),
            "document_count": len(documents),
            "embedding_model": manifest.get("embedding_model", self._config.embedding_model),
            "index_path": str(self._config.index_path),
            "last_ingest_at": manifest.get("last_ingest_at"),
        }

    def doctor(self) -> dict[str, object]:
        report = run_doctor(config=self._config, allow_model_download=self._allow_model_download)
        return asdict(report)


def _to_optional_str(value: Any, *, field_name: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise DocctlError(message=f"invalid session request field '{field_name}'", exit_code=50)


def _to_optional_int(value: Any, *, field_name: str, minimum: int | None = None) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int):
        raise DocctlError(message=f"invalid session request field '{field_name}'", exit_code=50)
    if minimum is not None and value < minimum:
        raise DocctlError(message=f"invalid session request field '{field_name}'", exit_code=50)
    return value


def _to_optional_float(
    value: Any, *, field_name: str, minimum: float | None = None, maximum: float | None = None
) -> float | None:
    if value is None:
        return None
    if not isinstance(value, (float, int)):
        raise DocctlError(message=f"invalid session request field '{field_name}'", exit_code=50)
    parsed = float(value)
    if minimum is not None and parsed < minimum:
        raise DocctlError(message=f"invalid session request field '{field_name}'", exit_code=50)
    if maximum is not None and parsed > maximum:
        raise DocctlError(message=f"invalid session request field '{field_name}'", exit_code=50)
    return parsed


def _session_error(*, request_id: Any, error: Exception) -> dict[str, Any]:
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


def run_session_requests(
    *,
    config: CliConfig,
    request_lines: Iterable[str],
    allow_model_download: bool,
) -> Iterable[dict[str, Any]]:
    runtime = _SessionRuntime(config=config, allow_model_download=allow_model_download)

    for raw_line in request_lines:
        line = raw_line.strip()
        if not line:
            continue

        request_id: Any = None
        try:
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise DocctlError(message="invalid session request payload", exit_code=50)

            request_id = payload.get("id")
            op = payload.get("op")
            if not isinstance(op, str):
                raise DocctlError(message="invalid session request field 'op'", exit_code=50)

            with _suppress_external_output(enabled=not config.verbose):
                if op == "search":
                    query = payload.get("query")
                    if not isinstance(query, str) or not query.strip():
                        raise DocctlError(message="invalid session request field 'query'", exit_code=50)

                    top_k_value = payload.get("top_k", 5)
                    if not isinstance(top_k_value, int) or top_k_value < 1 or top_k_value > 100:
                        raise DocctlError(message="invalid session request field 'top_k'", exit_code=50)

                    result = runtime.search(
                        query=query,
                        top_k=top_k_value,
                        doc_id=_to_optional_str(payload.get("doc_id"), field_name="doc_id"),
                        source=_to_optional_str(payload.get("source"), field_name="source"),
                        page=_to_optional_int(payload.get("page"), field_name="page", minimum=1),
                        min_score=_to_optional_float(
                            payload.get("min_score"),
                            field_name="min_score",
                            minimum=0.0,
                            maximum=1.0,
                        ),
                    )
                elif op == "show":
                    chunk_id = payload.get("chunk_id")
                    if not isinstance(chunk_id, str) or not chunk_id:
                        raise DocctlError(message="invalid session request field 'chunk_id'", exit_code=50)
                    result = runtime.show(chunk_id=chunk_id)
                elif op == "stats":
                    result = runtime.stats()
                elif op == "doctor":
                    result = runtime.doctor()
                else:
                    raise DocctlError(message=f"unsupported session operation: {op}", exit_code=50)

            yield {
                "id": request_id,
                "ok": True,
                "result": result,
            }
        except Exception as error:  # noqa: BLE001
            yield _session_error(request_id=request_id, error=error)


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
            verbose=config.verbose,
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
