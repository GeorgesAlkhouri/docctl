# DDES-0005 Two-Stage Retrieval Re-Ranking (Chroma + Local CrossEncoder)

## Intent
Add modern reranking to `docctl` while preserving the existing local-first Chroma retrieval architecture and stable CLI/session contracts.

## Decision
`docctl` uses a two-stage retrieval flow when reranking is enabled:
1. Retrieve candidate chunks from Chroma with existing metadata filters.
2. Rerank those candidates in-process with a local `sentence-transformers` `CrossEncoder`.

Reranking is opt-in (`--rerank` / session `rerank: true`) and does not change default behavior.

## Why This Approach
- Reuses existing `ChromaStore.query()` and service boundaries with minimal churn.
- Keeps runtime self-contained without introducing provider API dependencies.
- Matches current repository architecture where query orchestration lives in `service_query.py` and `service_session.py`.
- Avoids coupling `docctl` runtime to LlamaIndex node/postprocessor abstractions for this feature.

## Contract Implications
- New optional search controls:
  - CLI: `--rerank`, `--rerank-candidates`
  - Session search payload: `rerank`, `rerank_candidates`
- Base hit fields remain unchanged.
- Reranked responses add `vector_rank` and `rerank_score`.

## Ranking Policy
- Final result count remains `top_k`.
- Default candidate depth for reranking is bounded:
  - `candidate_k = min(max(top_k, 5), 100)`
- Explicit candidate depth must satisfy `candidate_k >= top_k`.
- Ties in rerank score are resolved by original vector order for deterministic output.

## Model Default
- Default reranker model: `BAAI/bge-reranker-v2-m3`
- Configurable via `DOCCTL_RERANK_MODEL`
- Uses existing `--allow-model-download` behavior for local artifact availability.

## Runtime Notes
- Backend: fixed `torch` runtime backend.
- Candidate depth defaults to `min(max(top_k, 5), 100)` unless explicitly set with `--rerank-candidates`.
