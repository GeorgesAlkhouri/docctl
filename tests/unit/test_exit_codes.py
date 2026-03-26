from docctl.errors import (
    ChunkNotFoundError,
    DocumentReadError,
    EmbeddingConfigError,
    EmptyExtractedTextError,
    EmptyIndexSearchError,
    IndexNotInitializedError,
    InputPathNotFoundError,
    InternalDocctlError,
    SnapshotArchiveError,
    SnapshotConflictError,
    WriteApprovalRequiredError,
)


def test_exit_code_contract() -> None:
    assert InputPathNotFoundError("x").exit_code == 10
    assert DocumentReadError("x").exit_code == 11
    assert EmptyExtractedTextError("x").exit_code == 12
    assert SnapshotArchiveError("x").exit_code == 13
    assert IndexNotInitializedError("x").exit_code == 20
    assert WriteApprovalRequiredError("x").exit_code == 21
    assert SnapshotConflictError("x").exit_code == 22
    assert EmptyIndexSearchError("x").exit_code == 30
    assert ChunkNotFoundError("x").exit_code == 31
    assert EmbeddingConfigError("x").exit_code == 40
    assert InternalDocctlError("x").exit_code == 50
