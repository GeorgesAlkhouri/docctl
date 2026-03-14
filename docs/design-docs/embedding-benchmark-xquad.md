# DDES-0003 Reproducible Multilingual Embedding Benchmark (XQuAD + Chunking Defaults)

## Intent
Provide a repeatable, repository-local benchmark for embedding model comparison
that reflects `docctl` retrieval behavior for German and English documents.

## Decision
Use `google/xquad` language splits (`xquad.en`, `xquad.de`) as public source
data, adapt contexts into PDF documents, and evaluate retrieval through `docctl`
itself (benchmark custom ingest + session search).

Primary reported metrics are computed on a deterministic hold-out `test` split.
`train` and `validation` splits are also generated and persisted to keep
evaluation hygiene clear for future tuning workflows.

## Benchmark Shape
1. Load XQuAD validation split for `en` and `de` using a pinned dataset revision.
2. Deduplicate contexts and write one PDF per unique context.
3. Sample a deterministic set of queries per language.
4. Split sampled queries into `train`, `validation`, and `test`.
5. For each language/model pair:
   - rebuild isolated index,
   - ingest corpus once using benchmark-configured chunking,
   - run all benchmark queries in one `docctl session` for each selected ranking mode,
   - compute metrics on `test` queries.

## Ranking Matrix
- Default benchmark mode is `vector_only` (no rerank).
- Optional rerank mode (`--rerank`) runs second-stage reranking.
- Optional matrix mode (`--rerank-matrix`) evaluates both `vector_only` and `rerank`
  for each language/model pair in one benchmark run so results are directly comparable.

## Model Matrix
- `paraphrase-multilingual-MiniLM-L12-v2`
- `paraphrase-multilingual-mpnet-base-v2`
- `distiluse-base-multilingual-cased-v2`

## Metrics
- `Recall@1`
- `Recall@5`
- `MRR@10`
- Query latency `p50` and `p95`
- Ingest duration (seconds)

## Artifacts
- Harness:
  [`benchmarks/embedding_eval/run_xquad_benchmark.py`](../../benchmarks/embedding_eval/run_xquad_benchmark.py)
- Benchmark usage notes:
  [`benchmarks/embedding_eval/README.md`](../../benchmarks/embedding_eval/README.md)
- Result artifacts (ignored): `benchmarks/embedding_eval/.work/`
- Tracked benchmark snapshot: this file (section below)

## Chunking Terms
- `chunk_size`: target maximum character length of each chunk. Smaller values
  create more chunks and increase retrieval granularity.
- `chunk_overlap`: number of characters repeated from the end of one chunk at
  the start of the next chunk to preserve local context at boundaries.

## Chunking Defaults
- `chunk_size=220`
- `chunk_overlap=40`

These values are used by the benchmark harness and are also aligned with the
runtime defaults in `src/docctl/chunking.py`.

## Latest Snapshot (Auto-generated)
<!-- BENCHMARK_RESULTS_START -->
- Generated at: `2026-03-05T09:51:26+00:00`
- Dataset: `google/xquad` @ `51adfef1c1287aab1d2d91b5bead9bcfb9c68583`
- Languages: `en, de`
- Queries per language: `200`
- Query splits: `train=20.0%`, `validation=20.0%`, `test=60.0%` (metrics on `test`)
- Sample size (sampled queries): `en=200, de=200`
- Sample size (evaluation `test`): `en=120, de=120`, `total=240`
- Chunking (benchmark ingest): `chunk_size=220`, `chunk_overlap=40`
- Top-K: `10`

### Per-Language Results

| language | model | ranking_mode | n_test | recall@1 | recall@5 | mrr@10 | p50 latency (ms) | p95 latency (ms) | ingest (s) |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| en | paraphrase-multilingual-MiniLM-L12-v2 | vector_only | 120 | 0.8667 | 0.9833 | 0.9190 | 16.56 | 136.69 | 21.41 |
| en | paraphrase-multilingual-mpnet-base-v2 | vector_only | 120 | 0.8417 | 0.9583 | 0.8911 | 23.58 | 194.76 | 21.44 |
| en | distiluse-base-multilingual-cased-v2 | vector_only | 120 | 0.8417 | 0.9667 | 0.9000 | 20.34 | 48.46 | 17.27 |
| de | paraphrase-multilingual-MiniLM-L12-v2 | vector_only | 120 | 0.7917 | 0.9333 | 0.8442 | 25.56 | 60.96 | 22.46 |
| de | paraphrase-multilingual-mpnet-base-v2 | vector_only | 120 | 0.8167 | 0.9667 | 0.8808 | 25.79 | 63.02 | 28.76 |
| de | distiluse-base-multilingual-cased-v2 | vector_only | 120 | 0.8333 | 0.9417 | 0.8865 | 22.13 | 49.03 | 21.52 |
| en | jinaai/jina-embeddings-v5-text-small-retrieval | vector_only | 120 | 0.9583 | 0.9917 | 0.9720 | 143.03 | 614.53 | 116.62 |
| de | jinaai/jina-embeddings-v5-text-small-retrieval | vector_only | 120 | 0.9083 | 0.9833 | 0.9389 | 191.11 | 341.42 | 117.04 |
| en | distiluse-base-multilingual-cased-v2 | rerank | 120 | 0.9667 | 0.9833 | 0.9750 | 3351.8 | 3713.0 | 41.6 |
| en | jinaai/jina-embeddings-v5-text-small-retrieval | rerank | 120 | 0.9833 | 1.0000 | 0.9917 | 3434.5 | 3803.5 | 177.0 |
| de | distiluse-base-multilingual-cased-v2 | rerank | 120 | 0.9500 | 0.9750 | 0.9586 | 2660.8 | 3170.1 | 41.5 |
| de | jinaai/jina-embeddings-v5-text-small-retrieval | rerank | 120 | 0.9583 | 0.9750 | 0.9667 | 2823.0 | 3293.8 | 255.3 |

### Macro Ranking (en/de)

| rank | model | macro recall@1 | macro recall@5 | macro mrr@10 | macro p50 latency (ms) | macro p95 latency (ms) | macro ingest (s) |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | distiluse-base-multilingual-cased-v2 | 0.8375 | 0.9542 | 0.8932 | 21.23 | 48.74 | 19.40 |
| 2 | paraphrase-multilingual-mpnet-base-v2 | 0.8292 | 0.9625 | 0.8860 | 24.69 | 128.89 | 25.10 |
| 3 | paraphrase-multilingual-MiniLM-L12-v2 | 0.8292 | 0.9583 | 0.8816 | 21.06 | 98.83 | 21.93 |
| 4 | jinaai/jina-embeddings-v5-text-small-retrieval | 0.9333 | 0.9875 | 0.9555 | 167.07 | 477.98 | 116.83 |

### Reproduction Command

```bash
uv run --with datasets python benchmarks/embedding_eval/run_xquad_benchmark.py --queries-per-lang 200 --seed 42 --top-k 10 --chunk-size 220 --chunk-overlap 40 --languages en,de --models-file benchmarks/embedding_eval/models.json --work-dir benchmarks/embedding_eval/.work --allow-model-download
```
<!-- BENCHMARK_RESULTS_END -->
