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
