# Embedding Benchmark (XQuAD, de/en)

This directory contains a reproducible benchmark harness for comparing
`docctl` embedding models without changing product runtime code in `src/`.

## Scope
- Public dataset: `google/xquad` (`xquad.en`, `xquad.de`)
- Corpus construction: deduplicated contexts rendered as PDFs
- Retrieval engine: benchmark custom ingest (docctl internals with configurable chunking) + `docctl session` search
- Primary evaluation split: hold-out `test` query split

## Models
Model list is versioned in [`models.json`](models.json).

## Run
From repository root:

```bash
uv run --with datasets python benchmarks/embedding_eval/run_xquad_benchmark.py
```

Default run behavior:
- `--queries-per-lang 200` (with split `train=20%`, `validation=20%`, `test=60%`, so `n_test=120` per language)
- reranking is enabled by default (`--rerank`) using `BAAI/bge-reranker-v2-m3`

Default benchmark chunking:
- `--chunk-size 220`
- `--chunk-overlap 40`

Common smoke run:

```bash
uv run --with datasets python benchmarks/embedding_eval/run_xquad_benchmark.py --queries-per-lang 10
```

Rerank smoke run:

```bash
uv run --with datasets python benchmarks/embedding_eval/run_xquad_benchmark.py --queries-per-lang 10 --rerank --rerank-model BAAI/bge-reranker-v2-m3
```

Comparable matrix smoke run (baseline + rerank in one report):

```bash
uv run --with datasets python benchmarks/embedding_eval/run_xquad_benchmark.py --queries-per-lang 10 --rerank-matrix --rerank-model jinaai/jina-reranker-v2-base-multilingual
```

## Outputs
- Machine artifacts (gitignored):
  - `benchmarks/embedding_eval/.work/query_manifest.json`
  - `benchmarks/embedding_eval/.work/results/latest.json`
  - `benchmarks/embedding_eval/.work/results/latest.csv`
- Tracked docs snapshot:
  - `docs/design-docs/embedding-benchmark-xquad.md`

## Reproducibility
- Pinned XQuAD dataset revision hash in script constants.
- Deterministic query sampling (`--seed`).
- Deterministic train/validation/test split from sampled queries.
- Isolated index per `(language, model)` under `.work/indexes/`.
- Rebuilt index on every benchmark run.
- Chunking is explicit and configurable (`--chunk-size`, `--chunk-overlap`) for stable comparisons.
