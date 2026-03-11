"""Configuration handling for the docctl CLI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DEFAULT_INDEX_PATH = Path(".docctl")
DEFAULT_COLLECTION = "default"
DEFAULT_EMBEDDING_MODEL = "jinaai/jina-embeddings-v5-text-small-retrieval"
DEFAULT_RERANK_MODEL = "BAAI/bge-reranker-v2-m3"
ENV_REQUIRE_WRITE_APPROVAL = "DOCCTL_REQUIRE_WRITE_APPROVAL"
ENV_EMBEDDING_MODEL = "DOCCTL_EMBEDDING_MODEL"
ENV_RERANK_MODEL = "DOCCTL_RERANK_MODEL"


@dataclass(slots=True)
class CliConfig:
    """Capture resolved CLI runtime configuration values."""

    index_path: Path = DEFAULT_INDEX_PATH
    collection: str = DEFAULT_COLLECTION
    json_output: bool = False
    verbose: bool = False
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    rerank_model: str = DEFAULT_RERANK_MODEL
    require_write_approval: bool = False
