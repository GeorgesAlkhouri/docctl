from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from docctl.config import CliConfig
from docctl.errors import (
    IndexNotInitializedError,
    SnapshotArchiveError,
    SnapshotConflictError,
    WriteApprovalRequiredError,
)
from docctl.service_snapshot import export_snapshot, import_snapshot
from docctl.service_types import ExportRequest, ImportRequest


def _config(tmp_path: Path, *, require_write_approval: bool = False) -> CliConfig:
    return CliConfig(
        index_path=tmp_path / "index",
        collection="test",
        embedding_model="model",
        require_write_approval=require_write_approval,
    )


def _write_valid_snapshot_archive(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", "{}")
        archive.writestr("chroma/index.sqlite3", "db")


def test_export_snapshot_rejects_non_zip_path(tmp_path: Path) -> None:
    request = ExportRequest(config=_config(tmp_path), archive_path=tmp_path / "snapshot.tar")

    with pytest.raises(SnapshotArchiveError, match="must end with .zip"):
        export_snapshot(request=request)


def test_export_snapshot_requires_initialized_index(tmp_path: Path) -> None:
    request = ExportRequest(config=_config(tmp_path), archive_path=tmp_path / "snapshot.zip")

    with pytest.raises(IndexNotInitializedError, match="index is not initialized"):
        export_snapshot(request=request)


def test_import_snapshot_rejects_non_zip_archive(tmp_path: Path) -> None:
    request = ImportRequest(
        config=_config(tmp_path),
        archive_path=tmp_path / "snapshot.tar",
        replace=False,
        approve_write=False,
    )

    with pytest.raises(SnapshotArchiveError, match="must end with .zip"):
        import_snapshot(request=request)


def test_import_snapshot_rejects_unsafe_member_path(tmp_path: Path) -> None:
    archive_path = tmp_path / "snapshot.zip"
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("../manifest.json", "{}")
        archive.writestr("chroma/index.sqlite3", "db")

    request = ImportRequest(
        config=_config(tmp_path),
        archive_path=archive_path,
        replace=False,
        approve_write=False,
    )

    with pytest.raises(SnapshotArchiveError, match="unsafe path"):
        import_snapshot(request=request)


def test_import_snapshot_conflict_when_target_exists_without_replace(tmp_path: Path) -> None:
    archive_path = tmp_path / "snapshot.zip"
    _write_valid_snapshot_archive(archive_path)
    config = _config(tmp_path)
    config.index_path.mkdir(parents=True, exist_ok=True)

    request = ImportRequest(
        config=config,
        archive_path=archive_path,
        replace=False,
        approve_write=False,
    )

    with pytest.raises(SnapshotConflictError, match="--replace"):
        import_snapshot(request=request)


def test_import_snapshot_replaces_existing_target_when_replace_enabled(tmp_path: Path) -> None:
    archive_path = tmp_path / "snapshot.zip"
    _write_valid_snapshot_archive(archive_path)
    config = _config(tmp_path)
    config.index_path.mkdir(parents=True, exist_ok=True)
    (config.index_path / "legacy.txt").write_text("legacy", encoding="utf-8")

    request = ImportRequest(
        config=config,
        archive_path=archive_path,
        replace=True,
        approve_write=False,
    )
    payload = import_snapshot(request=request)

    assert payload["files_imported"] == 2
    assert (config.index_path / "manifest.json").exists()
    assert (config.index_path / "chroma" / "index.sqlite3").exists()
    assert not (config.index_path / "legacy.txt").exists()


def test_import_snapshot_honors_write_approval_requirement(tmp_path: Path) -> None:
    archive_path = tmp_path / "snapshot.zip"
    _write_valid_snapshot_archive(archive_path)
    config = _config(tmp_path, require_write_approval=True)
    request = ImportRequest(
        config=config,
        archive_path=archive_path,
        replace=False,
        approve_write=False,
    )

    with pytest.raises(WriteApprovalRequiredError, match="write approval is required"):
        import_snapshot(request=request)
