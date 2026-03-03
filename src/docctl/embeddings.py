"""Embedding function factory for Chroma."""

from __future__ import annotations

import logging
from typing import cast

from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from sentence_transformers import SentenceTransformer
from transformers.utils import logging as transformers_logging

from .errors import EmbeddingConfigError


class LocalSentenceTransformerEmbedding(EmbeddingFunction[Documents]):
    """Chroma-compatible embedding function backed by sentence-transformers."""

    def __init__(self, *, model_name: str, allow_download: bool, verbose: bool) -> None:
        self._verbose = verbose
        if not verbose:
            transformers_logging.set_verbosity_error()
            logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
            logging.getLogger("transformers").setLevel(logging.ERROR)
        try:
            self._model = SentenceTransformer(
                model_name,
                local_files_only=not allow_download,
            )
        except Exception as error:  # noqa: BLE001
            raise EmbeddingConfigError(
                "failed to load embedding model "
                f"'{model_name}'. Use --allow-model-download to fetch missing model artifacts."
            ) from error

    def __call__(self, input: Documents) -> Embeddings:
        vectors = self._model.encode(
            list(input),
            normalize_embeddings=True,
            show_progress_bar=self._verbose,
        )
        return cast(Embeddings, vectors.tolist())


def create_embedding_function(
    *, model_name: str, allow_download: bool, verbose: bool = False
) -> EmbeddingFunction[Documents]:
    return LocalSentenceTransformerEmbedding(
        model_name=model_name,
        allow_download=allow_download,
        verbose=verbose,
    )
