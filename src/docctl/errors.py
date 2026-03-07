"""Custom exceptions and exit code mappings for docctl."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class DocctlError(Exception):
    """Base error that carries a stable process exit code."""

    message: str
    exit_code: int

    def __str__(self) -> str:
        return self.message


class InputPathNotFoundError(DocctlError):
    """Raise when an ingest input path cannot be found or is invalid."""

    def __init__(self, message: str) -> None:
        super().__init__(message=message, exit_code=10)


class DocumentReadError(DocctlError):
    """Raise when document bytes cannot be decoded into extractable text units."""

    def __init__(self, message: str) -> None:
        super().__init__(message=message, exit_code=11)


class EmptyExtractedTextError(DocctlError):
    """Raise when extraction succeeds structurally but returns no usable text."""

    def __init__(self, message: str) -> None:
        super().__init__(message=message, exit_code=12)


class IndexNotInitializedError(DocctlError):
    """Raise when expected index artifacts are missing from disk."""

    def __init__(self, message: str) -> None:
        super().__init__(message=message, exit_code=20)


class WriteApprovalRequiredError(DocctlError):
    """Raise when write operations require explicit user approval."""

    def __init__(self, message: str) -> None:
        super().__init__(message=message, exit_code=21)


class EmptyIndexSearchError(DocctlError):
    """Raise when search is requested against an empty collection."""

    def __init__(self, message: str) -> None:
        super().__init__(message=message, exit_code=30)


class ChunkNotFoundError(DocctlError):
    """Raise when a requested chunk id is not present in storage."""

    def __init__(self, message: str) -> None:
        super().__init__(message=message, exit_code=31)


class EmbeddingConfigError(DocctlError):
    """Raise when embedding configuration or model readiness fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message=message, exit_code=40)


class InternalDocctlError(DocctlError):
    """Raise for unexpected internal failures mapped to a stable exit code."""

    def __init__(self, message: str) -> None:
        super().__init__(message=message, exit_code=50)
