# PSPEC-0001 CLI Contract v3 (Multi-Format Ingest, Locator-Free Retrieval)

## Commands
- `docctl ingest <path>`
- `docctl export <archive_path>`
- `docctl import <archive_path>`
- `docctl search <query>`
- `docctl show <chunk_id>`
- `docctl stats`
- `docctl catalog`
- `docctl doctor`
- `docctl session`

## Ingest Inputs
- Supported ingest file extensions: `.pdf`, `.docx`, `.txt`, `.md`.
- Directory ingest discovers supported files that match `--glob` (default `*`).
- Single-file ingest rejects unsupported extensions.

## Snapshot Import/Export
- `docctl export <archive_path>` writes one `.zip` file containing current index artifacts.
- `docctl export` requires initialized index artifacts (`manifest.json` and `chroma/`).
- `docctl import <archive_path>` accepts `.zip` files only.
- `docctl import` is mutating and supports `--replace` to overwrite existing `--index-path`.
- Without `--replace`, import fails when `--index-path` already exists.
- Import enforces safe extraction (rejects unsafe archive member paths and symlinks).

## Search Filters
- `docctl search` supports optional metadata filters:
  - `--doc-id`
  - `--source`
  - `--title`
- Multiple filters are combined using logical `AND`.
- `title` matching uses exact string equality.

## Search Ranking
- `docctl search` supports optional reranking controls:
  - `--rerank/--no-rerank` (default `--no-rerank`)
  - `--rerank-candidates` (range `[1, 100]`, must be greater than or equal to `--top-k`)
- Rerank backend is fixed to `torch`.
- `session` search payload supports optional reranking fields:
  - `rerank` (bool)
  - `rerank_candidates` (int range `[1, 100]`, must be greater than or equal to `top_k`)
- When reranking is disabled, ranking is vector-distance based.
- When reranking is enabled, vector retrieval produces candidates and a second-stage cross-encoder reranks the returned hits.

## Output Modes
- Human-readable default output.
- Deterministic JSON output with `--json`.
- `docctl session` uses NDJSON request/response on stdin/stdout:
  - Request line format: `{"id":"q1","op":"search",...}`
  - Supported operations: `search`, `show`, `stats`, `catalog`, `doctor`
  - Search request accepts optional fields: `doc_id`, `source`, `title`, `min_score`, `rerank`, `rerank_candidates`.
  - Response line format: `{"id":"q1","ok":true,"result":{...}}`
  - Error response format: `{"id":"q1","ok":false,"error":{"message":"...","exit_code":NN}}`

## Search Hit Payload
- Base hit shape includes: `id`, `text`, `metadata`, `distance`, `score`, `rank`.
- When reranking is enabled, each hit additionally includes:
  - `vector_rank` (rank before reranking)
  - `rerank_score` (cross-encoder score)

## Catalog Output
- `catalog.summary` includes aggregate counts (`document_count`, `chunk_count`, `units_total`) and `last_ingest_at`.
- Each `catalog.documents[]` row includes:
  - `doc_id`
  - `source`
  - `title`
  - `units`
  - `chunks`
  - `last_ingest_at`
  - `content_hash`

## Baseline Acceptance
1. Search returns hit metadata with source provenance.
2. Show returns the selected chunk by exact ID.
3. Stats, catalog, and doctor report environment/index health and document inventory.
4. Failure classes map to stable exit codes.
5. In `--json` mode, stdout contains only deterministic JSON payloads.
6. `session` reuses one embedding model instance across multiple search requests in one process.
