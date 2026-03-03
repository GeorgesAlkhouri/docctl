"""Data models shared across services and CLI output."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ChunkMetadata:
    doc_id: str
    source: str
    title: str
    page: int
    section: str | None = None


@dataclass(slots=True)
class SearchHit:
    rank: int
    id: str
    text: str
    distance: float
    score: float
    metadata: ChunkMetadata


@dataclass(slots=True)
class ChunkRecord:
    id: str
    text: str
    metadata: ChunkMetadata


@dataclass(slots=True)
class DoctorCheck:
    name: str
    ok: bool
    message: str


@dataclass(slots=True)
class DoctorReport:
    ok: bool
    checks: list[DoctorCheck]
    warnings: list[str]
    errors: list[str]


JsonDict = dict[str, Any]
