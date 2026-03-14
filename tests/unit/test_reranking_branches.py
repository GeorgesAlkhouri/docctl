from __future__ import annotations

from typing import Any

import pytest

from docctl.errors import EmbeddingConfigError
from docctl.reranking import create_reranker


def test_create_reranker_builds_cross_encoder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class _FakeCrossEncoder:
        def __init__(self, model_name: str, **kwargs: Any) -> None:
            captured["model_name"] = model_name
            captured["init_kwargs"] = kwargs

        def predict(self, pairs: list[tuple[str, str]], **kwargs: Any) -> list[float]:
            captured["pairs"] = pairs
            captured["predict_kwargs"] = kwargs
            return [0.2 for _ in pairs]

    monkeypatch.setattr("docctl.reranking.CrossEncoder", _FakeCrossEncoder)
    reranker = create_reranker(
        model_name="r",
        allow_download=False,
        verbose=False,
    )
    scores = reranker.score(query="q", texts=["a", "b"])

    assert scores == [0.2, 0.2]
    assert captured["model_name"] == "r"
    assert captured["init_kwargs"]["local_files_only"] is True
    assert captured["init_kwargs"]["trust_remote_code"] is True
    assert captured["pairs"] == [("q", "a"), ("q", "b")]
    assert captured["predict_kwargs"]["convert_to_numpy"] is True
    assert captured["predict_kwargs"]["show_progress_bar"] is False


def test_create_reranker_raises_embedding_config_error_on_load_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _ExplodingCrossEncoder:
        def __init__(self, model_name: str, **kwargs: Any) -> None:
            _ = (model_name, kwargs)
            raise RuntimeError("load failed")

    monkeypatch.setattr("docctl.reranking.CrossEncoder", _ExplodingCrossEncoder)

    with pytest.raises(EmbeddingConfigError, match="failed to load reranker model"):
        create_reranker(model_name="broken", allow_download=False, verbose=False)


def test_reranker_score_returns_empty_for_empty_candidate_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeCrossEncoder:
        def __init__(self, model_name: str, **kwargs: Any) -> None:
            _ = (model_name, kwargs)

        def predict(self, pairs: list[tuple[str, str]], **kwargs: Any) -> list[float]:
            _ = (pairs, kwargs)
            raise AssertionError("predict should not be called for empty texts")

    monkeypatch.setattr("docctl.reranking.CrossEncoder", _FakeCrossEncoder)
    reranker = create_reranker(model_name="r", allow_download=False, verbose=False)

    assert reranker.score(query="q", texts=[]) == []


def test_reranker_score_handles_scalar_predict_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeCrossEncoder:
        def __init__(self, model_name: str, **kwargs: Any) -> None:
            _ = (model_name, kwargs)

        def predict(self, pairs: list[tuple[str, str]], **kwargs: Any) -> float:
            _ = (pairs, kwargs)
            return 0.7

    monkeypatch.setattr("docctl.reranking.CrossEncoder", _FakeCrossEncoder)
    reranker = create_reranker(model_name="r", allow_download=False, verbose=False)

    assert reranker.score(query="q", texts=["a"]) == [0.7]


def test_reranker_score_handles_nested_predict_output_lists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Values:
        def tolist(self) -> list[list[float]]:
            return [[], [0.25, 0.9]]

    class _FakeCrossEncoder:
        def __init__(self, model_name: str, **kwargs: Any) -> None:
            _ = (model_name, kwargs)

        def predict(self, pairs: list[tuple[str, str]], **kwargs: Any) -> _Values:
            _ = (pairs, kwargs)
            return _Values()

    monkeypatch.setattr("docctl.reranking.CrossEncoder", _FakeCrossEncoder)
    reranker = create_reranker(model_name="r", allow_download=False, verbose=False)

    assert reranker.score(query="q", texts=["a", "b"]) == [0.0, 0.9]
