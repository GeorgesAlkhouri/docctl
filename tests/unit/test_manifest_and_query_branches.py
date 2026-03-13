from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from docctl.config import CliConfig
from docctl.errors import ChunkNotFoundError, DocctlError, InternalDocctlError
from docctl.service_manifest import catalog_documents, load_manifest, manifest_documents
from docctl.service_query import (
    build_where_filter,
    rerank_hits,
    resolve_rerank_candidate_count,
    search_hits_from_result,
    show_chunk,
)
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


def test_resolve_rerank_candidate_count_defaults_and_bounds() -> None:
    assert resolve_rerank_candidate_count(top_k=5, rerank_candidates=None) == 10
    assert resolve_rerank_candidate_count(top_k=30, rerank_candidates=None) == 30
    assert resolve_rerank_candidate_count(top_k=5, rerank_candidates=7) == 7

    with pytest.raises(DocctlError):
        resolve_rerank_candidate_count(top_k=5, rerank_candidates=4)


def test_rerank_hits_adds_metadata_and_sorts_by_rerank_score(tmp_path: Path) -> None:
    class _Reranker:
        def score(self, *, query: str, texts: list[str]) -> list[float]:
            _ = query
            return [0.1, 0.9, 0.9][: len(texts)]

    captured: dict[str, Any] = {}

    def _factory(**kwargs: Any) -> _Reranker:
        captured.update(kwargs)
        return _Reranker()

    deps = ServiceDependencies(
        embedding_factory=lambda **kwargs: object(),
        store_factory=lambda **kwargs: object(),
        reranker_factory=_factory,
    )
    config = CliConfig(
        index_path=tmp_path,
        collection="c",
        embedding_model="m",
        rerank_model="r",
    )
    hits = [
        {"rank": 1, "id": "a", "text": "A", "distance": 0.1, "score": 0.9, "metadata": {}},
        {"rank": 2, "id": "b", "text": "B", "distance": 0.2, "score": 0.8, "metadata": {}},
        {"rank": 3, "id": "c", "text": "C", "distance": 0.3, "score": 0.7, "metadata": {}},
    ]

    reranked = rerank_hits(
        hits=hits,
        query="query",
        top_k=2,
        config=config,
        allow_model_download=False,
        deps=deps,
    )

    assert [hit["id"] for hit in reranked] == ["b", "c"]
    assert [hit["rank"] for hit in reranked] == [1, 2]
    assert [hit["vector_rank"] for hit in reranked] == [2, 3]
    assert all("rerank_score" in hit for hit in reranked)
    assert captured == {
        "model_name": "r",
        "allow_download": False,
        "verbose": False,
    }


def test_rerank_hits_returns_empty_when_candidate_hits_empty(tmp_path: Path) -> None:
    deps = ServiceDependencies(
        embedding_factory=lambda **kwargs: object(),
        store_factory=lambda **kwargs: object(),
        reranker_factory=lambda **kwargs: object(),
    )
    config = CliConfig(index_path=tmp_path, collection="c", embedding_model="m", rerank_model="r")

    reranked = rerank_hits(
        hits=[],
        query="query",
        top_k=2,
        config=config,
        allow_model_download=False,
        deps=deps,
    )

    assert reranked == []


def test_rerank_hits_raises_when_reranker_factory_missing(tmp_path: Path) -> None:
    deps = ServiceDependencies(
        embedding_factory=lambda **kwargs: object(),
        store_factory=lambda **kwargs: object(),
        reranker_factory=None,
    )
    config = CliConfig(index_path=tmp_path, collection="c", embedding_model="m", rerank_model="r")

    with pytest.raises(InternalDocctlError, match="reranker factory is not configured"):
        rerank_hits(
            hits=[
                {"rank": 1, "id": "a", "text": "A", "distance": 0.1, "score": 0.9, "metadata": {}}
            ],
            query="query",
            top_k=1,
            config=config,
            allow_model_download=False,
            deps=deps,
        )


def test_rerank_hits_raises_when_score_count_is_invalid(tmp_path: Path) -> None:
    class _BadReranker:
        def score(self, *, query: str, texts: list[str]) -> list[float]:
            _ = (query, texts)
            return [0.5]

    deps = ServiceDependencies(
        embedding_factory=lambda **kwargs: object(),
        store_factory=lambda **kwargs: object(),
        reranker_factory=lambda **kwargs: _BadReranker(),
    )
    config = CliConfig(index_path=tmp_path, collection="c", embedding_model="m", rerank_model="r")

    with pytest.raises(InternalDocctlError, match="reranker returned an invalid score count"):
        rerank_hits(
            hits=[
                {"rank": 1, "id": "a", "text": "A", "distance": 0.1, "score": 0.9, "metadata": {}},
                {"rank": 2, "id": "b", "text": "B", "distance": 0.2, "score": 0.8, "metadata": {}},
            ],
            query="query",
            top_k=2,
            config=config,
            allow_model_download=False,
            deps=deps,
        )


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
