# PSPEC-0001 CLI Contract v1 (Session + Catalog Extension)

## Commands
- `docctl ingest <path>`
- `docctl search <query>`
- `docctl show <chunk_id>`
- `docctl stats`
- `docctl catalog`
- `docctl doctor`
- `docctl session`

## Search Filters
- `docctl search` supports optional metadata filters:
  - `--doc-id`
  - `--source`
  - `--title`
  - `--page`
- Multiple filters are combined using logical `AND`.
- `title` matching uses exact string equality.

## Output Modes
- Human-readable default output.
- Deterministic JSON output with `--json`.
- `docctl session` uses NDJSON request/response on stdin/stdout:
  - Request line format: `{"id":"q1","op":"search",...}`
  - Supported operations: `search`, `show`, `stats`, `catalog`, `doctor`
  - Search request accepts optional filter fields: `doc_id`, `source`, `title`, `page`.
  - Response line format: `{"id":"q1","ok":true,"result":{...}}`
  - Error response format: `{"id":"q1","ok":false,"error":{"message":"...","exit_code":NN}}`

## Baseline Acceptance
1. Search returns hit metadata with source and page provenance.
2. Show returns the selected chunk by exact ID.
3. Stats, catalog, and doctor report environment/index health and document inventory.
4. Failure classes map to stable exit codes.
5. In `--json` mode, stdout contains only deterministic JSON payloads.
6. `session` reuses one embedding model instance across multiple search requests in one process.
