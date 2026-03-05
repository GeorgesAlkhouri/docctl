# DDES-0003 Reproducible Multilingual Embedding Benchmark (XQuAD Adaptation)

## Intent
Provide a repeatable, repository-local benchmark for embedding model comparison
that reflects `docctl` retrieval behavior for German and English documents.

## Decision
Use `google/xquad` language splits (`xquad.en`, `xquad.de`) as public source
data, adapt contexts into PDF documents, and evaluate retrieval through `docctl`
itself (ingest + session search).

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
   - ingest corpus once,
   - run all benchmark queries in one `docctl session`,
   - compute metrics on `test` queries.

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

## Latest Snapshot (Auto-generated)
<!-- BENCHMARK_RESULTS_START -->
- Generated at: `2026-03-05T09:03:19+00:00`
- Dataset: `google/xquad` @ `51adfef1c1287aab1d2d91b5bead9bcfb9c68583`
- Languages: `en, de`
- Queries per language: `10`
- Query splits: `train=20.0%`, `validation=20.0%`, `test=60.0%` (metrics on `test`)
- Top-K: `10`

### Per-Language Results

| language | model | recall@1 | recall@5 | mrr@10 | p50 latency (ms) | p95 latency (ms) | ingest (s) |
|---|---|---:|---:|---:|---:|---:|---:|
| en | paraphrase-multilingual-MiniLM-L12-v2 | 0.8333 | 1.0000 | 0.8889 | 82.80 | 7895.43 | 22.35 |
| en | paraphrase-multilingual-mpnet-base-v2 | 1.0000 | 1.0000 | 1.0000 | 136.69 | 8866.48 | 23.72 |
| en | distiluse-base-multilingual-cased-v2 | 0.8333 | 1.0000 | 0.9167 | 52.43 | 6354.03 | 19.94 |
| de | paraphrase-multilingual-MiniLM-L12-v2 | 0.5000 | 0.8333 | 0.6667 | 43.01 | 7875.78 | 21.28 |
| de | paraphrase-multilingual-mpnet-base-v2 | 0.5000 | 1.0000 | 0.6806 | 65.60 | 7963.77 | 23.22 |
| de | distiluse-base-multilingual-cased-v2 | 0.6667 | 1.0000 | 0.7917 | 48.62 | 6863.48 | 19.47 |

### Macro Ranking (en/de)

| rank | model | macro recall@1 | macro recall@5 | macro mrr@10 | macro p50 latency (ms) | macro p95 latency (ms) | macro ingest (s) |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | distiluse-base-multilingual-cased-v2 | 0.7500 | 1.0000 | 0.8542 | 50.53 | 6608.75 | 19.71 |
| 2 | paraphrase-multilingual-mpnet-base-v2 | 0.7500 | 1.0000 | 0.8403 | 101.14 | 8415.13 | 23.47 |
| 3 | paraphrase-multilingual-MiniLM-L12-v2 | 0.6667 | 0.9167 | 0.7778 | 62.90 | 7885.60 | 21.82 |

### Reproduction Command

```bash
uv run --with datasets python benchmarks/embedding_eval/run_xquad_benchmark.py --queries-per-lang 10 --seed 42 --top-k 10 --languages en,de --models-file benchmarks/embedding_eval/models.json --work-dir benchmarks/embedding_eval/.work --allow-model-download
```
<!-- BENCHMARK_RESULTS_END -->
