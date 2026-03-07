"""Document extraction dispatcher for supported ingest formats."""

from __future__ import annotations

import re
from pathlib import Path

from docx import Document as DocxDocument

from .errors import DocumentReadError, EmptyExtractedTextError, InputPathNotFoundError
from .models import TextUnit
from .pdf_extract import extract_pdf_units
from .text_sanitize import sanitize_text

SUPPORTED_INGEST_EXTENSIONS: frozenset[str] = frozenset({".pdf", ".docx", ".txt", ".md"})
_PARAGRAPH_BREAK_RE = re.compile(r"\n{2,}")


def is_supported_ingest_file(path: Path) -> bool:
    """Return whether a path has an extension supported by ingest.

    Args:
        path: Candidate path to inspect.

    Returns:
        `True` when the file extension is supported by ingest.
    """
    return path.suffix.lower() in SUPPORTED_INGEST_EXTENSIONS


def _split_paragraph_units(text: str) -> list[TextUnit]:
    """Split normalized plaintext into non-empty paragraph-style text units."""
    normalized = sanitize_text(text).replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []
    paragraphs = [segment.strip() for segment in _PARAGRAPH_BREAK_RE.split(normalized)]
    return [
        TextUnit(text=paragraph)
        for paragraph in paragraphs
        if paragraph
    ]


def _extract_docx_units(path: Path) -> list[TextUnit]:
    """Extract paragraph text units from a DOCX file."""
    try:
        doc = DocxDocument(str(path))
    except Exception as error:  # noqa: BLE001
        raise DocumentReadError(f"failed to read DOCX: {path} ({error})") from error

    units = [
        TextUnit(text=text)
        for text in (
            sanitize_text(paragraph.text).strip()
            for paragraph in doc.paragraphs
            if paragraph.text.strip()
        )
        if text
    ]
    if not units:
        raise EmptyExtractedTextError(f"no extractable text found in document: {path}")
    return units


def _extract_text_units(path: Path) -> list[TextUnit]:
    """Extract paragraph text units from UTF-8 plaintext inputs."""
    try:
        content = path.read_text(encoding="utf-8-sig")
    except Exception as error:  # noqa: BLE001
        raise DocumentReadError(f"failed to read text file: {path} ({error})") from error

    units = _split_paragraph_units(content)
    if not units:
        raise EmptyExtractedTextError(f"no extractable text found in document: {path}")
    return units


def extract_document_units(path: Path) -> list[TextUnit]:
    """Extract normalized text units from a supported document file.

    Args:
        path: Supported document path.

    Returns:
        Ordered non-empty text units.

    Raises:
        InputPathNotFoundError: If the file extension is unsupported.
        DocumentReadError: If the file cannot be decoded or parsed.
        EmptyExtractedTextError: If parsing succeeds but no text units are available.
    """
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf_units(path)
    if suffix == ".docx":
        return _extract_docx_units(path)
    if suffix in {".txt", ".md"}:
        return _extract_text_units(path)
    raise InputPathNotFoundError(f"unsupported ingest file type: {path}")
