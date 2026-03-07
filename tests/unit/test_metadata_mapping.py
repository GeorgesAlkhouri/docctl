from docctl.chunking import chunk_document_units
from docctl.models import TextUnit


def test_chunking_preserves_required_metadata_fields() -> None:
    units = [
        TextUnit(text="First sentence. Second sentence for chunking."),
        TextUnit(text="Another page sentence for metadata."),
    ]

    chunks = chunk_document_units(
        doc_id="doc-123",
        source="docs/input.pdf",
        title="input",
        units=units,
        chunk_size=80,
        chunk_overlap=10,
    )

    assert chunks
    for chunk in chunks:
        assert chunk.metadata.doc_id == "doc-123"
        assert chunk.metadata.source == "docs/input.pdf"
        assert chunk.metadata.title == "input"
