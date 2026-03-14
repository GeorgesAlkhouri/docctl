"""Cross-encoder reranker factory used by search and session workflows."""

from __future__ import annotations

import logging

from sentence_transformers import CrossEncoder
from transformers.utils import logging as transformers_logging

from .errors import EmbeddingConfigError


class LocalCrossEncoderReranker:
    """Local reranker backed by a sentence-transformers cross encoder."""

    def __init__(self, *, model_name: str, allow_download: bool, verbose: bool) -> None:
        self._verbose = verbose
        if not verbose:
            transformers_logging.set_verbosity_error()
            logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
            logging.getLogger("transformers").setLevel(logging.ERROR)
        try:
            self._model = CrossEncoder(
                model_name,
                local_files_only=not allow_download,
                trust_remote_code=True,
            )
        except Exception as error:  # noqa: BLE001
            raise EmbeddingConfigError(
                "failed to load reranker model "
                f"'{model_name}'. Use --allow-model-download to fetch missing model artifacts."
            ) from error

    def score(self, *, query: str, texts: list[str]) -> list[float]:
        """Score query/text pairs and return one score per candidate text.

        Args:
            query: User query used for all candidate pairs.
            texts: Candidate texts returned from vector retrieval.

        Returns:
            Reranker scores aligned with `texts` order.
        """
        if not texts:
            return []

        pairs = [(query, text) for text in texts]
        raw = self._model.predict(
            pairs,
            convert_to_numpy=True,
            show_progress_bar=self._verbose,
        )
        values = raw.tolist() if hasattr(raw, "tolist") else raw

        if not isinstance(values, list):
            values = [values]

        scores: list[float] = []
        for value in values:
            if isinstance(value, list):
                scores.append(float(value[-1]) if value else 0.0)
                continue
            scores.append(float(value))
        return scores


def create_reranker(
    *,
    model_name: str,
    allow_download: bool,
    verbose: bool = False,
) -> LocalCrossEncoderReranker:
    """Create the reranker used for optional second-stage search ranking.

    Args:
        model_name: Cross-encoder model identifier.
        allow_download: Whether missing model assets may be downloaded.
        verbose: Whether verbose diagnostics are enabled.

    Returns:
        Reranker instance used to score candidate chunks for a query.
    """
    return LocalCrossEncoderReranker(
        model_name=model_name,
        allow_download=allow_download,
        verbose=verbose,
    )
