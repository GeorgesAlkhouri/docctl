"""Configuration handling for the docctl CLI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DEFAULT_INDEX_PATH = Path(".docctl")
DEFAULT_COLLECTION = "default"
DEFAULT_EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
ENV_REQUIRE_WRITE_APPROVAL = "DOCCTL_REQUIRE_WRITE_APPROVAL"
ENV_EMBEDDING_MODEL = "DOCCTL_EMBEDDING_MODEL"


@dataclass(slots=True)
class CliConfig:
    """Capture resolved CLI runtime configuration values."""

    index_path: Path = DEFAULT_INDEX_PATH
    collection: str = DEFAULT_COLLECTION
    json_output: bool = False
    verbose: bool = False
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    require_write_approval: bool = False
