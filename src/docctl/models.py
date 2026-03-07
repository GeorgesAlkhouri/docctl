"""Data models shared across services and CLI output."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True, frozen=True)
class TextUnit:
    """Represent one extracted text unit."""

    text: str


@dataclass(slots=True)
class ChunkMetadata:
    """Describe source metadata stored alongside each indexed chunk."""

    doc_id: str
    source: str
    title: str
    section: str | None = None


@dataclass(slots=True)
class SearchHit:
    """Represent one ranked search result returned from vector lookup."""

    rank: int
    id: str
    text: str
    distance: float
    score: float
    metadata: ChunkMetadata


@dataclass(slots=True)
class ChunkRecord:
    """Store a chunk payload and its normalized metadata."""

    id: str
    text: str
    metadata: ChunkMetadata


@dataclass(slots=True)
class DoctorCheck:
    """Capture one health-check outcome emitted by `docctl doctor`."""

    name: str
    ok: bool
    message: str


@dataclass(slots=True)
class DoctorReport:
    """Aggregate all doctor checks, warnings, and errors for CLI output."""

    ok: bool
    checks: list[DoctorCheck]
    warnings: list[str]
    errors: list[str]


JsonDict = dict[str, Any]
