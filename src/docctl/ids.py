"""Identifier generation utilities."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    lowered = value.strip().lower()
    normalized = _NON_ALNUM_RE.sub("-", lowered)
    compact = normalized.strip("-")
    return compact or "document"


def file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def build_doc_id(source: str) -> str:
    normalized = source.replace("\\", "/")
    digest = hashlib.sha1(normalized.encode("utf-8"), usedforsecurity=False).hexdigest()[:10]
    stem = Path(normalized).stem
    return f"{slugify(stem)}-{digest}"


def build_chunk_id(doc_id: str, page: int, chunk_index: int, text: str) -> str:
    digest = hashlib.sha1(text.encode("utf-8"), usedforsecurity=False).hexdigest()[:8]
    return f"{doc_id}:p{page:04d}:c{chunk_index:04d}:{digest}"
