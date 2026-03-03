# PSPEC-0001 CLI Contract v1

## Commands
- `docctl ingest <path>`
- `docctl search <query>`
- `docctl show <chunk_id>`
- `docctl stats`
- `docctl doctor`

## Output Modes
- Human-readable default output.
- Deterministic JSON output with `--json`.

## Baseline Acceptance
1. Search returns hit metadata with source and page provenance.
2. Show returns the selected chunk by exact ID.
3. Stats and doctor report environment and index health.
4. Failure classes map to stable exit codes.
