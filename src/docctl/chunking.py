"""Sentence-aware chunking for extracted documents."""

from __future__ import annotations

from collections import defaultdict

from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import Document, MetadataMode

from .ids import build_chunk_id
from .models import ChunkMetadata, ChunkRecord
from .pdf_extract import PageText


def chunk_document_pages(
    *,
    doc_id: str,
    source: str,
    title: str,
    pages: list[PageText],
    chunk_size: int = 600,
    chunk_overlap: int = 80,
) -> list[ChunkRecord]:
    """Convert page-level text into sentence-aware chunks while preserving metadata."""
    documents = [
        Document(
            text=page.text,
            metadata={
                "doc_id": doc_id,
                "source": source,
                "title": title,
                "page": page.page,
            },
            id_=f"{doc_id}:page:{page.page}",
        )
        for page in pages
    ]

    splitter = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    nodes = splitter.get_nodes_from_documents(documents)

    chunk_counters: dict[int, int] = defaultdict(int)
    records: list[ChunkRecord] = []
    for node in nodes:
        metadata = dict(node.metadata)
        page_value = int(metadata.get("page", 0))
        chunk_counters[page_value] += 1
        chunk_index = chunk_counters[page_value]

        text = node.get_content(metadata_mode=MetadataMode.NONE).strip()
        if not text:
            continue

        chunk_id = build_chunk_id(doc_id=doc_id, page=page_value, chunk_index=chunk_index, text=text)
        records.append(
            ChunkRecord(
                id=chunk_id,
                text=text,
                metadata=ChunkMetadata(
                    doc_id=str(metadata.get("doc_id", doc_id)),
                    source=str(metadata.get("source", source)),
                    title=str(metadata.get("title", title)),
                    page=page_value,
                    section=metadata.get("section"),
                ),
            )
        )

    return records
