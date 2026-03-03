from __future__ import annotations

import json
from pathlib import Path

from docctl.cli import app


def _json(output: str) -> dict:
    return json.loads(output.strip())


def test_show_chunk_by_id(runner, make_pdf, patch_fake_embeddings, tmp_path: Path) -> None:
    pdf_path = make_pdf(
        tmp_path / "doc.pdf",
        ["Diagnostic chunk one. Diagnostic chunk two."],
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
        ["--index-path", str(index_path), "--collection", "test", "--json", "search", "diagnostic"],
    )
    assert search_result.exit_code == 0, search_result.output
    search_payload = _json(search_result.output)
    assert search_payload["hits"]

    chunk_id = search_payload["hits"][0]["id"]
    show_result = runner.invoke(
        app,
        ["--index-path", str(index_path), "--collection", "test", "--json", "show", chunk_id],
    )

    assert show_result.exit_code == 0, show_result.output
    show_payload = _json(show_result.output)

    assert show_payload["id"] == chunk_id
    assert "text" in show_payload
    assert "metadata" in show_payload
    assert show_payload["metadata"]["page"] >= 1
