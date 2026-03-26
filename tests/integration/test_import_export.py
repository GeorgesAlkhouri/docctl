from __future__ import annotations

import json
from pathlib import Path

from docctl.cli import app


def _json(output: str) -> dict:
    return json.loads(output.strip())


def test_export_import_round_trip_json(
    runner, make_pdf, patch_fake_embeddings, tmp_path: Path
) -> None:
    pdf_path = make_pdf(
        tmp_path / "docs" / "roundtrip.pdf",
        ["Round-trip retrieval sentence one.", "Round-trip retrieval sentence two."],
    )
    source_index = tmp_path / "source-index"
    imported_index = tmp_path / "imported-index"
    archive_path = tmp_path / "snapshots" / "snapshot.zip"

    ingest_result = runner.invoke(
        app,
        [
            "--index-path",
            str(source_index),
            "--collection",
            "test",
            "--json",
            "ingest",
            str(pdf_path),
        ],
    )
    assert ingest_result.exit_code == 0, ingest_result.output

    export_result = runner.invoke(
        app,
        [
            "--index-path",
            str(source_index),
            "--collection",
            "test",
            "--json",
            "export",
            str(archive_path),
        ],
    )
    assert export_result.exit_code == 0, export_result.output
    export_payload = _json(export_result.output)
    assert export_payload["files_exported"] >= 2
    assert archive_path.exists()

    import_result = runner.invoke(
        app,
        [
            "--index-path",
            str(imported_index),
            "--collection",
            "test",
            "--json",
            "import",
            str(archive_path),
            "--approve-write",
        ],
    )
    assert import_result.exit_code == 0, import_result.output
    import_payload = _json(import_result.output)
    assert import_payload["files_imported"] >= 2

    search_result = runner.invoke(
        app,
        [
            "--index-path",
            str(imported_index),
            "--collection",
            "test",
            "--json",
            "search",
            "round-trip retrieval",
        ],
    )
    assert search_result.exit_code == 0, search_result.output
    search_payload = _json(search_result.output)
    assert search_payload["hits"]


def test_import_requires_replace_when_target_exists(
    runner, make_pdf, patch_fake_embeddings, tmp_path: Path
) -> None:
    pdf_path = make_pdf(tmp_path / "docs" / "doc.pdf", ["Import replace safety check sentence."])
    source_index = tmp_path / "source-index"
    target_index = tmp_path / "target-index"
    archive_path = tmp_path / "snapshot.zip"

    ingest_result = runner.invoke(
        app,
        [
            "--index-path",
            str(source_index),
            "--collection",
            "test",
            "--json",
            "ingest",
            str(pdf_path),
        ],
    )
    assert ingest_result.exit_code == 0, ingest_result.output

    export_result = runner.invoke(
        app,
        [
            "--index-path",
            str(source_index),
            "--collection",
            "test",
            "--json",
            "export",
            str(archive_path),
        ],
    )
    assert export_result.exit_code == 0, export_result.output

    target_index.mkdir(parents=True, exist_ok=True)
    (target_index / "placeholder.txt").write_text("existing", encoding="utf-8")
    import_result = runner.invoke(
        app,
        [
            "--index-path",
            str(target_index),
            "--collection",
            "test",
            "--json",
            "import",
            str(archive_path),
            "--approve-write",
        ],
    )

    assert import_result.exit_code == 22
    assert "--replace" in import_result.output
