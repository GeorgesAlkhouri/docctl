#!/usr/bin/env python3
"""Run a reproducible multilingual embedding benchmark for docctl retrieval."""

from __future__ import annotations

import argparse
import csv
import importlib.metadata
import json
import math
import os
import platform
import random
import re
import shlex
import shutil
import statistics
import subprocess
import sys
import textwrap
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

DATASET_ID = "google/xquad"
DATASET_REVISION = "51adfef1c1287aab1d2d91b5bead9bcfb9c68583"
DATASET_SPLIT = "validation"
DATASET_CONFIG_BY_LANG = {
    "en": "xquad.en",
    "de": "xquad.de",
}
SPLIT_TRAIN_RATIO = 0.2
SPLIT_VALIDATION_RATIO = 0.2
EVALUATION_SPLIT = "test"

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODELS_FILE = Path("benchmarks/embedding_eval/models.json")
DEFAULT_WORK_DIR = Path("benchmarks/embedding_eval/.work")
DOC_SUMMARY_PATH = REPO_ROOT / "docs/design-docs/embedding-benchmark-xquad.md"
RESULTS_MARKER_START = "<!-- BENCHMARK_RESULTS_START -->"
RESULTS_MARKER_END = "<!-- BENCHMARK_RESULTS_END -->"


@dataclass(slots=True, frozen=True)
class QuerySpec:
    """Represent one benchmark query and expected retrieval target."""

    query_id: str
    query: str
    expected_title: str

    def to_dict(self) -> dict[str, str]:
        """Serialize query spec into stable JSON shape."""

        return {
            "query_id": self.query_id,
            "query": self.query,
            "expected_title": self.expected_title,
        }


@dataclass(slots=True, frozen=True)
class IngestConfig:
    """Capture benchmark ingest settings."""

    model_name: str
    allow_model_download: bool
    chunk_size: int
    chunk_overlap: int


@dataclass(slots=True, frozen=True)
class IngestDependencies:
    """Bundle lazy-loaded docctl ingest callables."""

    chunk_document_units: Any
    create_embedding_function: Any
    build_doc_id: Any
    chroma_store_cls: Any
    extract_pdf_units: Any


@dataclass(slots=True, frozen=True)
class RankingMode:
    """Represent one retrieval ranking mode benchmark dimension."""

    key: str
    rerank: bool


def resolve_ranking_modes(*, rerank: bool, rerank_matrix: bool) -> list[RankingMode]:
    """Resolve ranking-mode benchmark dimensions from CLI options.

    Args:
        rerank: Single-mode rerank toggle.
        rerank_matrix: Whether both baseline and rerank modes should run.

    Returns:
        Ordered ranking modes to evaluate for each language/model pair.
    """
    if rerank_matrix:
        return [
            RankingMode(key="vector_only", rerank=False),
            RankingMode(key="rerank", rerank=True),
        ]
    if rerank:
        return [RankingMode(key="rerank", rerank=True)]
    return [RankingMode(key="vector_only", rerank=False)]


def parse_args() -> argparse.Namespace:  # noqa: C901, PLR0915
    """Parse benchmark CLI options."""

    parser = argparse.ArgumentParser(
        description="Run multilingual XQuAD retrieval benchmark over docctl embeddings."
    )
    parser.add_argument(
        "--queries-per-lang",
        type=int,
        default=200,
        help="Number of deterministic sampled queries per language.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed used for deterministic query sampling.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Top-K used for docctl search requests.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=220,
        help="Benchmark ingest chunk size (smaller than docctl default to increase chunk granularity).",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=40,
        help="Benchmark ingest chunk overlap.",
    )
    parser.add_argument(
        "--languages",
        type=str,
        default="en,de",
        help="Comma-separated language list; supported values: en,de.",
    )
    parser.add_argument(
        "--models-file",
        type=Path,
        default=DEFAULT_MODELS_FILE,
        help="Path to model list JSON file.",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=DEFAULT_WORK_DIR,
        help="Path to benchmark work directory.",
    )
    parser.add_argument(
        "--allow-model-download",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Allow docctl to download missing embedding artifacts.",
    )
    parser.add_argument(
        "--rerank",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable second-stage reranking in session search requests.",
    )
    parser.add_argument(
        "--rerank-matrix",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Evaluate both baseline and rerank modes as one benchmark matrix.",
    )
    parser.add_argument(
        "--rerank-model",
        type=str,
        default="BAAI/bge-reranker-v2-m3",
        help="Reranker model configured via DOCCTL_RERANK_MODEL.",
    )
    parser.add_argument(
        "--rerank-candidates",
        type=int,
        default=None,
        help="Optional candidate depth used before reranking.",
    )
    args = parser.parse_args()

    if args.queries_per_lang <= 0:
        raise SystemExit("--queries-per-lang must be positive")
    if not (1 <= args.top_k <= 100):
        raise SystemExit("--top-k must be in range [1, 100]")
    if args.chunk_size <= 0:
        raise SystemExit("--chunk-size must be positive")
    if args.chunk_overlap < 0:
        raise SystemExit("--chunk-overlap must be non-negative")
    if args.chunk_overlap >= args.chunk_size:
        raise SystemExit("--chunk-overlap must be smaller than --chunk-size")
    if args.rerank_candidates is not None and not (1 <= args.rerank_candidates <= 100):
        raise SystemExit("--rerank-candidates must be in range [1, 100]")
    if args.rerank_candidates is not None and args.rerank_candidates < args.top_k:
        raise SystemExit("--rerank-candidates must be greater than or equal to --top-k")

    languages = [part.strip() for part in args.languages.split(",") if part.strip()]
    if not languages:
        raise SystemExit("--languages must include at least one language")
    invalid = [lang for lang in languages if lang not in DATASET_CONFIG_BY_LANG]
    if invalid:
        raise SystemExit(f"Unsupported languages: {', '.join(invalid)}")
    args.languages = languages
    return args


