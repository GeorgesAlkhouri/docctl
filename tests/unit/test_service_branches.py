from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from docctl import service_doctor, service_ingest, service_session
from docctl.config import CliConfig
from docctl.errors import (
    DocctlError,
    EmptyExtractedTextError,
    EmptyIndexSearchError,
    InputPathNotFoundError,
)
from docctl.models import ChunkMetadata, ChunkRecord, DoctorCheck, DoctorReport
from docctl.pdf_extract import PageText
from docctl.service_types import (
    DoctorRequest,
    IngestRequest,
    ServiceDependencies,
    SessionStreamRequest,
)


class _SessionStore:
    def __init__(
        self,
        *,
        count_value: int = 1,
        query_result: dict[str, Any] | None = None,
        chunk: ChunkRecord | None = None,
    ) -> None:
        self._count_value = count_value
        self._query_result = query_result or {"ids": [[]], "documents": [[]], "metadatas": [[]]}
        self._chunk = chunk or ChunkRecord(
            id="chunk-1",
            text="text",
            metadata=ChunkMetadata(doc_id="d", source="s", title="t", page=1, section=None),
        )

    def count(self) -> int:
        return self._count_value

    def query(
        self, *, query: str, top_k: int, where: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        _ = (query, top_k, where)
        return self._query_result

    def get_chunk(self, *, chunk_id: str) -> ChunkRecord:
        _ = chunk_id
        return self._chunk

    def upsert_chunks(self, records: list[ChunkRecord]) -> None:
        _ = records

    def delete_by_doc_id(self, doc_id: str) -> None:
        _ = doc_id


def _config(tmp_path: Path, *, verbose: bool = False) -> CliConfig:
    return CliConfig(
        index_path=tmp_path,
        collection="test",
        json_output=False,
        verbose=verbose,
        embedding_model="model",
        require_write_approval=False,
    )


def test_doctor_embedding_configuration_error_branch(tmp_path: Path) -> None:
    deps = ServiceDependencies(
        embedding_factory=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("bad embedding")),
        store_factory=lambda **kwargs: _SessionStore(),
    )
    request = DoctorRequest(config=_config(tmp_path), allow_model_download=False)

    check, embedding_fn, ok, errors = service_doctor._check_embedding_configuration(
        request=request,
        deps=deps,
    )

    assert check.ok is False
    assert embedding_fn is None
    assert ok is False
    assert errors == ["bad embedding"]


def test_doctor_collection_availability_error_branch(tmp_path: Path) -> None:
    deps = ServiceDependencies(
        embedding_factory=lambda **kwargs: object(),
        store_factory=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("missing collection")),
    )
    request = DoctorRequest(config=_config(tmp_path), allow_model_download=False)

    check, store, ok, chunk_count, warnings = service_doctor._check_collection_availability(
        request=request,
        deps=deps,
        embedding_fn=None,
        embedding_ok=False,
    )

    assert check.ok is False
    assert store is None
    assert ok is False
    assert chunk_count == 0
    assert warnings == ["missing collection"]


def test_doctor_test_query_skip_and_exception_paths() -> None:
    skipped, warnings, errors = service_doctor._check_test_query(
        collection_ok=False,
        embedding_ok=True,
        chunk_count=1,
        store=_SessionStore(),
    )
    assert skipped.ok is False
    assert warnings == ["test query skipped"]
    assert errors == []

    class _ExplodingStore(_SessionStore):
        def query(
            self, *, query: str, top_k: int, where: dict[str, Any] | None = None
        ) -> dict[str, Any]:
            _ = (query, top_k, where)
            raise RuntimeError("query failed")

    failed, warnings, errors = service_doctor._check_test_query(
        collection_ok=True,
        embedding_ok=True,
        chunk_count=1,
        store=_ExplodingStore(),
    )
    assert failed.ok is False
    assert warnings == []
    assert errors == ["query failed"]


def test_discover_pdf_files_rejects_non_pdf_file(tmp_path: Path) -> None:
    file_path = tmp_path / "notes.txt"
    file_path.write_text("x", encoding="utf-8")

    with pytest.raises(InputPathNotFoundError):
        service_ingest.discover_pdf_files(
            input_path=file_path, recursive=False, glob_pattern="*.pdf"
        )


def test_discover_pdf_files_raises_when_directory_has_no_pdfs(tmp_path: Path) -> None:
    with pytest.raises(InputPathNotFoundError):
        service_ingest.discover_pdf_files(
            input_path=tmp_path, recursive=False, glob_pattern="*.pdf"
        )


