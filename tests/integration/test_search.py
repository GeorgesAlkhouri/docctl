from __future__ import annotations

import json
from pathlib import Path

from docctl.cli import app


def _json(output: str) -> dict:
    return json.loads(output.strip())


def test_search_json_contract_with_metadata(runner, make_pdf, patch_fake_embeddings, tmp_path: Path) -> None:
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
        ["--index-path", str(index_path), "--collection", "test", "--json", "ingest", str(pdf_path)],
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
    assert {"doc_id", "source", "title", "page"}.issubset(hit["metadata"].keys())
