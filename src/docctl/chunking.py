"""Sentence-aware chunking for extracted documents."""

from __future__ import annotations

from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import Document, MetadataMode

from .ids import build_chunk_id
from .models import ChunkMetadata, ChunkRecord, TextUnit


def chunk_document_units(  # noqa: PLR0913 - explicit parameters keep the chunking API clear; wrapping into a config object here would add indirection without reducing complexity.
    *,
    doc_id: str,
    source: str,
    title: str,
    units: list[TextUnit],
    chunk_size: int = 220,
    chunk_overlap: int = 40,
) -> list[ChunkRecord]:
    """Convert text units into sentence-aware chunks while preserving metadata.

    Args:
        doc_id: Stable identifier of the source document.
        source: Source path or URI associated with the document.
        title: Human-readable title associated with the document.
        units: Extracted text units.
        chunk_size: Maximum target size for each chunk in characters.
            Smaller values create more, shorter chunks.
        chunk_overlap: Number of trailing characters repeated from one chunk
            into the next chunk to preserve local context across boundaries.

    Returns:
        Deterministic chunk records with metadata and stable chunk identifiers.
    """
    documents = [
        Document(
            text=unit.text,
            metadata={
                "doc_id": doc_id,
                "source": source,
                "title": title,
            },
            id_=f"{doc_id}:unit",
        )
        for unit in units
    ]

    splitter = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    nodes = splitter.get_nodes_from_documents(documents)

    records: list[ChunkRecord] = []
    for node in nodes:
        metadata = dict(node.metadata)

        text = node.get_content(metadata_mode=MetadataMode.NONE).strip()
        if not text:
            continue
        chunk_index = len(records) + 1

        chunk_id = build_chunk_id(
            doc_id=doc_id,
            chunk_index=chunk_index,
            text=text,
        )
        records.append(
            ChunkRecord(
                id=chunk_id,
                text=text,
                metadata=ChunkMetadata(
                    doc_id=str(metadata.get("doc_id", doc_id)),
                    source=str(metadata.get("source", source)),
                    title=str(metadata.get("title", title)),
                    section=metadata.get("section"),
                ),
            )
        )

    return records
