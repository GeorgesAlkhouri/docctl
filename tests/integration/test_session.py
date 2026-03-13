from __future__ import annotations

import json
from pathlib import Path

from docctl.cli import app


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


def test_session_reuses_embedding_model_for_multiple_searches(
    runner, make_pdf, monkeypatch, tmp_path: Path
) -> None:
    pdf_path = make_pdf(
        tmp_path / "doc.pdf",
        ["Vehicle diagnostics and retrieval text.", "Another diagnostics paragraph."],
    )
    index_path = tmp_path / "index"
    create_calls = {"count": 0}

    def counting_factory(
        model_name: str, allow_download: bool, verbose: bool = False
    ) -> _FakeEmbeddingFunction:
        _ = (model_name, allow_download, verbose)
        create_calls["count"] += 1
        return _FakeEmbeddingFunction()

    monkeypatch.setattr("docctl.services.create_embedding_function", counting_factory)

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
    assert create_calls["count"] == 1

    request_lines = "\n".join(
        [
            json.dumps({"id": "q1", "op": "search", "query": "vehicle", "top_k": 3}),
            json.dumps({"id": "q2", "op": "search", "query": "diagnostics", "top_k": 3}),
            json.dumps({"id": "q3", "op": "search", "query": "paragraph", "top_k": 3}),
        ]
    )
    request_lines = f"{request_lines}\n"

    session_result = runner.invoke(
        app,
        ["--index-path", str(index_path), "--collection", "test", "session"],
        input=request_lines,
    )
    assert session_result.exit_code == 0, session_result.output

    responses = [json.loads(line) for line in session_result.output.splitlines() if line.strip()]
    assert [response["id"] for response in responses] == ["q1", "q2", "q3"]
    assert all(response["ok"] is True for response in responses)

    # One for ingest + one for all session search requests.
    assert create_calls["count"] == 2