def load_models(models_file: Path) -> list[str]:
    """Load embedding model list from JSON file."""

    path = models_file if models_file.is_absolute() else (REPO_ROOT / models_file)
    payload = json.loads(path.read_text(encoding="utf-8"))
    models = payload.get("models")
    if not isinstance(models, list) or not models:
        raise SystemExit(f"Invalid models file: {path}")
    if any(not isinstance(model, str) or not model.strip() for model in models):
        raise SystemExit(f"Invalid model value in models file: {path}")
    return [model.strip() for model in models]


def model_slug(model_name: str) -> str:
    """Convert model identifier into path-safe slug."""

    slug = re.sub(r"[^a-zA-Z0-9]+", "-", model_name).strip("-").lower()
    return slug or "model"


def write_pdf(path: Path, *, title: str, context: str) -> None:
    """Render one context into a local PDF document."""

    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(path), pagesize=letter)
    _, height = letter
    margin = 72
    line_height = 14
    max_line_chars = 95
    max_lines_per_page = int((height - (margin * 2)) / line_height)

    lines: list[str] = [title, ""]
    for paragraph in context.replace("\r\n", "\n").split("\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            lines.append("")
            continue
        lines.extend(textwrap.wrap(paragraph, width=max_line_chars))
        lines.append("")

    cursor = 0
    while cursor < len(lines):
        text_obj = pdf.beginText(margin, height - margin)
        page_lines = lines[cursor : cursor + max_lines_per_page]
        for line in page_lines:
            text_obj.textLine(line)
        pdf.drawText(text_obj)
        pdf.showPage()
        cursor += max_lines_per_page

    pdf.save()


def prepare_language_corpus(
    *,
    language: str,
    work_dir: Path,
    queries_per_lang: int,
    seed: int,
) -> tuple[list[QuerySpec], dict[str, Any]]:
    """Load XQuAD language split, create corpus PDFs, and build query sample."""

    config = DATASET_CONFIG_BY_LANG[language]
    dataset = load_xquad_split(config=config)
    corpus_dir = work_dir / "corpus" / language
    if corpus_dir.exists():
        shutil.rmtree(corpus_dir)
    corpus_dir.mkdir(parents=True, exist_ok=True)

    context_to_title: dict[str, str] = {}
    query_pool: list[QuerySpec] = []
    context_counter = 0

    for row_index, row in enumerate(dataset):
        context = str(row["context"]).strip()
        question = str(row["question"]).strip()
        if not context or not question:
            continue

        if context not in context_to_title:
            title = f"xquad-{language}-{context_counter:04d}"
            context_to_title[context] = title
            write_pdf(corpus_dir / f"{title}.pdf", title=title, context=context)
            context_counter += 1

        query_pool.append(
            QuerySpec(
                query_id=f"{language}-{row_index:05d}-{row['id']}",
                query=question,
                expected_title=context_to_title[context],
            )
        )

    if not query_pool:
        raise SystemExit(f"No query rows available for language '{language}'")

    sample_size = min(queries_per_lang, len(query_pool))
    rng = random.Random(f"{seed}:{language}")
    sampled = rng.sample(query_pool, sample_size)
    sampled.sort(key=lambda item: item.query_id)

    return sampled, {
        "language": language,
        "dataset_config": config,
        "dataset_rows": len(query_pool),
        "unique_contexts": len(context_to_title),
        "queries_selected": sample_size,
        "corpus_dir": str(corpus_dir),
    }


def split_queries(
    *, queries: list[QuerySpec], language: str, seed: int
) -> dict[str, list[QuerySpec]]:
    """Create deterministic train/validation/test query splits.

    The benchmark computes primary metrics on the hold-out `test` split.
    """

    shuffled = list(queries)
    rng = random.Random(f"{seed}:{language}:split")
    rng.shuffle(shuffled)

    if len(shuffled) < 3:
        return {
            "train": [],
            "validation": [],
            "test": sorted(shuffled, key=lambda item: item.query_id),
        }

    train_count = max(1, int(len(shuffled) * SPLIT_TRAIN_RATIO))
    validation_count = max(1, int(len(shuffled) * SPLIT_VALIDATION_RATIO))
    if train_count + validation_count >= len(shuffled):
        train_count = max(1, len(shuffled) - 2)
        validation_count = 1
    test_count = len(shuffled) - train_count - validation_count
    if test_count <= 0:
        test_count = 1
        if validation_count > 1:
            validation_count -= 1
        else:
            train_count -= 1

    train_queries = sorted(shuffled[:train_count], key=lambda item: item.query_id)
    validation_queries = sorted(
        shuffled[train_count : train_count + validation_count],
        key=lambda item: item.query_id,
    )
    test_queries = sorted(
        shuffled[train_count + validation_count :], key=lambda item: item.query_id
    )
    return {
        "train": train_queries,
        "validation": validation_queries,
        "test": test_queries,
    }


def load_xquad_split(*, config: str) -> Any:
    """Load one XQuAD split with explicit dependency error guidance."""

    try:
        from datasets import load_dataset
    except ImportError as error:  # pragma: no cover - operator environment check
        raise SystemExit(
            "Missing dependency 'datasets'. Run with:\n"
            "uv run --with datasets python benchmarks/embedding_eval/run_xquad_benchmark.py"
        ) from error

    return load_dataset(
        DATASET_ID,
        config,
        split=DATASET_SPLIT,
        revision=DATASET_REVISION,
    )


def load_docctl_ingest_dependencies() -> IngestDependencies:
    """Import benchmark ingest dependencies lazily from docctl internals."""

    try:
        from docctl.chunking import chunk_document_units
        from docctl.embeddings import create_embedding_function
        from docctl.ids import build_doc_id
        from docctl.index_store import ChromaStore
        from docctl.pdf_extract import extract_pdf_units
    except ImportError as error:  # pragma: no cover - operator environment check
        raise RuntimeError(
            "Failed to import docctl modules for benchmark ingest. "
            "Run from repository root with `uv run ...`."
        ) from error

    return IngestDependencies(
        chunk_document_units=chunk_document_units,
        create_embedding_function=create_embedding_function,
        build_doc_id=build_doc_id,
        chroma_store_cls=ChromaStore,
        extract_pdf_units=extract_pdf_units,
    )


def ingest_one_pdf(
    *,
    pdf_path: Path,
    store: Any,
    dependencies: IngestDependencies,
    config: IngestConfig,
) -> tuple[int, int]:
    """Ingest one PDF into an existing store and return unit/chunk counts."""

    source = str(pdf_path.resolve())
    title = pdf_path.stem
    doc_id = str(dependencies.build_doc_id(source))
    units = dependencies.extract_pdf_units(pdf_path)
    chunks = dependencies.chunk_document_units(
        doc_id=doc_id,
        source=source,
        title=title,
        units=units,
        chunk_size=config.chunk_size,
        chunk_overlap=config.chunk_overlap,
    )
    if not chunks:
        raise RuntimeError(f"No chunks produced for PDF: {pdf_path}")
    store.delete_by_doc_id(doc_id)
    store.upsert_chunks(chunks)
    return len(units), len(chunks)


def ingest_corpus_with_custom_chunking(
    *,
    corpus_dir: Path,
    index_path: Path,
    config: IngestConfig,
) -> dict[str, Any]:
    """Build benchmark index using custom chunking parameters."""

    dependencies = load_docctl_ingest_dependencies()
    embedding_fn = dependencies.create_embedding_function(
        model_name=config.model_name,
        allow_download=config.allow_model_download,
        verbose=False,
    )
    store = dependencies.chroma_store_cls(
        index_path=index_path,
        collection_name="default",
        embedding_function=embedding_fn,
        create_collection=True,
        embedding_model=config.model_name,
    )

    pdf_files = sorted(corpus_dir.glob("*.pdf"))
    if not pdf_files:
        raise RuntimeError(f"No PDF files found in corpus directory: {corpus_dir}")

    files_indexed = 0
    pages_indexed = 0
    chunks_indexed = 0
    errors: list[dict[str, str]] = []
    for pdf_path in pdf_files:
        try:
            pages_count, chunks_count = ingest_one_pdf(
                pdf_path=pdf_path,
                store=store,
                dependencies=dependencies,
                config=config,
            )
            files_indexed += 1
            pages_indexed += pages_count
            chunks_indexed += chunks_count
        except Exception as error:  # noqa: BLE001
            errors.append({"file": str(pdf_path), "error": str(error)})

    if files_indexed <= 0:
        first_error = errors[0]["error"] if errors else "unknown ingest failure"
        raise RuntimeError(f"Custom benchmark ingest failed. First error: {first_error}")

    return {
        "collection": "default",
        "embedding_model": config.model_name,
        "files_discovered": len(pdf_files),
        "files_indexed": files_indexed,
        "files_skipped": 0,
        "pages_indexed": pages_indexed,
        "chunks_indexed": chunks_indexed,
        "chunk_size": config.chunk_size,
        "chunk_overlap": config.chunk_overlap,
        "errors": errors,
        "index_path": str(index_path),
        "ingest_mode": "benchmark_custom_chunking",
    }


def run_ingest(
    *,
    language: str,
    model_path_slug: str,
    work_dir: Path,
    config: IngestConfig,
) -> tuple[float, dict[str, Any], Path]:
    """Build isolated index for one language/model pair and return ingest metrics."""

    index_path = work_dir / "indexes" / language / model_path_slug
    if index_path.exists():
        shutil.rmtree(index_path)
    index_path.parent.mkdir(parents=True, exist_ok=True)

    corpus_dir = work_dir / "corpus" / language
    start = time.perf_counter()
    ingest_payload = ingest_corpus_with_custom_chunking(
        corpus_dir=corpus_dir,
        index_path=index_path,
        config=config,
    )
    ingest_seconds = time.perf_counter() - start
    return ingest_seconds, ingest_payload, index_path


def query_session(  # noqa: PLR0913
    *,
    queries: list[QuerySpec],
    model_name: str,
    index_path: Path,
    top_k: int,
    allow_model_download: bool,
    rerank: bool,
    rerank_candidates: int | None,
    rerank_model: str,
) -> tuple[list[dict[str, Any]], list[float]]:
    """Execute queries in one docctl session and capture per-query latency."""

    process = open_session_process(
        model_name=model_name,
        index_path=index_path,
        allow_model_download=allow_model_download,
        rerank_model=rerank_model,
    )
    responses, latencies_ms = execute_session_queries(
        process=process,
        queries=queries,
        top_k=top_k,
        rerank=rerank,
        rerank_candidates=rerank_candidates,
    )
    finalize_session_process(process=process)
    return responses, latencies_ms


def open_session_process(
    *,
    model_name: str,
    index_path: Path,
    allow_model_download: bool,
    rerank_model: str,
) -> subprocess.Popen[str]:
    """Start docctl session subprocess for iterative search requests."""

    command = [
        "uv",
        "run",
        "docctl",
        "--index-path",
        str(index_path),
        "--collection",
        "default",
        "session",
    ]
    if allow_model_download:
        command.append("--allow-model-download")

    env = dict(os.environ)
    env["DOCCTL_EMBEDDING_MODEL"] = model_name
    env["DOCCTL_RERANK_MODEL"] = rerank_model

    return subprocess.Popen(
        command,
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=1,
    )


def execute_session_queries(
    *,
    process: subprocess.Popen[str],
    queries: list[QuerySpec],
    top_k: int,
    rerank: bool,
    rerank_candidates: int | None,
) -> tuple[list[dict[str, Any]], list[float]]:
    """Send search requests over one live session process."""

    if process.stdin is None or process.stdout is None:
        raise RuntimeError("Failed to start docctl session pipes")

    responses: list[dict[str, Any]] = []
    latencies_ms: list[float] = []
    try:
        for spec in queries:
            response, elapsed_ms = send_search_request(
                process=process,
                query_spec=spec,
                top_k=top_k,
                rerank=rerank,
                rerank_candidates=rerank_candidates,
            )
            if not response.get("ok", False):
                raise RuntimeError(f"Session query failed: {response}")
            responses.append(response)
            latencies_ms.append(elapsed_ms)
    finally:
        if process.stdin is not None and not process.stdin.closed:
            process.stdin.close()

    return responses, latencies_ms


def send_search_request(
    *,
    process: subprocess.Popen[str],
    query_spec: QuerySpec,
    top_k: int,
    rerank: bool,
    rerank_candidates: int | None,
) -> tuple[dict[str, Any], float]:
    """Send one search request and return parsed response with latency."""

    if process.stdin is None or process.stdout is None:
        raise RuntimeError("Session pipes are unavailable")

    request = {
        "id": query_spec.query_id,
        "op": "search",
        "query": query_spec.query,
        "top_k": top_k,
    }
    if rerank:
        request["rerank"] = True
        if rerank_candidates is not None:
            request["rerank_candidates"] = rerank_candidates
    request_line = json.dumps(request, ensure_ascii=False)

    start = time.perf_counter()
    process.stdin.write(request_line + "\n")
    process.stdin.flush()
    response_line = process.stdout.readline()
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    if not response_line:
        raise RuntimeError("Session ended before all responses were read")
    return json.loads(response_line), elapsed_ms


def finalize_session_process(*, process: subprocess.Popen[str]) -> None:
    """Validate clean session shutdown after query loop."""

    stdout_tail = process.stdout.read() if process.stdout is not None else ""
    stderr_tail = process.stderr.read() if process.stderr is not None else ""
    process.wait(timeout=60)
    if stdout_tail.strip():
        raise RuntimeError(f"Unexpected trailing session stdout:\n{stdout_tail}")
    if process.returncode != 0:
        raise RuntimeError(
            f"Session failed with exit code {process.returncode}\nstderr:\n{stderr_tail}"
        )


def reciprocal_rank_at_k(*, hits: list[dict[str, Any]], expected_title: str, k: int) -> float:
    """Compute reciprocal rank for first relevant hit within top-k."""

    for rank, hit in enumerate(hits[:k], start=1):
        title = str(hit.get("metadata", {}).get("title", ""))
        if title == expected_title:
            return 1.0 / float(rank)
    return 0.0


def percentile(values: list[float], q: float) -> float:
    """Return nearest-rank percentile for non-empty numeric list."""

    if not values:
        return 0.0
    if q <= 0:
        return min(values)
    if q >= 1:
        return max(values)
    sorted_values = sorted(values)
    index = max(0, min(len(sorted_values) - 1, math.ceil(q * len(sorted_values)) - 1))
    return float(sorted_values[index])


def score_metrics(
    *,
    queries: list[QuerySpec],
    responses: list[dict[str, Any]],
    latencies_ms: list[float],
) -> dict[str, float]:
    """Compute retrieval and latency metrics for one language/model run."""

    if len(queries) != len(responses):
        raise RuntimeError("Query/response count mismatch")

    recall_at_1 = 0.0
    recall_at_5 = 0.0
    mrr_at_10 = 0.0

    expected_title_by_id = {query.query_id: query.expected_title for query in queries}
    for response in responses:
        query_id = str(response.get("id"))
        expected_title = expected_title_by_id[query_id]
        result = response.get("result", {})
        hits = result.get("hits", [])
        top_1 = hits[:1]
        top_5 = hits[:5]

        if any(str(hit.get("metadata", {}).get("title", "")) == expected_title for hit in top_1):
            recall_at_1 += 1.0
        if any(str(hit.get("metadata", {}).get("title", "")) == expected_title for hit in top_5):
            recall_at_5 += 1.0
        mrr_at_10 += reciprocal_rank_at_k(hits=hits, expected_title=expected_title, k=10)

    total = float(len(queries))
    return {
        "recall_at_1": recall_at_1 / total,
        "recall_at_5": recall_at_5 / total,
        "mrr_at_10": mrr_at_10 / total,
        "query_latency_ms_p50": statistics.median(latencies_ms),
        "query_latency_ms_p95": percentile(latencies_ms, 0.95),
    }


def summarize_aggregates(
    *,
    results: list[dict[str, Any]],
    languages: list[str],
    models: list[str],
    ranking_modes: list[RankingMode],
) -> dict[str, Any]:
    """Build language leaderboard and macro-average model ranking."""

    language_leaderboards: dict[str, list[dict[str, Any]]] = {}
    for language in languages:
        for mode in ranking_modes:
            per_language_mode = [
                row
                for row in results
                if row["language"] == language and row["ranking_mode"] == mode.key
            ]
            ranked = sorted(
                per_language_mode,
                key=lambda row: (
                    row["metrics"]["mrr_at_10"],
                    row["metrics"]["recall_at_5"],
                    -row["metrics"]["query_latency_ms_p95"],
                ),
                reverse=True,
            )
            language_leaderboards[f"{language}:{mode.key}"] = ranked

    macro_by_model: list[dict[str, Any]] = []
    for mode in ranking_modes:
        for model in models:
            rows = [
                row for row in results if row["model"] == model and row["ranking_mode"] == mode.key
            ]
            if not rows:
                continue
            macro_by_model.append(
                {
                    "model": model,
                    "ranking_mode": mode.key,
                    "languages_evaluated": sorted({row["language"] for row in rows}),
                    "macro_avg": {
                        "recall_at_1": statistics.mean(
                            row["metrics"]["recall_at_1"] for row in rows
                        ),
                        "recall_at_5": statistics.mean(
                            row["metrics"]["recall_at_5"] for row in rows
                        ),
                        "mrr_at_10": statistics.mean(row["metrics"]["mrr_at_10"] for row in rows),
                        "query_latency_ms_p50": statistics.mean(
                            row["metrics"]["query_latency_ms_p50"] for row in rows
                        ),
                        "query_latency_ms_p95": statistics.mean(
                            row["metrics"]["query_latency_ms_p95"] for row in rows
                        ),
                        "ingest_seconds": statistics.mean(row["ingest_seconds"] for row in rows),
                    },
                }
            )

    macro_ranking = sorted(
        macro_by_model,
        key=lambda row: (
            row["macro_avg"]["mrr_at_10"],
            row["macro_avg"]["recall_at_5"],
            -row["macro_avg"]["query_latency_ms_p95"],
        ),
        reverse=True,
    )

    return {
        "per_language_leaderboard": language_leaderboards,
        "macro_ranking": macro_ranking,
    }


def write_results_artifacts(
    *,
    report: dict[str, Any],
    work_dir: Path,
) -> tuple[Path, Path]:
    """Write JSON and CSV benchmark artifacts to work directory."""

    results_dir = work_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    json_path = results_dir / "latest.json"
    csv_path = results_dir / "latest.csv"

    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "language",
                "model",
                "ranking_mode",
                "rerank_enabled",
                "recall_at_1",
                "recall_at_5",
                "mrr_at_10",
                "query_latency_ms_p50",
                "query_latency_ms_p95",
                "ingest_seconds",
                "query_count",
            ]
        )
        for row in report["results"]:
            metrics = row["metrics"]
            writer.writerow(
                [
                    row["language"],
                    row["model"],
                    row["ranking_mode"],
                    row["rerank_enabled"],
                    f"{metrics['recall_at_1']:.6f}",
                    f"{metrics['recall_at_5']:.6f}",
                    f"{metrics['mrr_at_10']:.6f}",
                    f"{metrics['query_latency_ms_p50']:.3f}",
                    f"{metrics['query_latency_ms_p95']:.3f}",
                    f"{row['ingest_seconds']:.3f}",
                    row["query_count"],
                ]
            )

    return json_path, csv_path


