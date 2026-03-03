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
    def __init__(self, message: str) -> None:
        super().__init__(message=message, exit_code=10)


class PdfReadError(DocctlError):
    def __init__(self, message: str) -> None:
        super().__init__(message=message, exit_code=11)


class EmptyExtractedTextError(DocctlError):
    def __init__(self, message: str) -> None:
        super().__init__(message=message, exit_code=12)


class IndexNotInitializedError(DocctlError):
    def __init__(self, message: str) -> None:
        super().__init__(message=message, exit_code=20)


class WriteApprovalRequiredError(DocctlError):
    def __init__(self, message: str) -> None:
        super().__init__(message=message, exit_code=21)


class EmptyIndexSearchError(DocctlError):
    def __init__(self, message: str) -> None:
        super().__init__(message=message, exit_code=30)


class ChunkNotFoundError(DocctlError):
    def __init__(self, message: str) -> None:
        super().__init__(message=message, exit_code=31)


class EmbeddingConfigError(DocctlError):
    def __init__(self, message: str) -> None:
        super().__init__(message=message, exit_code=40)


class InternalDocctlError(DocctlError):
    def __init__(self, message: str) -> None:
        super().__init__(message=message, exit_code=50)