def test_session_search_supports_title_filter(
    runner, make_pdf, patch_fake_embeddings, tmp_path: Path
) -> None:
    alpha_pdf = make_pdf(
        tmp_path / "alpha-manual.pdf",
        ["Shared diagnostics retrieval phrase for alpha."],
    )
    beta_pdf = make_pdf(
        tmp_path / "beta-manual.pdf",
        ["Shared diagnostics retrieval phrase for beta."],
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

    request_lines = json.dumps(
        {
            "id": "q1",
            "op": "search",
            "query": "shared diagnostics retrieval",
            "top_k": 10,
            "title": "alpha-manual",
        }
    )
    session_result = runner.invoke(
        app,
        ["--index-path", str(index_path), "--collection", "test", "session"],
        input=f"{request_lines}\n",
    )
    assert session_result.exit_code == 0, session_result.output

    responses = [json.loads(line) for line in session_result.output.splitlines() if line.strip()]
    assert len(responses) == 1
    assert responses[0]["id"] == "q1"
    assert responses[0]["ok"] is True
    hits = responses[0]["result"]["hits"]
    assert len(hits) >= 1
    assert all(hit["metadata"]["title"] == "alpha-manual" for hit in hits)


def test_session_search_rejects_non_string_title(runner, tmp_path: Path) -> None:
    index_path = tmp_path / "index"
    request_lines = json.dumps({"id": "q1", "op": "search", "query": "any query", "title": 123})

    session_result = runner.invoke(
        app,
        ["--index-path", str(index_path), "--collection", "test", "session"],
        input=f"{request_lines}\n",
    )
    assert session_result.exit_code == 0, session_result.output

    responses = [json.loads(line) for line in session_result.output.splitlines() if line.strip()]
    assert len(responses) == 1
    assert responses[0]["id"] == "q1"
    assert responses[0]["ok"] is False
    assert responses[0]["error"]["exit_code"] == 50
    assert responses[0]["error"]["message"] == "invalid session request field 'title'"


def test_session_catalog_operation(runner, make_pdf, patch_fake_embeddings, tmp_path: Path) -> None:
    pdf_path = make_pdf(
        tmp_path / "catalog-doc.pdf",
        ["Catalog check sentence one.", "Catalog check sentence two."],
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

    session_result = runner.invoke(
        app,
        ["--index-path", str(index_path), "--collection", "test", "session"],
        input='{"id":"q1","op":"catalog"}\n',
    )
    assert session_result.exit_code == 0, session_result.output

    responses = [json.loads(line) for line in session_result.output.splitlines() if line.strip()]
    assert len(responses) == 1
    assert responses[0]["id"] == "q1"
    assert responses[0]["ok"] is True

    result = responses[0]["result"]
    assert result["collection"] == "test"
    assert result["summary"]["document_count"] == 1
    assert result["summary"]["chunk_count"] >= 1
    assert result["summary"]["units_total"] == 2
    assert len(result["documents"]) == 1


def test_session_search_ignores_unknown_extra_fields(
    runner, make_pdf, patch_fake_embeddings, tmp_path: Path
) -> None:
    pdf_path = make_pdf(tmp_path / "doc.pdf", ["Session migration check text."])
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

    request_lines = json.dumps(
        {"id": "q1", "op": "search", "query": "migration", "ignored_field": 1, "top_k": 3}
    )
    session_result = runner.invoke(
        app,
        ["--index-path", str(index_path), "--collection", "test", "session"],
        input=f"{request_lines}\n",
    )
    assert session_result.exit_code == 0, session_result.output

    responses = [json.loads(line) for line in session_result.output.splitlines() if line.strip()]
    assert len(responses) == 1
    assert responses[0]["id"] == "q1"
    assert responses[0]["ok"] is True
    assert responses[0]["result"]["hits"]


def test_session_search_with_rerank_adds_fields(
    runner,
    make_pdf,
    patch_fake_embeddings,
    patch_fake_reranker,
    monkeypatch,
    tmp_path: Path,
) -> None:
    pdf_path = make_pdf(tmp_path / "doc.pdf", ["Session rerank check text."])
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
    query_top_k_values: list[int] = []

    def _fake_query(self, query, top_k, where=None):  # noqa: ANN001
        _ = (self, query, where)
        query_top_k_values.append(top_k)
        return {
            "ids": [["a", "b"]],
            "documents": [["short", "this is a longer passage"]],
            "metadatas": [
                [
                    {"doc_id": "d", "source": "s", "title": "ta"},
                    {"doc_id": "d", "source": "s", "title": "tb"},
                ]
            ],
            "distances": [[0.0, 0.1]],
        }

    monkeypatch.setattr("docctl.index_store.ChromaStore.query", _fake_query)

    request_line = json.dumps(
        {
            "id": "q1",
            "op": "search",
            "query": "anything",
            "top_k": 2,
            "rerank": True,
        }
    )
    session_result = runner.invoke(
        app,
        ["--index-path", str(index_path), "--collection", "test", "session"],
        input=f"{request_line}\n",
    )
    assert session_result.exit_code == 0, session_result.output
    responses = [json.loads(line) for line in session_result.output.splitlines() if line.strip()]
    assert len(responses) == 1
    assert responses[0]["ok"] is True
    hits = responses[0]["result"]["hits"]
    assert [hit["id"] for hit in hits] == ["b", "a"]
    assert all("vector_rank" in hit for hit in hits)
    assert all("rerank_score" in hit for hit in hits)
    assert query_top_k_values == [10]


def test_session_search_rejects_rerank_candidates_below_top_k(runner, tmp_path: Path) -> None:
    index_path = tmp_path / "index"
    request_lines = json.dumps(
        {
            "id": "q1",
            "op": "search",
            "query": "q",
            "top_k": 5,
            "rerank": True,
            "rerank_candidates": 4,
        }
    )

    session_result = runner.invoke(
        app,
        ["--index-path", str(index_path), "--collection", "test", "session"],
        input=f"{request_lines}\n",
    )
    assert session_result.exit_code == 0, session_result.output
    responses = [json.loads(line) for line in session_result.output.splitlines() if line.strip()]
    assert len(responses) == 1
    assert responses[0]["ok"] is False
    assert responses[0]["error"]["exit_code"] == 50
    assert responses[0]["error"]["message"] == "invalid session request field 'rerank_candidates'"
