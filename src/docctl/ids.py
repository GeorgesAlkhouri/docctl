"""Identifier generation utilities."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    """Convert free-form text into a stable lowercase slug.

    Args:
        value: Source text to normalize.

    Returns:
        A hyphen-delimited slug suitable for deterministic identifiers.
    """
    lowered = value.strip().lower()
    normalized = _NON_ALNUM_RE.sub("-", lowered)
    compact = normalized.strip("-")
    return compact or "document"


def file_sha256(path: Path) -> str:
    """Compute the SHA-256 digest for a file on disk.

    Args:
        path: Path to the file to hash.

    Returns:
        Hex-encoded SHA-256 digest.
    """
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def build_doc_id(source: str) -> str:
    """Build a deterministic document id from a source path.

    Args:
        source: Original source path string.

    Returns:
        Stable identifier composed of a slug and short hash suffix.
    """
    normalized = source.replace("\\", "/")
    digest = hashlib.sha1(normalized.encode("utf-8"), usedforsecurity=False).hexdigest()[:10]
    stem = Path(normalized).stem
    return f"{slugify(stem)}-{digest}"


def build_chunk_id(doc_id: str, page: int, chunk_index: int, text: str) -> str:
    """Build a deterministic chunk id for one chunk within a document.

    Args:
        doc_id: Parent document id.
        page: One-based PDF page number containing the chunk.
        chunk_index: Zero-based chunk offset within the page.
        text: Chunk text used to derive a collision-resistant suffix.

    Returns:
        Structured chunk identifier with page, index, and digest components.
    """
    digest = hashlib.sha1(text.encode("utf-8"), usedforsecurity=False).hexdigest()[:8]
    return f"{doc_id}:p{page:04d}:c{chunk_index:04d}:{digest}"
