"""Typer CLI entrypoint for docctl."""

from __future__ import annotations

import io
import os
import sys
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from dataclasses import asdict
from pathlib import Path
from typing import Any

import typer

from .config import (
    DEFAULT_COLLECTION,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_INDEX_PATH,
    DEFAULT_RERANK_MODEL,
    ENV_EMBEDDING_MODEL,
    ENV_REQUIRE_WRITE_APPROVAL,
    ENV_RERANK_MODEL,
    CliConfig,
)
from .errors import DocctlError, EmbeddingConfigError, InternalDocctlError
from .jsonio import dumps_json
from .models import DoctorReport
from .services import (
    DEFAULT_SESSION_IDLE_TTL_SECONDS,
    collect_catalog,
    collect_stats,
    exec_session_requests,
    export_snapshot,
    import_snapshot,
    ingest_path,
    run_doctor,
    run_session_requests,
    search_chunks,
    session_worker_status,
    show_chunk,
    start_session_worker,
    stop_session_worker,
)

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="docctl is a CLI-first local document retrieval tool.",
)
session_app = typer.Typer(
    add_completion=False,
    invoke_without_command=True,
    help="Session control and NDJSON session execution commands.",
)
app.add_typer(session_app, name="session")

ALLOW_MODEL_DOWNLOAD_HELP = "Allow downloading missing embedding/reranker model artifacts."


def _emit_success(*, config: CliConfig, payload: dict[str, Any]) -> None:
    if config.json_output:
        typer.echo(dumps_json(payload))
        return
    for key, value in payload.items():
        typer.echo(f"{key}: {value}")


def _emit_doctor(*, config: CliConfig, report: DoctorReport) -> None:
    if config.json_output:
        typer.echo(dumps_json(asdict(report)))
        return
    typer.echo(f"ok: {report.ok}")
    for check in report.checks:
        status = "OK" if check.ok else "FAIL"
        typer.echo(f"[{status}] {check.name}: {check.message}")
    for warning in report.warnings:
        typer.echo(f"warning: {warning}")
    for error in report.errors:
        typer.echo(f"error: {error}")


@contextmanager
def _machine_output_guard(*, enabled: bool):
    if not enabled:
        yield
        return

    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        yield


def _handle_error(error: Exception) -> None:
    if isinstance(error, typer.Exit):
        raise error
    if isinstance(error, DocctlError):
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=error.exit_code)
    typer.echo(f"error: {error}", err=True)
    fallback = InternalDocctlError("unexpected internal error")
    raise typer.Exit(code=fallback.exit_code)


@app.callback()
def callback(
    ctx: typer.Context,
    index_path: Path = typer.Option(
        DEFAULT_INDEX_PATH,
        "--index-path",
        help="Path to local docctl index directory.",
    ),
    collection: str = typer.Option(
        DEFAULT_COLLECTION,
        "--collection",
        help="Chroma collection name.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit deterministic JSON output for agents.",
    ),
    verbose: bool = typer.Option(False, "--verbose", help="Enable verbose diagnostics."),
) -> None:
    """Initialize shared CLI context before command execution.

    Args:
        ctx: Typer context used to store runtime config.
        index_path: Base index directory path.
        collection: Chroma collection name.
        json_output: Whether machine-readable JSON output is enabled.
        verbose: Whether verbose diagnostics should be emitted.
    """
    embedding_model = os.getenv(ENV_EMBEDDING_MODEL, DEFAULT_EMBEDDING_MODEL)
    rerank_model = os.getenv(ENV_RERANK_MODEL)
    require_write_approval = os.getenv(ENV_REQUIRE_WRITE_APPROVAL, "0") == "1"

    ctx.obj = CliConfig(
        index_path=index_path,
        collection=collection,
        json_output=json_output,
        verbose=verbose,
        embedding_model=embedding_model,
        rerank_model=rerank_model or DEFAULT_RERANK_MODEL,
        require_write_approval=require_write_approval,
    )