def sample_size_summary(report: dict[str, Any]) -> tuple[dict[str, int], dict[str, int], int]:
    """Extract sampled and evaluation split query counts per language."""

    settings = report["settings"]
    language_meta = report["dataset_meta"]["languages"]
    sampled_by_language = {
        str(row["language"]): int(row.get("queries_selected", 0)) for row in language_meta
    }
    split_counts_by_language = {
        str(row["language"]): {
            str(split): int(count) for split, count in row.get("query_split_counts", {}).items()
        }
        for row in language_meta
    }
    eval_split = str(settings["evaluation_split"])
    eval_counts_by_language = {
        language: split_counts_by_language.get(language, {}).get(eval_split, 0)
        for language in settings["languages"]
    }
    total_eval_count = sum(eval_counts_by_language.values())
    return sampled_by_language, eval_counts_by_language, total_eval_count


def append_per_language_results(lines: list[str], report: dict[str, Any]) -> None:
    """Append per-language benchmark table to markdown output."""

    lines.append("### Per-Language Results")
    lines.append("")
    lines.append(
        "| language | ranking_mode | model | n_test | recall@1 | recall@5 | mrr@10 | p50 latency (ms) | p95 latency (ms) | ingest (s) |"
    )
    lines.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for row in report["results"]:
        metrics = row["metrics"]
        lines.append(
            "| "
            f"{row['language']} | {row['ranking_mode']} | {row['model']} | {row['query_count']} | "
            f"{metrics['recall_at_1']:.4f} | "
            f"{metrics['recall_at_5']:.4f} | {metrics['mrr_at_10']:.4f} | "
            f"{metrics['query_latency_ms_p50']:.2f} | {metrics['query_latency_ms_p95']:.2f} | "
            f"{row['ingest_seconds']:.2f} |"
        )
    lines.append("")