def test_ingest_document_raises_when_chunker_returns_no_chunks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(b"%PDF")
    context = service_ingest._DocumentContext(
        source="doc.pdf",
        doc_id="doc-id",
        title="doc",
        content_hash="hash",
    )
    monkeypatch.setattr(
        service_ingest, "extract_pdf_pages", lambda _: [PageText(page=1, text="text")]
    )
    monkeypatch.setattr(service_ingest, "chunk_document_pages", lambda **kwargs: [])

    with pytest.raises(EmptyExtractedTextError):
        service_ingest._ingest_document(file_path=pdf_path, context=context, store=_SessionStore())


def test_record_error_tracks_first_docctl_error() -> None:
    state = service_ingest._IngestState()
    context = service_ingest._DocumentContext(
        source="doc.pdf",
        doc_id="doc-id",
        title="doc",
        content_hash="hash",
    )
    error = InputPathNotFoundError("missing")

    service_ingest._record_error(context=context, error=error, state=state)

    assert state.first_docctl_error is error
    assert state.errors == [{"file": "doc.pdf", "error": "missing"}]


def test_process_files_skips_existing_documents(tmp_path: Path) -> None:
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    request = IngestRequest(
        config=_config(tmp_path),
        input_path=tmp_path,
        recursive=False,
        glob_pattern="*.pdf",
        force=False,
        approve_write=True,
        allow_model_download=False,
    )
    context = service_ingest._document_context(pdf_path)
    manifest_docs = {context.doc_id: {"content_hash": context.content_hash}}

    state = service_ingest._process_files(
        files=[pdf_path],
        request=request,
        manifest_docs=manifest_docs,
        store=_SessionStore(),
    )

    assert state.skipped_files == 1
    assert state.indexed_files == 0


def test_process_files_records_non_docctl_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    request = IngestRequest(
        config=_config(tmp_path),
        input_path=tmp_path,
        recursive=False,
        glob_pattern="*.pdf",
        force=True,
        approve_write=True,
        allow_model_download=False,
    )
    monkeypatch.setattr(
        service_ingest,
        "_ingest_document",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("ingest failed")),
    )

    state = service_ingest._process_files(
        files=[pdf_path],
        request=request,
        manifest_docs={},
        store=_SessionStore(),
    )

    assert state.errors[0]["error"] == "ingest failed"
    assert state.first_docctl_error is None


def test_finalize_manifest_skips_write_when_nothing_indexed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    request = IngestRequest(
        config=_config(tmp_path),
        input_path=tmp_path,
        recursive=False,
        glob_pattern="*.pdf",
        force=False,
        approve_write=True,
        allow_model_download=False,
    )
    manifest = {"documents": {}}
    state = service_ingest._IngestState(indexed_files=0)
    monkeypatch.setattr(
        service_ingest,
        "write_manifest",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError),
    )

    service_ingest._finalize_manifest(request=request, manifest=manifest, state=state)


def test_raise_if_no_indexed_files_branches() -> None:
    docctl_error_state = service_ingest._IngestState(
        indexed_files=0,
        skipped_files=0,
        first_docctl_error=InputPathNotFoundError("missing"),
    )
    with pytest.raises(InputPathNotFoundError):
        service_ingest._raise_if_no_indexed_files(state=docctl_error_state)

    error_state = service_ingest._IngestState(
        indexed_files=0,
        skipped_files=0,
        errors=[{"file": "x", "error": "boom"}],
    )
    with pytest.raises(EmptyExtractedTextError, match="first failure: boom"):
        service_ingest._raise_if_no_indexed_files(state=error_state)

    empty_state = service_ingest._IngestState(indexed_files=0, skipped_files=0)
    with pytest.raises(EmptyExtractedTextError, match="no files were indexed"):
        service_ingest._raise_if_no_indexed_files(state=empty_state)


