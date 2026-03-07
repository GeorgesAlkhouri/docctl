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
    assert payload["units_indexed"] == 2
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


def test_ingest_directory_recursive_mixed_formats_json(
    runner, make_pdf, make_docx, patch_fake_embeddings, tmp_path: Path
) -> None:
    root = tmp_path / "docs"
    make_pdf(root / "a.pdf", ["PDF page one.", "PDF page two."])
    make_docx(root / "b.docx", ["DOCX paragraph one.", "DOCX paragraph two."])
    (root / "nested").mkdir(parents=True, exist_ok=True)
    (root / "nested" / "c.txt").write_text(
        "TXT paragraph one.\n\nTXT paragraph two.",
        encoding="utf-8",
    )
    (root / "nested" / "d.md").write_text(
        "# Heading\n\nMarkdown paragraph one.\n\nMarkdown paragraph two.",
        encoding="utf-8",
    )
    (root / "skip.csv").write_text("a,b\n1,2\n", encoding="utf-8")
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
    assert payload["files_discovered"] == 4
    assert payload["files_indexed"] == 4
    assert payload["units_indexed"] >= 8
    assert payload["chunks_indexed"] >= 4