def append_macro_ranking(lines: list[str], report: dict[str, Any]) -> None:
    """Append macro ranking table to markdown output."""

    lines.append("### Macro Ranking")
    lines.append("")
    lines.append(
        "| rank | ranking_mode | model | macro recall@1 | macro recall@5 | macro mrr@10 | macro p50 latency (ms) | macro p95 latency (ms) | macro ingest (s) |"
    )
    lines.append("|---:|---|---|---:|---:|---:|---:|---:|---:|")
    for index, row in enumerate(report["aggregates"]["macro_ranking"], start=1):
        metric = row["macro_avg"]
        lines.append(
            "| "
            f"{index} | {row['ranking_mode']} | {row['model']} | {metric['recall_at_1']:.4f} | {metric['recall_at_5']:.4f} | "
            f"{metric['mrr_at_10']:.4f} | {metric['query_latency_ms_p50']:.2f} | "
            f"{metric['query_latency_ms_p95']:.2f} | {metric['ingest_seconds']:.2f} |"
        )
    lines.append("")


def build_results_markdown(report: dict[str, Any]) -> str:
    """Render markdown block used for documentation snapshot update."""

    lines: list[str] = []
    run_meta = report["run_meta"]
    settings = report["settings"]
    sampled_by_language, eval_counts_by_language, total_eval_count = sample_size_summary(report)
    eval_split = str(settings["evaluation_split"])

    lines.append(f"- Generated at: `{run_meta['timestamp_utc']}`")
    lines.append(f"- Dataset: `{DATASET_ID}` @ `{DATASET_REVISION}`")
    lines.append(f"- Languages: `{', '.join(settings['languages'])}`")
    lines.append(f"- Queries per language: `{settings['queries_per_lang']}`")
    lines.append(
        "- Query splits: "
        f"`train={settings['split_train_ratio']:.1%}`, "
        f"`validation={settings['split_validation_ratio']:.1%}`, "
        f"`test={(1.0 - settings['split_train_ratio'] - settings['split_validation_ratio']):.1%}` "
        f"(metrics on `{settings['evaluation_split']}`)"
    )
    sampled_parts = [
        f"{language}={sampled_by_language.get(language, 0)}" for language in settings["languages"]
    ]
    lines.append(f"- Sample size (sampled queries): `{', '.join(sampled_parts)}`")
    eval_parts = [
        f"{language}={eval_counts_by_language.get(language, 0)}"
        for language in settings["languages"]
    ]
    lines.append(
        f"- Sample size (evaluation `{eval_split}`): `{', '.join(eval_parts)}`, "
        f"`total={total_eval_count}`"
    )
    lines.append(
        f"- Chunking (benchmark ingest): `chunk_size={settings['chunk_size']}`, "
        f"`chunk_overlap={settings['chunk_overlap']}`"
    )
    lines.append(f"- Top-K: `{settings['top_k']}`")
    lines.append(f"- Ranking modes: `{', '.join(settings['ranking_modes'])}`")
    lines.append(f"- Rerank matrix mode: `{settings['rerank_matrix']}`")
    if "rerank" in settings["ranking_modes"]:
        lines.append(f"- Rerank model: `{settings['rerank_model']}`")
        lines.append(f"- Rerank candidates: `{settings['rerank_candidates']}`")
    lines.append("")
    append_per_language_results(lines, report)
    append_macro_ranking(lines, report)
    lines.append("### Reproduction Command")
    lines.append("")
    lines.append("```bash")
    lines.append(run_meta["command"])
    lines.append("```")

    return "\n".join(lines)


