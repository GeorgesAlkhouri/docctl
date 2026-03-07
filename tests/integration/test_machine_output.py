from __future__ import annotations

import json
import sys
from pathlib import Path

from docctl.cli import app
from docctl.models import ChunkMetadata, ChunkRecord


class _FakeEmbeddingFunction:
    @staticmethod
    def _normalize_text(value: object) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, (list, tuple)):
            return " ".join(str(item) for item in value)
        return str(value)

    def _vectorize(self, value: object) -> list[float]:
        clean = self._normalize_text(value)
        total = sum(ord(char) for char in clean)
        length = len(clean)
        vowels = sum(1 for char in clean.lower() if char in "aeiouäöü")
        return [
            float(total % 997) / 997.0,
            float(length % 389) / 389.0,
            float(vowels % 211) / 211.0,
        ]

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

    def embed_query(self, input: object) -> list[list[float]]:
        if isinstance(input, (list, tuple)):
            return [self._vectorize(item) for item in input]
        return [self._vectorize(input)]

    def embed_documents(self, input: list[object]) -> list[list[float]]:
        return self(input)

    def __call__(self, input: list[object]) -> list[list[float]]:
        return [self._vectorize(item) for item in input]


def _json(output: str) -> dict:
    return json.loads(output.strip())


def test_json_search_ignores_noisy_embedding_output(
    runner, make_pdf, monkeypatch, tmp_path: Path
) -> None:
    pdf_path = make_pdf(tmp_path / "doc.pdf", ["A clean sentence for retrieval."])
    index_path = tmp_path / "index"

    def noisy_factory(
        model_name: str, allow_download: bool, verbose: bool = False
    ) -> _FakeEmbeddingFunction:
        _ = (model_name, allow_download, verbose)
        print("Loading weights ...")
        print("progress: 10%", file=sys.stderr)
        return _FakeEmbeddingFunction()

    monkeypatch.setattr("docctl.services.create_embedding_function", noisy_factory)

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
    ingest_payload = _json(ingest_result.output)
    assert ingest_payload["files_indexed"] == 1

    search_result = runner.invoke(
        app,
        [
            "--index-path",
            str(index_path),
            "--collection",
            "test",
            "--json",
            "search",
            "retrieval",
        ],
    )
    assert search_result.exit_code == 0, search_result.output
    search_payload = _json(search_result.output)
    assert "hits" in search_payload


def test_search_json_output_sanitizes_control_chars(
    runner, make_pdf, patch_fake_embeddings, monkeypatch, tmp_path: Path
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
            "ids": [["legacy"]],
            "documents": [["A\x00B\x1fC"]],
            "metadatas": [
                [
                    {
                        "doc_id": "d",
                        "source": "s",
                        "title": "t",
                        "section": None,
                    }
                ]
            ],
            "distances": [[0.0]],
        },
    )

    result = runner.invoke(
        app,
        ["--index-path", str(index_path), "--collection", "test", "--json", "search", "anything"],
    )

    assert result.exit_code == 0, result.output
    payload = _json(result.output)
    assert payload["hits"][0]["text"] == "ABC"


def test_show_json_output_sanitizes_control_chars(
    runner, make_pdf, patch_fake_embeddings, monkeypatch, tmp_path: Path
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

    monkeypatch.setattr(
        "docctl.index_store.ChromaStore.get_chunk",
        lambda self, chunk_id: ChunkRecord(
            id=chunk_id,
            text="X\x00Y\x1fZ",
            metadata=ChunkMetadata(
                doc_id="d",
                source="s",
                title="t",
                section=None,
            ),
        ),
    )

    result = runner.invoke(
        app,
        [
            "--index-path",
            str(index_path),
            "--collection",
            "test",
            "--json",
            "show",
            "legacy-chunk-id",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = _json(result.output)
    assert payload["text"] == "XYZ"