def test_suppress_external_output_disabled_leaves_streams_visible(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with service_session.suppress_external_output(enabled=False):
        print("visible")
    assert capsys.readouterr().out.strip() == "visible"


def test_session_runtime_search_raises_for_empty_index(tmp_path: Path) -> None:
    store = _SessionStore(count_value=0)
    deps = ServiceDependencies(
        embedding_factory=lambda **kwargs: object(),
        store_factory=lambda **kwargs: store,
    )
    runtime = service_session.SessionRuntime(
        request=SessionStreamRequest(
            config=_config(tmp_path), request_lines=[], allow_model_download=False
        ),
        deps=deps,
    )
    request = service_session._SessionSearchRequest(
        query="q",
        top_k=3,
        doc_id=None,
        source=None,
        title=None,
        page=None,
        min_score=None,
    )

    with pytest.raises(EmptyIndexSearchError):
        runtime.search(request=request)


def test_session_runtime_show_stats_catalog_and_doctor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    store = _SessionStore(count_value=3)
    deps = ServiceDependencies(
        embedding_factory=lambda **kwargs: object(),
        store_factory=lambda **kwargs: store,
    )
    runtime = service_session.SessionRuntime(
        request=SessionStreamRequest(
            config=_config(tmp_path), request_lines=[], allow_model_download=False
        ),
        deps=deps,
    )
    monkeypatch.setattr(
        service_session,
        "load_manifest",
        lambda _: {
            "embedding_model": "manifest-model",
            "last_ingest_at": "2026-01-01T00:00:00+00:00",
            "documents": {
                "d1": {
                    "source": "a.pdf",
                    "title": "a",
                    "pages": 2,
                    "chunks": 4,
                    "content_hash": "h",
                    "last_ingest_at": "2026-01-01T00:00:00+00:00",
                }
            },
        },
    )
    monkeypatch.setattr(
        service_session,
        "run_doctor",
        lambda request, deps: DoctorReport(
            ok=True,
            checks=[DoctorCheck(name="x", ok=True, message="ok")],
            warnings=[],
            errors=[],
        ),
    )

    shown = runtime.show(chunk_id="chunk-1")
    stats = runtime.stats()
    catalog = runtime.catalog()
    doctor = runtime.doctor()

    assert shown["id"] == "chunk-1"
    assert stats["chunk_count"] == 3
    assert catalog["summary"]["pages_total"] == 2
    assert doctor["ok"] is True


def test_session_error_uses_internal_code_for_unexpected_exception() -> None:
    payload = service_session.session_error(request_id="r1", error=RuntimeError("boom"))
    assert payload["error"]["exit_code"] == 50
    assert payload["error"]["message"] == "boom"


def test_parse_payload_and_operation_validation_errors() -> None:
    with pytest.raises(DocctlError):
        service_session._parse_payload("[1,2,3]")
    with pytest.raises(DocctlError):
        service_session._parse_operation({"op": 7})


def test_operation_helpers_delegate_to_runtime_methods(tmp_path: Path) -> None:
    runtime = service_session.SessionRuntime(
        request=SessionStreamRequest(
            config=_config(tmp_path), request_lines=[], allow_model_download=False
        ),
        deps=ServiceDependencies(
            embedding_factory=lambda **kwargs: object(),
            store_factory=lambda **kwargs: _SessionStore(),
        ),
    )

    assert "chunk_count" in service_session._handle_stats(runtime, {})
    assert "documents" in service_session._handle_catalog(runtime, {})
    assert "checks" in service_session._handle_doctor(runtime, {})


def test_search_and_show_handlers_validate_required_fields(tmp_path: Path) -> None:
    runtime = service_session.SessionRuntime(
        request=SessionStreamRequest(
            config=_config(tmp_path), request_lines=[], allow_model_download=False
        ),
        deps=ServiceDependencies(
            embedding_factory=lambda **kwargs: object(),
            store_factory=lambda **kwargs: _SessionStore(),
        ),
    )

    with pytest.raises(DocctlError, match="invalid session request field 'query'"):
        service_session._handle_search(runtime, {"query": "   ", "top_k": 5})
    with pytest.raises(DocctlError, match="invalid session request field 'top_k'"):
        service_session._handle_search(runtime, {"query": "ok", "top_k": 0})
    with pytest.raises(DocctlError, match="invalid session request field 'chunk_id'"):
        service_session._handle_show(runtime, {"chunk_id": 7})

    show_result = service_session._handle_show(runtime, {"chunk_id": "chunk-1"})
    assert show_result["id"] == "chunk-1"


def test_run_session_requests_skips_blank_lines_and_reports_unsupported_op(tmp_path: Path) -> None:
    request = SessionStreamRequest(
        config=_config(tmp_path),
        request_lines=["   ", '{"id":"r1","op":"unknown"}'],
        allow_model_download=False,
    )
    deps = ServiceDependencies(
        embedding_factory=lambda **kwargs: object(),
        store_factory=lambda **kwargs: _SessionStore(),
    )

    responses = list(service_session.run_session_requests(request=request, deps=deps))
    assert len(responses) == 1
    assert responses[0]["id"] == "r1"
    assert responses[0]["ok"] is False
    assert "unsupported session operation" in responses[0]["error"]["message"]


def test_build_where_filter_returns_doc_id_only_mapping() -> None:
    assert service_session.build_where_filter(doc_id="d1", source=None, title=None, page=None) == {
        "doc_id": "d1"
    }