def update_summary_doc(*, report: dict[str, Any]) -> None:
    """Write latest benchmark snapshot into design document marker block."""

    existing = DOC_SUMMARY_PATH.read_text(encoding="utf-8")
    if RESULTS_MARKER_START not in existing or RESULTS_MARKER_END not in existing:
        raise RuntimeError(
            f"Missing markers in summary doc: {DOC_SUMMARY_PATH}. "
            f"Expected {RESULTS_MARKER_START} and {RESULTS_MARKER_END}."
        )
    before, remainder = existing.split(RESULTS_MARKER_START, maxsplit=1)
    middle, after = remainder.split(RESULTS_MARKER_END, maxsplit=1)
    _ = middle

    replacement = "\n" + build_results_markdown(report).rstrip() + "\n"
    updated = before + RESULTS_MARKER_START + replacement + RESULTS_MARKER_END + after
    DOC_SUMMARY_PATH.write_text(updated, encoding="utf-8")


def format_command_for_meta(args: argparse.Namespace) -> str:
    """Build explicit reproduction command line for report metadata."""

    parts = [
        "uv",
        "run",
        "--with",
        "datasets",
        "python",
        "benchmarks/embedding_eval/run_xquad_benchmark.py",
        "--queries-per-lang",
        str(args.queries_per_lang),
        "--seed",
        str(args.seed),
        "--top-k",
        str(args.top_k),
        "--chunk-size",
        str(args.chunk_size),
        "--chunk-overlap",
        str(args.chunk_overlap),
        "--languages",
        ",".join(args.languages),
        "--models-file",
        str(args.models_file),
        "--work-dir",
        str(args.work_dir),
    ]
    if args.allow_model_download:
        parts.append("--allow-model-download")
    else:
        parts.append("--no-allow-model-download")
    if args.rerank_matrix:
        parts.append("--rerank-matrix")
    elif args.rerank:
        parts.append("--rerank")
    else:
        parts.append("--no-rerank")
    if args.rerank or args.rerank_matrix:
        parts.extend(["--rerank-model", args.rerank_model])
        if args.rerank_candidates is not None:
            parts.extend(["--rerank-candidates", str(args.rerank_candidates)])
    return " ".join(shlex.quote(part) for part in parts)


