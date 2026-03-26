from __future__ import annotations

from pathlib import Path

import chromadb

from docctl.cli import app


class _FakeEmbeddingFunction:
    @staticmethod
    def name() -> str:
        return "docctl-fake-embedding"

    @staticmethod
    def build_from_config(config: dict) -> "_FakeEmbeddingFunction":
        _ = config
        return _FakeEmbeddingFunction()

    @staticmethod
    def is_legacy() -> bool:
        return False

    @staticmethod
    def get_config() -> dict[str, str]:
        return {}

    @staticmethod
    def default_space() -> str:
        return "cosine"

    @staticmethod
    def supported_spaces() -> list[str]:
        return ["cosine", "l2", "ip"]

    def __call__(self, input: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in input]


def test_ingest_missing_path_exit_code_10(runner, tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.pdf"

    result = runner.invoke(app, ["--json", "ingest", str(missing_path)])

    assert result.exit_code == 10
    assert "input path does not exist" in result.output


def test_write_approval_required_exit_code_21(runner, make_pdf, tmp_path: Path) -> None:
    pdf_path = make_pdf(tmp_path / "doc.pdf", ["content"])

    result = runner.invoke(
        app,
        ["--json", "ingest", str(pdf_path)],
        env={"DOCCTL_REQUIRE_WRITE_APPROVAL": "1"},
    )

    assert result.exit_code == 21
    assert "write approval is required" in result.output


def test_search_on_empty_collection_exit_code_30(
    runner, patch_fake_embeddings, tmp_path: Path
) -> None:
    index_path = tmp_path / "index"
    chroma_path = index_path / "chroma"
    chroma_path.mkdir(parents=True, exist_ok=True)
    chromadb.PersistentClient(path=str(chroma_path)).get_or_create_collection(
        name="test",
        embedding_function=_FakeEmbeddingFunction(),
    )

    result = runner.invoke(
        app,
        [
            "--index-path",
            str(index_path),
            "--collection",
            "test",
            "--json",
            "search",
            "anything",
        ],
    )

    assert result.exit_code == 30
    assert "empty index" in result.output


def test_show_missing_chunk_exit_code_31(runner, tmp_path: Path) -> None:
    index_path = tmp_path / "index"
    chroma_path = index_path / "chroma"
    chroma_path.mkdir(parents=True, exist_ok=True)
    chromadb.PersistentClient(path=str(chroma_path)).get_or_create_collection(name="test")

    result = runner.invoke(
        app,
        [
            "--index-path",
            str(index_path),
            "--collection",
            "test",
            "--json",
            "show",
            "missing-id",
        ],
    )

    assert result.exit_code == 31
    assert "chunk not found" in result.output


def test_invalid_embedding_config_exit_code_40(runner, tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "--index-path",
            str(tmp_path / "index"),
            "--collection",
            "test",
            "--json",
            "search",
            "diagnostics",
        ],
        env={"DOCCTL_EMBEDDING_MODEL": "nonexistent-model-for-docctl-tests"},
    )

    assert result.exit_code == 40
    assert "failed to load embedding model" in result.output


def test_stats_on_uninitialized_index_exit_code_20_has_actionable_message(
    runner, tmp_path: Path
) -> None:
    result = runner.invoke(
        app,
        [
            "--index-path",
            str(tmp_path / "fresh-index"),
            "--collection",
            "test",
            "--json",
            "stats",
        ],
    )

    output = result.output.lower()

    assert result.exit_code == 20
    assert "index is not initialized" in output
    assert "run `docctl ingest <path>` first" in output
    assert "--index-path" in output


def test_export_invalid_archive_extension_exit_code_13(runner, tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "--index-path",
            str(tmp_path / "index"),
            "--collection",
            "test",
            "--json",
            "export",
            str(tmp_path / "snapshot.tar"),
        ],
    )

    assert result.exit_code == 13
    assert "must end with .zip" in result.output


def test_import_conflict_without_replace_exit_code_22(
    runner, make_pdf, patch_fake_embeddings, tmp_path: Path
) -> None:
    pdf_path = make_pdf(tmp_path / "doc.pdf", ["Import conflict check sentence."])
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

    result = runner.invoke(
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

    assert result.exit_code == 22
    assert "--replace" in result.output
