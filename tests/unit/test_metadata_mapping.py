from docctl.chunking import chunk_document_pages
from docctl.pdf_extract import PageText


def test_chunking_preserves_required_metadata_fields() -> None:
    pages = [
        PageText(page=1, text="First sentence. Second sentence for chunking."),
        PageText(page=2, text="Another page sentence for metadata."),
    ]

    chunks = chunk_document_pages(
        doc_id="doc-123",
        source="docs/input.pdf",
        title="input",
        pages=pages,
        chunk_size=80,
        chunk_overlap=10,
    )

    assert chunks
    for chunk in chunks:
        assert chunk.metadata.doc_id == "doc-123"
        assert chunk.metadata.source == "docs/input.pdf"
        assert chunk.metadata.title == "input"
        assert chunk.metadata.page in {1, 2}
