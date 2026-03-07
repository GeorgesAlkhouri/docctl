from __future__ import annotations

from pathlib import Path

import pytest
from docx import Document
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from typer.testing import CliRunner


class FakeEmbeddingFunction:
    @staticmethod
    def _normalize_text(value: object) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, (list, tuple)):
            return " ".join(str(item) for item in value)
        return str(value)

    def _vectorize(self, value: object) -> list[float]:
        clean = self._normalize_text(value)
        total = sum(ord(char) for char in clean)
        length = len(clean)
        vowels = sum(1 for char in clean.lower() if char in "aeiouäöü")
        return [
            float(total % 997) / 997.0,
            float(length % 389) / 389.0,
            float(vowels % 211) / 211.0,
        ]

    @staticmethod
    def name() -> str:
        return "docctl-fake-embedding"

    @staticmethod
    def build_from_config(config: dict) -> "FakeEmbeddingFunction":
        _ = config
        return FakeEmbeddingFunction()

    @staticmethod
    def is_legacy() -> bool:
        return False

    @staticmethod
    def get_config() -> dict[str, str]:
        return {}

    @staticmethod
    def default_space() -> str:
        return "cosine"

    @staticmethod
    def supported_spaces() -> list[str]:
        return ["cosine", "l2", "ip"]

    def embed_query(self, input: object) -> list[list[float]]:
        if isinstance(input, (list, tuple)):
            return [self._vectorize(item) for item in input]
        return [self._vectorize(input)]

    def embed_documents(self, input: list[object]) -> list[list[float]]:
        return self(input)

    def __call__(self, input: list[object]) -> list[list[float]]:
        return [self._vectorize(item) for item in input]


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture()
def patch_fake_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "docctl.services.create_embedding_function",
        lambda model_name, allow_download, verbose=False: FakeEmbeddingFunction(),
    )


@pytest.fixture()
def make_pdf() -> callable:
    def _make_pdf(path: Path, page_texts: list[str]) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        pdf = canvas.Canvas(str(path), pagesize=letter)
        for page_text in page_texts:
            y_pos = 760
            for line in page_text.splitlines() or [""]:
                pdf.drawString(72, y_pos, line)
                y_pos -= 14
            pdf.showPage()
        pdf.save()
        return path

    return _make_pdf


@pytest.fixture()
def make_docx() -> callable:
    def _make_docx(path: Path, paragraphs: list[str]) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        document = Document()
        for paragraph in paragraphs:
            document.add_paragraph(paragraph)
        document.save(str(path))
        return path

    return _make_docx