@app.command(
    help=(
        "Ingest one supported document or a directory of supported documents. "
        "This command mutates local index state."
    )
)
def ingest(
    ctx: typer.Context,
    path: Path = typer.Argument(
        ..., help="Path to a supported file (.pdf/.docx/.txt/.md) or directory."
    ),
    recursive: bool = typer.Option(False, "--recursive", help="Scan directories recursively."),
    glob_pattern: str = typer.Option("*", "--glob", help="Glob pattern for file discovery."),
    force: bool = typer.Option(False, "--force", help="Force reingestion of known documents."),
    approve_write: bool = typer.Option(
        False, "--approve-write", help="Explicitly approve mutating writes."
    ),
    allow_model_download: bool = typer.Option(
        False,
        "--allow-model-download",
        help=ALLOW_MODEL_DOWNLOAD_HELP,
    ),
) -> None:
    """Ingest one supported file or directory into the local index.

    Args:
        ctx: Typer context containing resolved configuration.
        path: Path to a supported file or directory.
        recursive: Whether directory traversal is recursive.
        glob_pattern: Glob pattern used for file discovery.
        force: Whether known documents should be reingested.
        approve_write: Explicit write approval for mutating operations.
        allow_model_download: Whether missing embedding models may be downloaded.
    """
    config = ctx.obj
    try:
        with _machine_output_guard(enabled=config.json_output and not config.verbose):
            payload = ingest_path(
                config=config,
                input_path=path,
                recursive=recursive,
                glob_pattern=glob_pattern,
                force=force,
                approve_write=approve_write,
                allow_model_download=allow_model_download,
            )
        _emit_success(config=config, payload=payload)
    except Exception as error:  # noqa: BLE001
        _handle_error(error)


@app.command(help="Search indexed content using natural-language queries.")
def search(
    ctx: typer.Context,
    query: str = typer.Argument(..., help="Natural-language query."),
    top_k: int = typer.Option(5, "--top-k", min=1, max=100, help="Maximum hits to return."),
    doc_id: str | None = typer.Option(None, "--doc-id", help="Filter by document id."),
    source: str | None = typer.Option(None, "--source", help="Filter by source path."),
    title: str | None = typer.Option(None, "--title", help="Filter by document title."),
    min_score: float | None = typer.Option(
        None, "--min-score", min=0.0, max=1.0, help="Minimum score."
    ),
    rerank: bool = typer.Option(
        False,
        "--rerank/--no-rerank",
        help="Enable second-stage cross-encoder reranking.",
    ),
    rerank_candidates: int | None = typer.Option(
        None,
        "--rerank-candidates",
        min=1,
        max=100,
        help="Candidate depth before reranking (must be >= --top-k).",
    ),
    allow_model_download: bool = typer.Option(
        False,
        "--allow-model-download",
        help=ALLOW_MODEL_DOWNLOAD_HELP,
    ),
) -> None:
    """Search indexed chunks and emit ranked results.

    Args:
        ctx: Typer context containing resolved configuration.
        query: Natural-language query text.
        top_k: Maximum number of hits to return.
        doc_id: Optional document id filter.
        source: Optional source path filter.
        title: Optional document title filter.
        min_score: Optional minimum score filter in [0.0, 1.0].
        rerank: Whether reranking should run after vector retrieval.
        rerank_candidates: Candidate count to rerank before trimming to `top_k`.
        allow_model_download: Whether missing embedding models may be downloaded.
    """
    config = ctx.obj
    if rerank_candidates is not None and rerank_candidates < top_k:
        _handle_error(
            DocctlError(
                message="invalid rerank candidate count: --rerank-candidates must be >= --top-k",
                exit_code=50,
            )
        )
        return
    try:
        with _machine_output_guard(enabled=config.json_output and not config.verbose):
            payload = search_chunks(
                config=config,
                query=query,
                top_k=top_k,
                doc_id=doc_id,
                source=source,
                title=title,
                min_score=min_score,
                rerank=rerank,
                rerank_candidates=rerank_candidates,
                allow_model_download=allow_model_download,
            )
        _emit_success(config=config, payload=payload)
    except Exception as error:  # noqa: BLE001
        _handle_error(error)


