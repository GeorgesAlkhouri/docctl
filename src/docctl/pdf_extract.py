"""PDF extraction utilities."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pdfplumber
from pypdf import PdfReader

from .errors import EmptyExtractedTextError, PdfReadError
from .text_sanitize import sanitize_text

_MAX_REPEATING_LINE_LEN = 120
_MULTIPLE_NEWLINES_RE = re.compile(r"\n{3,}")


@dataclass(slots=True)
class PageText:
    """Represent normalized text extracted from one PDF page."""

    page: int
    text: str


def _normalize_page_text(text: str) -> str:
    normalized = sanitize_text(text).replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in normalized.split("\n")]
    joined = "\n".join(lines)
    joined = _MULTIPLE_NEWLINES_RE.sub("\n\n", joined)
    return joined.strip()


def _strip_repeating_headers_and_footers(pages: list[PageText]) -> list[PageText]:
    if len(pages) < 2:
        return pages

    first_lines: Counter[str] = Counter()
    last_lines: Counter[str] = Counter()
    split_lines: list[list[str]] = []

    for page in pages:
        lines = [line.strip() for line in page.text.splitlines() if line.strip()]
        split_lines.append(lines)
        if lines and len(lines[0]) <= _MAX_REPEATING_LINE_LEN:
            first_lines[lines[0]] += 1
        if lines and len(lines[-1]) <= _MAX_REPEATING_LINE_LEN:
            last_lines[lines[-1]] += 1

    header_candidates = {line for line, count in first_lines.items() if count >= 2}
    footer_candidates = {line for line, count in last_lines.items() if count >= 2}

    stripped_pages: list[PageText] = []
    for page, lines in zip(pages, split_lines, strict=True):
        if lines and lines[0] in header_candidates:
            lines = lines[1:]
        if lines and lines[-1] in footer_candidates:
            lines = lines[:-1]
        stripped_pages.append(PageText(page=page.page, text="\n".join(lines).strip()))

    return stripped_pages


def _extract_with_pdfplumber(path: Path) -> list[PageText]:
    try:
        with pdfplumber.open(path) as pdf:
            return [
                PageText(page=index, text=(page.extract_text() or ""))
                for index, page in enumerate(pdf.pages, start=1)
            ]
    except Exception as error:  # noqa: BLE001
        raise PdfReadError(f"failed to read PDF with pdfplumber: {path} ({error})") from error


def _extract_with_pypdf(path: Path) -> list[PageText]:
    try:
        reader = PdfReader(str(path))
        return [
            PageText(page=index, text=(page.extract_text() or ""))
            for index, page in enumerate(reader.pages, start=1)
        ]
    except Exception as error:  # noqa: BLE001
        raise PdfReadError(f"failed to read PDF with pypdf fallback: {path} ({error})") from error


def extract_pdf_pages(path: Path) -> list[PageText]:
    """Extract non-empty page text from a PDF with robust fallbacks."""
    extracted: list[PageText]

    try:
        extracted = _extract_with_pdfplumber(path)
    except PdfReadError:
        extracted = _extract_with_pypdf(path)

    normalized = [
        PageText(page=page.page, text=_normalize_page_text(page.text)) for page in extracted
    ]
    normalized = _strip_repeating_headers_and_footers(normalized)
    non_empty_pages = [page for page in normalized if page.text.strip()]

    if not non_empty_pages:
        raise EmptyExtractedTextError(f"no extractable text found in PDF: {path}")

    return non_empty_pages
