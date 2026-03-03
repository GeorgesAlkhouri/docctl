from docctl.ids import build_chunk_id, build_doc_id


def test_build_doc_id_is_stable() -> None:
    source = "docs/Vehicle Guide.pdf"
    assert build_doc_id(source) == build_doc_id(source)


def test_build_chunk_id_is_stable() -> None:
    first = build_chunk_id("doc-1", page=3, chunk_index=2, text="sample chunk")
    second = build_chunk_id("doc-1", page=3, chunk_index=2, text="sample chunk")
    assert first == second
