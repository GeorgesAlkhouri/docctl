from __future__ import annotations

from typing import Any

import pytest

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
