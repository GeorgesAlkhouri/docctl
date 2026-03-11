from __future__ import annotations

import json
from pathlib import Path

from docctl.cli import app


def _json(output: str) -> dict:
    return json.loads(output.strip())


def test_search_json_contract_with_metadata(
    runner, make_pdf, patch_fake_embeddings, tmp_path: Path
) -> None:
    pdf_path = make_pdf(
        tmp_path / "searchable.pdf",
        [
            "Vehicle diagnostics sentence one. Vehicle diagnostics sentence two.",
            "Cyber security gateway data retrieval text.",
        ],
    )
    index_path = tmp_path / "index"

    ingest_result = runner.invoke(
        app,
        [
            "--index-path",
            str(index_path),
            "--collection",
            "test",
            "--json",
            "ingest",
            str(pdf_path),
        ],
    )
    assert ingest_result.exit_code == 0, ingest_result.output

    search_result = runner.invoke(
        app,
        [
            "--index-path",
            str(index_path),
            "--collection",
            "test",
            "--json",
            "search",
            "vehicle diagnostics",
            "--top-k",
            "3",
        ],
    )

    assert search_result.exit_code == 0, search_result.output
    payload = _json(search_result.output)

    assert set(payload.keys()) == {"collection", "hits", "index_path", "query", "top_k"}
    assert payload["query"] == "vehicle diagnostics"
    assert payload["top_k"] == 3
    assert len(payload["hits"]) >= 1

    hit = payload["hits"][0]
    assert {"id", "text", "metadata", "distance", "score", "rank"}.issubset(hit.keys())
    assert {"doc_id", "source", "title"}.issubset(hit["metadata"].keys())


def test_search_supports_title_filter(
    runner, make_pdf, patch_fake_embeddings, tmp_path: Path
) -> None:
    alpha_pdf = make_pdf(
        tmp_path / "alpha-manual.pdf",
        [
            "Shared retrieval phrase for alpha page one.",
            "Shared retrieval phrase for alpha page two.",
        ],
    )
    beta_pdf = make_pdf(
        tmp_path / "beta-manual.pdf",
        [
            "Shared retrieval phrase for beta page one.",
        ],
    )
    index_path = tmp_path / "index"

    for pdf_path in (alpha_pdf, beta_pdf):
        ingest_result = runner.invoke(
            app,
            [
                "--index-path",
                str(index_path),
                "--collection",
                "test",
                "--json",
                "ingest",
                str(pdf_path),
            ],
        )
        assert ingest_result.exit_code == 0, ingest_result.output

    title_filtered = runner.invoke(
        app,
        [
            "--index-path",
            str(index_path),
            "--collection",
            "test",
            "--json",
            "search",
            "shared retrieval phrase",
            "--top-k",
            "10",
            "--title",
            "alpha-manual",
        ],
    )
    assert title_filtered.exit_code == 0, title_filtered.output
    title_payload = _json(title_filtered.output)

    assert len(title_payload["hits"]) >= 1
    assert all(hit["metadata"]["title"] == "alpha-manual" for hit in title_payload["hits"])


def test_search_rerank_adds_fields_and_reorders_hits(
    runner,
    make_pdf,
    patch_fake_embeddings,
    patch_fake_reranker,
    monkeypatch,
    tmp_path: Path,
) -> None:
    pdf_path = make_pdf(tmp_path / "doc.pdf", ["Baseline text for index initialization."])
    index_path = tmp_path / "index"
    ingest_result = runner.invoke(
        app,
        [
            "--index-path",
            str(index_path),
            "--collection",
            "test",
            "--json",
            "ingest",
            str(pdf_path),
        ],
    )
    assert ingest_result.exit_code == 0, ingest_result.output

    monkeypatch.setattr("docctl.index_store.ChromaStore.count", lambda self: 1)
    monkeypatch.setattr(
        "docctl.index_store.ChromaStore.query",
        lambda self, query, top_k, where=None: {
            "ids": [["a", "b"]],
            "documents": [["short", "this is a longer passage"]],
            "metadatas": [
                [
                    {"doc_id": "d", "source": "s", "title": "ta"},
                    {"doc_id": "d", "source": "s", "title": "tb"},
                ]
            ],
            "distances": [[0.0, 0.1]],
        },
    )

    search_result = runner.invoke(
        app,
        [
            "--index-path",
            str(index_path),
            "--collection",
            "test",
            "--json",
            "search",
            "anything",
            "--top-k",
            "2",
            "--rerank",
        ],
    )
    assert search_result.exit_code == 0, search_result.output
    payload = _json(search_result.output)

    assert [hit["id"] for hit in payload["hits"]] == ["b", "a"]
    assert all("vector_rank" in hit for hit in payload["hits"])
    assert all("rerank_score" in hit for hit in payload["hits"])
