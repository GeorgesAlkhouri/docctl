"""PDF extraction utilities."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pdfplumber
from pypdf import PdfReader

from .errors import DocumentReadError, EmptyExtractedTextError
from .models import TextUnit
from .text_sanitize import sanitize_text

_MAX_REPEATING_LINE_LEN = 120
_MULTIPLE_NEWLINES_RE = re.compile(r"\n{3,}")


def _normalize_page_text(text: str) -> str:
    normalized = sanitize_text(text).replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in normalized.split("\n")]
    joined = "\n".join(lines)
    joined = _MULTIPLE_NEWLINES_RE.sub("\n\n", joined)
    return joined.strip()


def _strip_repeating_headers_and_footers(units: list[TextUnit]) -> list[TextUnit]:
    """Remove common repeated page header/footer lines from PDF units."""
    if len(units) < 2:
        return units

    first_lines: Counter[str] = Counter()
    last_lines: Counter[str] = Counter()
    split_lines: list[list[str]] = []

    for unit in units:
        lines = [line.strip() for line in unit.text.splitlines() if line.strip()]
        split_lines.append(lines)
        if lines and len(lines[0]) <= _MAX_REPEATING_LINE_LEN:
            first_lines[lines[0]] += 1
        if lines and len(lines[-1]) <= _MAX_REPEATING_LINE_LEN:
            last_lines[lines[-1]] += 1

    header_candidates = {line for line, count in first_lines.items() if count >= 2}
    footer_candidates = {line for line, count in last_lines.items() if count >= 2}

    stripped_units: list[TextUnit] = []
    for _unit, lines in zip(units, split_lines, strict=True):
        if lines and lines[0] in header_candidates:
            lines = lines[1:]
        if lines and lines[-1] in footer_candidates:
            lines = lines[:-1]
        stripped_units.append(TextUnit(text="\n".join(lines).strip()))

    return stripped_units


def _extract_with_pdfplumber(path: Path) -> list[TextUnit]:
    """Extract raw text from PDF pages with pdfplumber."""
    try:
        with pdfplumber.open(path) as pdf:
            return [
                TextUnit(text=(page.extract_text() or ""))
                for index, page in enumerate(pdf.pages, start=1)
            ]
    except Exception as error:  # noqa: BLE001
        raise DocumentReadError(f"failed to read PDF with pdfplumber: {path} ({error})") from error


def _extract_with_pypdf(path: Path) -> list[TextUnit]:
    """Extract raw text from PDF pages with pypdf."""
    try:
        reader = PdfReader(str(path))
        return [
            TextUnit(text=(page.extract_text() or ""))
            for index, page in enumerate(reader.pages, start=1)
        ]
    except Exception as error:  # noqa: BLE001
        raise DocumentReadError(
            f"failed to read PDF with pypdf fallback: {path} ({error})"
        ) from error


def extract_pdf_units(path: Path) -> list[TextUnit]:
    """Extract non-empty page text units from a PDF with robust fallbacks."""
    extracted: list[TextUnit]

    try:
        extracted = _extract_with_pdfplumber(path)
    except DocumentReadError:
        extracted = _extract_with_pypdf(path)

    normalized = [TextUnit(text=_normalize_page_text(unit.text)) for unit in extracted]
    normalized = _strip_repeating_headers_and_footers(normalized)
    non_empty_units = [unit for unit in normalized if unit.text.strip()]

    if not non_empty_units:
        raise EmptyExtractedTextError(f"no extractable text found in PDF: {path}")

    return non_empty_units
