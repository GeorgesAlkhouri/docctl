"""Manifest and catalog helpers for the document index."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .coerce import to_non_negative_int

_MANIFEST_FILENAME = "manifest.json"


def manifest_path(index_path: Path) -> Path:
    """Return the manifest path for an index directory.

    Args:
        index_path: Root index path.

    Returns:
        Path to `manifest.json` under the index directory.
    """
    return index_path / _MANIFEST_FILENAME


def load_manifest(index_path: Path) -> dict[str, Any]:
    """Load manifest content or return defaults when absent.

    Args:
        index_path: Root index path.

    Returns:
        Manifest payload with guaranteed `documents` mapping key.
    """
    path = manifest_path(index_path)
    if not path.exists():
        return {
            "schema_version": 1,
            "last_ingest_at": None,
            "documents": {},
        }

    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if "documents" not in payload:
        payload["documents"] = {}
    return payload


def write_manifest(index_path: Path, payload: dict[str, Any]) -> None:
    """Persist manifest payload with deterministic JSON formatting.

    Args:
        index_path: Root index path.
        payload: Manifest dictionary to write.
    """
    index_path.mkdir(parents=True, exist_ok=True)
    path = manifest_path(index_path)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def manifest_documents(manifest: dict[str, Any]) -> dict[str, Any]:
    """Return normalized manifest `documents` mapping.

    Args:
        manifest: Full manifest payload.

    Returns:
        Dictionary of document metadata keyed by `doc_id`.
    """
    documents = manifest.get("documents", {})
    if isinstance(documents, dict):
        return documents
    return {}


def catalog_documents(manifest_docs: dict[str, Any]) -> list[dict[str, Any]]:
    """Serialize manifest document records into catalog rows.

    Args:
        manifest_docs: Manifest document mapping.

    Returns:
        Sorted catalog-ready document rows.
    """
    documents: list[dict[str, Any]] = []
    for doc_id, raw_details in sorted(manifest_docs.items()):
        if not isinstance(raw_details, dict):
            continue
        units = to_non_negative_int(raw_details.get("units", 0))
        chunks = to_non_negative_int(raw_details.get("chunks", 0))
        documents.append(
            {
                "doc_id": str(doc_id),
                "source": str(raw_details.get("source", "")),
                "title": str(raw_details.get("title", "")),
                "units": units,
                "chunks": chunks,
                "last_ingest_at": raw_details.get("last_ingest_at"),
                "content_hash": str(raw_details.get("content_hash", "")),
            }
        )
    return documents