@app.command(help="Show one indexed chunk by id.")
def show(
    ctx: typer.Context,
    chunk_id: str = typer.Argument(..., help="Chunk identifier."),
    allow_model_download: bool = typer.Option(
        False,
        "--allow-model-download",
        help=ALLOW_MODEL_DOWNLOAD_HELP,
    ),
) -> None:
    """Show one indexed chunk by id.

    Args:
        ctx: Typer context containing resolved configuration.
        chunk_id: Chunk identifier to retrieve.
        allow_model_download: Whether missing embedding models may be downloaded.
    """
    config = ctx.obj
    try:
        with _machine_output_guard(enabled=config.json_output and not config.verbose):
            payload = show_chunk(
                config=config, chunk_id=chunk_id, allow_model_download=allow_model_download
            )
        _emit_success(config=config, payload=payload)
    except Exception as error:  # noqa: BLE001
        _handle_error(error)


@app.command(help="Show index statistics.")
def stats(ctx: typer.Context) -> None:
    """Show index statistics for the current configuration.

    Args:
        ctx: Typer context containing resolved configuration.
    """
    config = ctx.obj
    try:
        with _machine_output_guard(enabled=config.json_output and not config.verbose):
            payload = collect_stats(config=config)
        _emit_success(config=config, payload=payload)
    except Exception as error:  # noqa: BLE001
        _handle_error(error)


@app.command(help="Show index catalog with summary and per-document inventory.")
def catalog(ctx: typer.Context) -> None:
    """Show catalog view for the current index configuration.

    Args:
        ctx: Typer context containing resolved configuration.
    """
    config = ctx.obj
    try:
        with _machine_output_guard(enabled=config.json_output and not config.verbose):
            payload = collect_catalog(config=config)
        _emit_success(config=config, payload=payload)
    except Exception as error:  # noqa: BLE001
        _handle_error(error)


@app.command(help="Run local diagnostics for index and embedding configuration.")
def doctor(
    ctx: typer.Context,
    allow_model_download: bool = typer.Option(
        False,
        "--allow-model-download",
        help=ALLOW_MODEL_DOWNLOAD_HELP,
    ),
) -> None:
    """Run local diagnostics for index and embedding readiness.

    Args:
        ctx: Typer context containing resolved configuration.
        allow_model_download: Whether missing embedding models may be downloaded.
    """
    config = ctx.obj
    try:
        with _machine_output_guard(enabled=config.json_output and not config.verbose):
            report = run_doctor(config=config, allow_model_download=allow_model_download)
        _emit_doctor(config=config, report=report)
        if not report.ok:
            raise EmbeddingConfigError("doctor checks failed")
    except Exception as error:  # noqa: BLE001
        _handle_error(error)


@app.command(help="Export current local index data into one zip snapshot file.")
def export(
    ctx: typer.Context,
    archive_path: Path = typer.Argument(..., help="Destination .zip snapshot archive path."),
) -> None:
    """Export current index artifacts into one zip snapshot archive.

    Args:
        ctx: Typer context containing resolved configuration.
        archive_path: Destination snapshot archive path.
    """
    config = ctx.obj
    try:
        payload = export_snapshot(config=config, archive_path=archive_path)
        _emit_success(config=config, payload=payload)
    except Exception as error:  # noqa: BLE001
        _handle_error(error)


@app.command(name="import", help="Import local index data from one zip snapshot file.")
def import_(
    ctx: typer.Context,
    archive_path: Path = typer.Argument(..., help="Source .zip snapshot archive path."),
    replace: bool = typer.Option(
        False,
        "--replace",
        help="Replace an existing --index-path before restoring snapshot data.",
    ),
    approve_write: bool = typer.Option(
        False,
        "--approve-write",
        help="Explicitly approve mutating writes.",
    ),
) -> None:
    """Import index artifacts from one zip snapshot archive.

    Args:
        ctx: Typer context containing resolved configuration.
        archive_path: Source snapshot archive path.
        replace: Whether existing index path should be overwritten.
        approve_write: Explicit write approval for mutating operations.
    """
    config = ctx.obj
    try:
        payload = import_snapshot(
            config=config,
            archive_path=archive_path,
            replace=replace,
            approve_write=approve_write,
        )
        _emit_success(config=config, payload=payload)
    except Exception as error:  # noqa: BLE001
        _handle_error(error)


