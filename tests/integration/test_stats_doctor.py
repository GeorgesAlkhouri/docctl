from __future__ import annotations

import json
from pathlib import Path

from docctl.cli import app


def _json(output: str) -> dict:
    return json.loads(output.strip())


def test_stats_json_output(runner, make_pdf, patch_fake_embeddings, tmp_path: Path) -> None:
    pdf_path = make_pdf(tmp_path / "stats.pdf", ["One stats sentence. Another stats sentence."])
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

    stats_result = runner.invoke(
        app,
        ["--index-path", str(index_path), "--collection", "test", "--json", "stats"],
    )

    assert stats_result.exit_code == 0, stats_result.output
    payload = _json(stats_result.output)

    assert payload["collection"] == "test"
    assert payload["document_count"] == 1
    assert payload["chunk_count"] >= 1
    assert "embedding_model" in payload
    assert "last_ingest_at" in payload


def test_doctor_json_output(runner, make_pdf, patch_fake_embeddings, tmp_path: Path) -> None:
    pdf_path = make_pdf(tmp_path / "doctor.pdf", ["Doctor check sample text for query."])
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

    doctor_result = runner.invoke(
        app,
        ["--index-path", str(index_path), "--collection", "test", "--json", "doctor"],
    )

    assert doctor_result.exit_code == 0, doctor_result.output
    payload = _json(doctor_result.output)
    assert payload["ok"] is True
    assert payload["checks"]
    assert payload["errors"] == []