def detect_docctl_version() -> str:
    """Detect installed docctl package version in current environment."""

    try:
        return importlib.metadata.version("docctl")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def main() -> None:  # noqa: PLR0915
    """Run end-to-end benchmark, persist artifacts, and update docs snapshot."""

    args = parse_args()
    work_dir = args.work_dir if args.work_dir.is_absolute() else (REPO_ROOT / args.work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    models = load_models(args.models_file)
    ranking_modes = resolve_ranking_modes(rerank=args.rerank, rerank_matrix=args.rerank_matrix)

    language_query_splits: dict[str, dict[str, list[QuerySpec]]] = {}
    dataset_meta_languages: list[dict[str, Any]] = []
    for language in args.languages:
        queries, lang_meta = prepare_language_corpus(
            language=language,
            work_dir=work_dir,
            queries_per_lang=args.queries_per_lang,
            seed=args.seed,
        )
        split_map = split_queries(queries=queries, language=language, seed=args.seed)
        language_query_splits[language] = split_map
        lang_meta["query_split_counts"] = {
            split_name: len(split_queries_) for split_name, split_queries_ in split_map.items()
        }
        dataset_meta_languages.append(lang_meta)

    manifest = {
        "dataset_id": DATASET_ID,
        "dataset_revision": DATASET_REVISION,
        "split": DATASET_SPLIT,
        "seed": args.seed,
        "queries_per_lang": args.queries_per_lang,
        "languages": args.languages,
        "query_splits": {
            language: {
                split_name: [query.to_dict() for query in split_queries_]
                for split_name, split_queries_ in language_query_splits[language].items()
            }
            for language in args.languages
        },
    }
    manifest_path = work_dir / "query_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    results: list[dict[str, Any]] = []
    for language in args.languages:
        queries = language_query_splits[language][EVALUATION_SPLIT]
        if not queries:
            raise RuntimeError(f"No hold-out test queries available for language '{language}'")
        for model_name in models:
            slug = model_slug(model_name)
            print(f"[benchmark] language={language} model={model_name}", flush=True)
            ingest_config = IngestConfig(
                model_name=model_name,
                allow_model_download=args.allow_model_download,
                chunk_size=args.chunk_size,
                chunk_overlap=args.chunk_overlap,
            )
            ingest_seconds, ingest_payload, index_path = run_ingest(
                language=language,
                model_path_slug=slug,
                work_dir=work_dir,
                config=ingest_config,
            )
            for ranking_mode in ranking_modes:
                print(
                    f"[benchmark] language={language} model={model_name} ranking_mode={ranking_mode.key}",
                    flush=True,
                )
                responses, latencies_ms = query_session(
                    queries=queries,
                    model_name=model_name,
                    index_path=index_path,
                    top_k=args.top_k,
                    allow_model_download=args.allow_model_download,
                    rerank=ranking_mode.rerank,
                    rerank_candidates=args.rerank_candidates,
                    rerank_model=args.rerank_model,
                )
                metrics = score_metrics(
                    queries=queries,
                    responses=responses,
                    latencies_ms=latencies_ms,
                )
                results.append(
                    {
                        "language": language,
                        "model": model_name,
                        "model_slug": slug,
                        "ranking_mode": ranking_mode.key,
                        "rerank_enabled": ranking_mode.rerank,
                        "evaluation_split": EVALUATION_SPLIT,
                        "query_count": len(queries),
                        "ingest_seconds": ingest_seconds,
                        "ingest_summary": ingest_payload,
                        "metrics": metrics,
                    }
                )

    aggregates = summarize_aggregates(
        results=results,
        languages=args.languages,
        models=models,
        ranking_modes=ranking_modes,
    )
    timestamp_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    report = {
        "run_meta": {
            "timestamp_utc": timestamp_utc,
            "command": format_command_for_meta(args),
            "platform": platform.platform(),
            "python_version": sys.version.split()[0],
            "docctl_version": detect_docctl_version(),
        },
        "dataset_meta": {
            "dataset_id": DATASET_ID,
            "dataset_revision": DATASET_REVISION,
            "split": DATASET_SPLIT,
            "languages": dataset_meta_languages,
            "query_manifest": str(manifest_path),
        },
        "settings": {
            "queries_per_lang": args.queries_per_lang,
            "seed": args.seed,
            "top_k": args.top_k,
            "chunk_size": args.chunk_size,
            "chunk_overlap": args.chunk_overlap,
            "languages": args.languages,
            "split_train_ratio": SPLIT_TRAIN_RATIO,
            "split_validation_ratio": SPLIT_VALIDATION_RATIO,
            "evaluation_split": EVALUATION_SPLIT,
            "models": models,
            "allow_model_download": args.allow_model_download,
            "rerank": args.rerank,
            "rerank_matrix": args.rerank_matrix,
            "ranking_modes": [mode.key for mode in ranking_modes],
            "rerank_model": args.rerank_model,
            "rerank_candidates": args.rerank_candidates,
            "work_dir": str(work_dir),
        },
        "results": results,
        "aggregates": aggregates,
    }

    json_path, csv_path = write_results_artifacts(report=report, work_dir=work_dir)
    update_summary_doc(report=report)

    print(f"[benchmark] wrote {json_path}")
    print(f"[benchmark] wrote {csv_path}")
    print(f"[benchmark] updated {DOC_SUMMARY_PATH}")


if __name__ == "__main__":
    main()