@session_app.callback()
def session(
    ctx: typer.Context,
    allow_model_download: bool = typer.Option(
        False,
        "--allow-model-download",
        help=ALLOW_MODEL_DOWNLOAD_HELP,
    ),
) -> None:
    """Run legacy read-only NDJSON stream mode when no subcommand is selected.

    Args:
        ctx: Typer context containing resolved configuration.
        allow_model_download: Whether missing embedding models may be downloaded.
    """
    if ctx.invoked_subcommand is not None:
        return
    config = ctx.obj
    try:
        responses = run_session_requests(
            config=config,
            request_lines=sys.stdin,
            allow_model_download=allow_model_download,
        )
        for response in responses:
            typer.echo(dumps_json(response))
    except Exception as error:  # noqa: BLE001
        _handle_error(error)


@session_app.command(help="Start singleton detached session worker.")
def start(
    ctx: typer.Context,
    allow_model_download: bool = typer.Option(
        False,
        "--allow-model-download",
        help=ALLOW_MODEL_DOWNLOAD_HELP,
    ),
    idle_ttl: int = typer.Option(
        DEFAULT_SESSION_IDLE_TTL_SECONDS,
        "--idle-ttl",
        min=1,
        help="Idle timeout in seconds before worker self-termination.",
    ),
) -> None:
    """Start singleton detached session worker.

    Args:
        ctx: Typer context containing resolved configuration.
        allow_model_download: Whether missing embedding models may be downloaded.
        idle_ttl: Idle timeout in seconds.
    """
    config = ctx.obj
    try:
        payload = start_session_worker(
            config=config,
            allow_model_download=allow_model_download,
            idle_ttl_seconds=idle_ttl,
        )
        _emit_success(config=config, payload=payload)
    except Exception as error:  # noqa: BLE001
        _handle_error(error)


@session_app.command(help="Show singleton detached session worker status.")
def status(
    ctx: typer.Context,
    allow_model_download: bool = typer.Option(
        False,
        "--allow-model-download",
        help=ALLOW_MODEL_DOWNLOAD_HELP,
    ),
) -> None:
    """Show singleton detached session worker status.

    Args:
        ctx: Typer context containing resolved configuration.
        allow_model_download: Whether missing embedding models may be downloaded.
    """
    config = ctx.obj
    try:
        payload = session_worker_status(
            config=config,
            allow_model_download=allow_model_download,
        )
        _emit_success(config=config, payload=payload)
    except Exception as error:  # noqa: BLE001
        _handle_error(error)


@session_app.command(name="exec", help="Execute NDJSON requests through singleton session worker.")
def exec_(
    ctx: typer.Context,
    allow_model_download: bool = typer.Option(
        False,
        "--allow-model-download",
        help=ALLOW_MODEL_DOWNLOAD_HELP,
    ),
    idle_ttl: int = typer.Option(
        DEFAULT_SESSION_IDLE_TTL_SECONDS,
        "--idle-ttl",
        min=1,
        help="Idle timeout in seconds for auto-started worker.",
    ),
) -> None:
    """Execute NDJSON request lines through singleton session worker.

    Args:
        ctx: Typer context containing resolved configuration.
        allow_model_download: Whether missing embedding models may be downloaded.
        idle_ttl: Idle timeout in seconds for auto-started worker.
    """
    config = ctx.obj
    try:
        request_lines = list(sys.stdin)
        responses = exec_session_requests(
            config=config,
            request_lines=request_lines,
            allow_model_download=allow_model_download,
            idle_ttl_seconds=idle_ttl,
        )
        for response in responses:
            typer.echo(dumps_json(response))
    except Exception as error:  # noqa: BLE001
        _handle_error(error)


@session_app.command(help="Stop singleton detached session worker.")
def stop(ctx: typer.Context) -> None:
    """Stop singleton detached session worker.

    Args:
        ctx: Typer context containing resolved configuration.
    """
    config = ctx.obj
    try:
        payload = stop_session_worker()
        _emit_success(config=config, payload=payload)
    except Exception as error:  # noqa: BLE001
        _handle_error(error)


def main() -> None:
    """Run the docctl CLI application entrypoint."""
    app()


if __name__ == "__main__":
    main()
