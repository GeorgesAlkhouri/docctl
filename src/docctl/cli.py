"""Typer CLI entrypoint for docctl."""

from __future__ import annotations

from contextlib import contextmanager, redirect_stderr, redirect_stdout
from dataclasses import asdict
import io
import os
from pathlib import Path
import sys
from typing import Any

import typer

from .config import (
    CliConfig,
    DEFAULT_COLLECTION,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_INDEX_PATH,
    ENV_EMBEDDING_MODEL,
    ENV_REQUIRE_WRITE_APPROVAL,
)
from .errors import DocctlError, EmbeddingConfigError, InternalDocctlError
from .jsonio import dumps_json
from .models import DoctorReport
from .services import collect_stats, ingest_path, run_doctor, run_session_requests, search_chunks, show_chunk

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="docctl is a CLI-first local document retrieval tool.",
)


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
    embedding_model = os.getenv(ENV_EMBEDDING_MODEL, DEFAULT_EMBEDDING_MODEL)
    require_write_approval = os.getenv(ENV_REQUIRE_WRITE_APPROVAL, "0") == "1"

    ctx.obj = CliConfig(
        index_path=index_path,
        collection=collection,
        json_output=json_output,
        verbose=verbose,
        embedding_model=embedding_model,
        require_write_approval=require_write_approval,
    )


@app.command(help="Ingest one PDF or a directory of PDFs. This command mutates local index state.")
def ingest(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="Path to a PDF file or directory."),
    recursive: bool = typer.Option(False, "--recursive", help="Scan directories recursively."),
    glob_pattern: str = typer.Option("*.pdf", "--glob", help="Glob pattern for file discovery."),
    force: bool = typer.Option(False, "--force", help="Force reingestion of known documents."),
    approve_write: bool = typer.Option(False, "--approve-write", help="Explicitly approve mutating writes."),
    allow_model_download: bool = typer.Option(
        False,
        "--allow-model-download",
        help="Allow downloading missing embedding model artifacts.",
    ),
) -> None:
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
    page: int | None = typer.Option(None, "--page", min=1, help="Filter by page number."),
    min_score: float | None = typer.Option(None, "--min-score", min=0.0, max=1.0, help="Minimum score."),
    allow_model_download: bool = typer.Option(
        False,
        "--allow-model-download",
        help="Allow downloading missing embedding model artifacts.",
    ),
) -> None:
    config = ctx.obj
    try:
        with _machine_output_guard(enabled=config.json_output and not config.verbose):
            payload = search_chunks(
                config=config,
                query=query,
                top_k=top_k,
                doc_id=doc_id,
                source=source,
                page=page,
                min_score=min_score,
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
        help="Allow downloading missing embedding model artifacts.",
    ),
) -> None:
    config = ctx.obj
    try:
        with _machine_output_guard(enabled=config.json_output and not config.verbose):
            payload = show_chunk(config=config, chunk_id=chunk_id, allow_model_download=allow_model_download)
        _emit_success(config=config, payload=payload)
    except Exception as error:  # noqa: BLE001
        _handle_error(error)


@app.command(help="Show index statistics.")
def stats(ctx: typer.Context) -> None:
    config = ctx.obj
    try:
        with _machine_output_guard(enabled=config.json_output and not config.verbose):
            payload = collect_stats(config=config)
        _emit_success(config=config, payload=payload)
    except Exception as error:  # noqa: BLE001
        _handle_error(error)


@app.command(help="Run local diagnostics for index and embedding configuration.")
def doctor(
    ctx: typer.Context,
    allow_model_download: bool = typer.Option(
        False,
        "--allow-model-download",
        help="Allow downloading missing embedding model artifacts.",
    ),
) -> None:
    config = ctx.obj
    try:
        with _machine_output_guard(enabled=config.json_output and not config.verbose):
            report = run_doctor(config=config, allow_model_download=allow_model_download)
        _emit_doctor(config=config, report=report)
        if not report.ok:
            raise EmbeddingConfigError("doctor checks failed")
    except Exception as error:  # noqa: BLE001
        _handle_error(error)


@app.command(help="Run a read-only NDJSON request session on stdin/stdout.")
def session(
    ctx: typer.Context,
    allow_model_download: bool = typer.Option(
        False,
        "--allow-model-download",
        help="Allow downloading missing embedding model artifacts.",
    ),
) -> None:
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


def main() -> None:
    app()


if __name__ == "__main__":
    main()
