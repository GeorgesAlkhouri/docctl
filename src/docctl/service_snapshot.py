"""Snapshot import/export helpers for the local index path."""

from __future__ import annotations

import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from .errors import (
    IndexNotInitializedError,
    SnapshotArchiveError,
    SnapshotConflictError,
    WriteApprovalRequiredError,
)
from .service_manifest import manifest_path
from .service_types import ExportRequest, ImportRequest

_CHROMA_DIRNAME = "chroma"


def _require_write_approval(*, require_approval: bool, approve_write: bool) -> None:
    """Validate explicit write approval for mutating snapshot imports.

    Args:
        require_approval: Whether configuration requires explicit write approval.
        approve_write: CLI flag value for write approval.

    Raises:
        WriteApprovalRequiredError: If write approval is required but missing.
    """
    if require_approval and not approve_write:
        raise WriteApprovalRequiredError(
            "write approval is required. Re-run import with --approve-write or unset DOCCTL_REQUIRE_WRITE_APPROVAL."
        )


def _ensure_zip_archive_path(path: Path) -> None:
    """Validate that a snapshot archive path uses `.zip` extension.

    Args:
        path: Snapshot archive path.

    Raises:
        SnapshotArchiveError: If archive path does not end with `.zip`.
    """
    if path.suffix.lower() != ".zip":
        raise SnapshotArchiveError("snapshot archive path must end with .zip")


def _ensure_export_source(index_path: Path) -> None:
    """Validate required index artifacts exist before export.

    Args:
        index_path: Local index path to export.

    Raises:
        IndexNotInitializedError: If required index artifacts are missing.
    """
    if not index_path.exists() or not index_path.is_dir():
        raise IndexNotInitializedError(
            "index is not initialized at "
            f"{index_path}. "
            "Run `docctl ingest <path>` first, or set `--index-path` to an existing index."
        )

    if not manifest_path(index_path).exists():
        raise IndexNotInitializedError("index manifest is missing; run `docctl ingest <path>` first")

    chroma_path = index_path / _CHROMA_DIRNAME
    if not chroma_path.exists() or not chroma_path.is_dir():
        raise IndexNotInitializedError(
            "index chroma data is missing; run `docctl ingest <path>` first"
        )


def export_snapshot(*, request: ExportRequest) -> dict[str, object]:
    """Export current index path into one zip archive.

    Args:
        request: Export request payload.

    Returns:
        Export summary payload with archive and file count.
    """
    _ensure_zip_archive_path(request.archive_path)
    _ensure_export_source(request.config.index_path)

    request.archive_path.parent.mkdir(parents=True, exist_ok=True)

    files = sorted(path for path in request.config.index_path.rglob("*") if path.is_file())
    with zipfile.ZipFile(request.archive_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in files:
            relative_path = file_path.relative_to(request.config.index_path)
            archive.write(file_path, arcname=str(relative_path))

    return {
        "archive_path": str(request.archive_path.resolve()),
        "files_exported": len(files),
        "index_path": str(request.config.index_path),
    }


def _validate_archive_member(member: zipfile.ZipInfo) -> None:
    """Validate one zip member path and file mode for safe extraction.

    Args:
        member: Zip member metadata.

    Raises:
        SnapshotArchiveError: If member path or mode is unsafe.
    """
    member_name = member.filename
    if not member_name:
        raise SnapshotArchiveError("snapshot archive contains an empty member path")

    posix_path = PurePosixPath(member_name)
    if posix_path.is_absolute() or any(part == ".." for part in posix_path.parts):
        raise SnapshotArchiveError(f"snapshot archive contains unsafe path: {member_name}")

    if len(posix_path.parts) > 0 and posix_path.parts[0].endswith(":"):
        raise SnapshotArchiveError(f"snapshot archive contains unsafe path: {member_name}")

    unix_mode = member.external_attr >> 16
    if stat.S_ISLNK(unix_mode):
        raise SnapshotArchiveError(f"snapshot archive contains unsupported symlink: {member_name}")


def _safe_extract_archive(*, archive: zipfile.ZipFile, target_root: Path) -> int:
    """Extract archive members safely into a target directory.

    Args:
        archive: Open zip archive.
        target_root: Extraction target directory.

    Returns:
        Number of extracted file entries.

    Raises:
        SnapshotArchiveError: If member paths are unsafe.
    """
    members = archive.infolist()
    if not members:
        raise SnapshotArchiveError("snapshot archive is empty")

    extracted_files = 0
    for member in members:
        _validate_archive_member(member)
        normalized = Path(*PurePosixPath(member.filename).parts)
        destination = target_root / normalized

        if member.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue

        destination.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member, mode="r") as source_handle, destination.open("wb") as target_handle:
            shutil.copyfileobj(source_handle, target_handle)
        extracted_files += 1

    return extracted_files


