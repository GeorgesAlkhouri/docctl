"""Embedding function factory for Chroma."""

from __future__ import annotations

from typing import cast

from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from sentence_transformers import SentenceTransformer

from .errors import EmbeddingConfigError


class LocalSentenceTransformerEmbedding(EmbeddingFunction[Documents]):
    """Chroma-compatible embedding function backed by sentence-transformers."""

    def __init__(self, *, model_name: str, allow_download: bool) -> None:
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
        vectors = self._model.encode(list(input), normalize_embeddings=True)
        return cast(Embeddings, vectors.tolist())


def create_embedding_function(*, model_name: str, allow_download: bool) -> EmbeddingFunction[Documents]:
    return LocalSentenceTransformerEmbedding(model_name=model_name, allow_download=allow_download)
