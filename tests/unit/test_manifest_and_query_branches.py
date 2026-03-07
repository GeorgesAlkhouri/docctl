from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from docctl.config import CliConfig
from docctl.errors import ChunkNotFoundError
from docctl.service_manifest import catalog_documents, load_manifest, manifest_documents
from docctl.service_query import build_where_filter, search_hits_from_result, show_chunk
from docctl.service_types import ServiceDependencies, ShowRequest


def test_load_manifest_backfills_documents_key(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text('{"schema_version":1}', encoding="utf-8")

    manifest = load_manifest(tmp_path)
    assert manifest["documents"] == {}


def test_manifest_documents_returns_empty_dict_for_non_mapping() -> None:
    assert manifest_documents({"documents": []}) == {}


def test_catalog_documents_skips_non_dict_entries() -> None:
    docs = {
        "a": "not-a-dict",
        "b": {"source": "s.pdf", "title": "t", "units": 1, "chunks": 2, "content_hash": "x"},
    }
    catalog = catalog_documents(docs)
    assert len(catalog) == 1
    assert catalog[0]["doc_id"] == "b"
    assert catalog[0]["source"] == "s.pdf"
    assert catalog[0]["units"] == 1
    assert catalog[0]["chunks"] == 2


def test_catalog_documents_ignores_unknown_extra_fields() -> None:
    docs = {
        "a": {
            "source": "notes.md",
            "title": "n",
            "units": 2,
            "chunks": 2,
            "content_hash": "x",
            "legacy_modes": ["one", "two", "one"],
        }
    }
    catalog = catalog_documents(docs)
    assert "legacy_modes" not in catalog[0]


def test_catalog_documents_sorts_and_preserves_base_fields() -> None:
    docs = {
        "a": {"source": "notes.md", "title": "n", "units": 1, "chunks": 1, "content_hash": "x"},
        "b": {"source": "notes.bin", "title": "b", "units": 1, "chunks": 1, "content_hash": "y"},
    }
    catalog = catalog_documents(docs)
    assert [row["doc_id"] for row in catalog] == ["a", "b"]
    assert all("legacy_modes" not in row for row in catalog)


def test_build_where_filter_supports_source_and_title_only() -> None:
    where = build_where_filter(
        doc_id=None,
        source="source.pdf",
        title="manual",
    )
    assert where == {"$and": [{"source": "source.pdf"}, {"title": "manual"}]}


def test_search_hits_respects_min_score_threshold() -> None:
    result = {
        "ids": [["chunk-1"]],
        "documents": [["text"]],
        "metadatas": [
            [
                {
                    "doc_id": "d",
                    "source": "s",
                    "title": "t",
                }
            ]
        ],
        "distances": [[10.0]],
    }
    hits = search_hits_from_result(result=result, min_score=0.2)
    assert hits == []


def test_show_chunk_raises_when_store_returns_none(tmp_path: Path) -> None:
    class _Store:
        def count(self) -> int:
            return 0

        def query(
            self, *, query: str, top_k: int, where: dict[str, Any] | None = None
        ) -> dict[str, Any]:
            _ = (query, top_k, where)
            return {}

        def get_chunk(self, *, chunk_id: str) -> Any:
            _ = chunk_id
            return None

        def upsert_chunks(self, records: list[Any]) -> None:
            _ = records

        def delete_by_doc_id(self, doc_id: str) -> None:
            _ = doc_id

    deps = ServiceDependencies(
        embedding_factory=lambda **kwargs: object(),
        store_factory=lambda **kwargs: _Store(),
    )
    request = ShowRequest(
        config=CliConfig(index_path=tmp_path, collection="c", embedding_model="m"),
        chunk_id="missing",
        allow_model_download=False,
    )

    with pytest.raises(ChunkNotFoundError):
        show_chunk(request=request, deps=deps)
