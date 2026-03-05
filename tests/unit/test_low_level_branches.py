from __future__ import annotations

from pathlib import Path

import pytest

from docctl import chunking, embeddings, index_store, pdf_extract
from docctl.errors import EmptyExtractedTextError, IndexNotInitializedError, PdfReadError
from docctl.pdf_extract import PageText


def test_chunk_document_pages_skips_empty_node_content(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Node:
        def __init__(self, text: str) -> None:
            self.metadata = {
                "doc_id": "doc",
                "source": "src.pdf",
                "title": "Title",
                "page": 1,
            }
            self._text = text

        def get_content(self, metadata_mode: object) -> str:
            _ = metadata_mode
            return self._text

    class _Splitter:
        def __init__(self, *, chunk_size: int, chunk_overlap: int) -> None:
            _ = (chunk_size, chunk_overlap)

        def get_nodes_from_documents(self, documents: list[object]) -> list[_Node]:
            _ = documents
            return [_Node("   "), _Node("valid text")]

    monkeypatch.setattr(chunking, "SentenceSplitter", _Splitter)
    records = chunking.chunk_document_pages(
        doc_id="doc",
        source="src.pdf",
        title="Title",
        pages=[PageText(page=1, text="seed")],
    )

    assert len(records) == 1
    assert records[0].text == "valid text"


def test_embedding_call_encodes_and_converts_to_lists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Vectors:
        def __init__(self, values: list[list[float]]) -> None:
            self._values = values

        def tolist(self) -> list[list[float]]:
            return self._values

    class _Model:
        def encode(
            self, input: list[str], *, normalize_embeddings: bool, show_progress_bar: bool
        ) -> _Vectors:
            assert input == ["a", "b"]
            assert normalize_embeddings is True
            assert show_progress_bar is True
            return _Vectors([[0.1, 0.2], [0.3, 0.4]])

    monkeypatch.setattr(embeddings, "SentenceTransformer", lambda *args, **kwargs: _Model())
    embedding_fn = embeddings.LocalSentenceTransformerEmbedding(
        model_name="fake",
        allow_download=False,
        verbose=True,
    )

    vectors = embedding_fn(["a", "b"])
    assert [list(row) for row in vectors] == [[0.1, 0.2], [0.3, 0.4]]


def test_index_store_constructor_raises_when_collection_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class _CollectionInfo:
        name = "other"

    class _Client:
        def __init__(self, *, path: str) -> None:
            self.path = path

        def list_collections(self) -> list[_CollectionInfo]:
            return [_CollectionInfo()]

        def get_collection(self, *, name: str, embedding_function: object) -> object:
            _ = (name, embedding_function)
            raise AssertionError("get_collection must not be called for missing collection")

    chroma_path = tmp_path / "index" / "chroma"
    chroma_path.mkdir(parents=True)
    monkeypatch.setattr(index_store.chromadb, "PersistentClient", _Client)

    with pytest.raises(IndexNotInitializedError):
        index_store.ChromaStore(
            index_path=tmp_path / "index",
            collection_name="missing",
            embedding_function=None,
            create_collection=False,
            embedding_model="fake-model",
        )


def test_index_store_upsert_empty_records_is_noop() -> None:
    class _Collection:
        def upsert(self, **kwargs: object) -> None:
            _ = kwargs
            raise AssertionError("upsert should not run for empty records")

    store = object.__new__(index_store.ChromaStore)
    store.collection = _Collection()
    store.upsert_chunks([])


def test_index_store_metadata_handles_none() -> None:
    class _Collection:
        metadata = None

    store = object.__new__(index_store.ChromaStore)
    store.collection = _Collection()
    assert store.metadata() == {}


def test_extract_with_pdfplumber_wraps_unexpected_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def _boom(path: Path) -> object:
        _ = path
        raise RuntimeError("boom")

    monkeypatch.setattr(pdf_extract.pdfplumber, "open", _boom)

    with pytest.raises(PdfReadError):
        pdf_extract._extract_with_pdfplumber(tmp_path / "sample.pdf")


def test_extract_with_pypdf_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class _Page:
        @staticmethod
        def extract_text() -> str:
            return "text"

    class _Reader:
        def __init__(self, path: str) -> None:
            _ = path
            self.pages = [_Page()]

    monkeypatch.setattr(pdf_extract, "PdfReader", _Reader)
    pages = pdf_extract._extract_with_pypdf(tmp_path / "sample.pdf")
    assert pages == [PageText(page=1, text="text")]


def test_extract_with_pypdf_wraps_unexpected_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class _Reader:
        def __init__(self, path: str) -> None:
            _ = path
            raise RuntimeError("bad")

    monkeypatch.setattr(pdf_extract, "PdfReader", _Reader)

    with pytest.raises(PdfReadError):
        pdf_extract._extract_with_pypdf(tmp_path / "sample.pdf")


def test_extract_pdf_pages_falls_back_to_pypdf(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        pdf_extract,
        "_extract_with_pdfplumber",
        lambda path: (_ for _ in ()).throw(PdfReadError(f"failed: {path}")),
    )
    monkeypatch.setattr(
        pdf_extract,
        "_extract_with_pypdf",
        lambda path: [PageText(page=1, text="fallback text")],
    )

    pages = pdf_extract.extract_pdf_pages(tmp_path / "sample.pdf")
    assert pages == [PageText(page=1, text="fallback text")]


def test_extract_pdf_pages_raises_when_all_pages_empty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        pdf_extract,
        "_extract_with_pdfplumber",
        lambda path: [PageText(page=1, text=" \n "), PageText(page=2, text="\n\t")],
    )

    with pytest.raises(EmptyExtractedTextError):
        pdf_extract.extract_pdf_pages(tmp_path / "sample.pdf")
