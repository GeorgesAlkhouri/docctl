from __future__ import annotations

import json
from pathlib import Path

from docctl.cli import app


def _load_json(output: str) -> dict:
    return json.loads(output.strip())


def test_ingest_single_pdf_json(runner, make_pdf, patch_fake_embeddings, tmp_path: Path) -> None:
    pdf_path = make_pdf(
        tmp_path / "single.pdf",
        [
            "Header\nThis is a sentence. This is another sentence.\nFooter",
            "Header\nA second page with retrieval text.\nFooter",
        ],
    )
    index_path = tmp_path / "index"

    result = runner.invoke(
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

    assert result.exit_code == 0, result.output
    payload = _load_json(result.output)
    assert payload["collection"] == "test"
    assert payload["files_discovered"] == 1
    assert payload["files_indexed"] == 1
    assert payload["pages_indexed"] == 2
    assert payload["chunks_indexed"] >= 1
    assert payload["errors"] == []


def test_ingest_directory_recursive_json(
    runner, make_pdf, patch_fake_embeddings, tmp_path: Path
) -> None:
    root = tmp_path / "docs"
    make_pdf(root / "a.pdf", ["Page one sentence. Page one sentence two."])
    make_pdf(root / "nested" / "b.pdf", ["Another document sentence."])
    index_path = tmp_path / "index"

    result = runner.invoke(
        app,
        [
            "--index-path",
            str(index_path),
            "--collection",
            "test",
            "--json",
            "ingest",
            str(root),
            "--recursive",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = _load_json(result.output)
    assert payload["files_discovered"] == 2
    assert payload["files_indexed"] == 2
    assert payload["chunks_indexed"] >= 2