def _resolve_snapshot_root(extract_root: Path) -> Path:
    """Resolve snapshot root folder after extraction.

    Args:
        extract_root: Directory where archive content was extracted.

    Returns:
        Directory containing snapshot artifacts.

    Raises:
        SnapshotArchiveError: If required artifacts are missing.
    """
    manifest_file = extract_root / "manifest.json"
    chroma_dir = extract_root / _CHROMA_DIRNAME
    if manifest_file.exists() and chroma_dir.is_dir():
        return extract_root

    children = [entry for entry in extract_root.iterdir()]
    if len(children) == 1 and children[0].is_dir():
        nested_root = children[0]
        nested_manifest = nested_root / "manifest.json"
        nested_chroma = nested_root / _CHROMA_DIRNAME
        if nested_manifest.exists() and nested_chroma.is_dir():
            return nested_root

    raise SnapshotArchiveError(
        "snapshot archive is missing required index artifacts: manifest.json and chroma/"
    )


def _prepare_import_target(*, index_path: Path, replace: bool) -> None:
    """Prepare target index path according to replace policy.

    Args:
        index_path: Target index path to restore into.
        replace: Whether existing target should be replaced.

    Raises:
        SnapshotConflictError: If target exists and replace is disabled.
    """
    if not index_path.exists():
        return

    if not replace:
        raise SnapshotConflictError(
            "index path already exists. Re-run import with --replace to overwrite it."
        )

    if index_path.is_dir():
        shutil.rmtree(index_path)
    else:
        index_path.unlink()


def import_snapshot(*, request: ImportRequest) -> dict[str, object]:
    """Import an index snapshot from one zip archive.

    Args:
        request: Import request payload.

    Returns:
        Import summary payload with archive and file count.

    Raises:
        SnapshotArchiveError: If archive path/content is invalid.
        SnapshotConflictError: If replace policy blocks import.
    """
    _require_write_approval(
        require_approval=request.config.require_write_approval,
        approve_write=request.approve_write,
    )
    _ensure_zip_archive_path(request.archive_path)

    if not request.archive_path.exists() or not request.archive_path.is_file():
        raise SnapshotArchiveError(f"snapshot archive does not exist: {request.archive_path}")

    try:
        with tempfile.TemporaryDirectory(prefix="docctl-import-") as temp_dir:
            extract_root = Path(temp_dir)
            with zipfile.ZipFile(request.archive_path, mode="r") as archive:
                extracted_files = _safe_extract_archive(archive=archive, target_root=extract_root)

            snapshot_root = _resolve_snapshot_root(extract_root)

            _prepare_import_target(index_path=request.config.index_path, replace=request.replace)
            request.config.index_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(snapshot_root, request.config.index_path)
    except zipfile.BadZipFile as error:
        raise SnapshotArchiveError(
            f"invalid snapshot archive format: {request.archive_path}"
        ) from error

    return {
        "archive_path": str(request.archive_path.resolve()),
        "files_imported": extracted_files,
        "index_path": str(request.config.index_path),
    }
