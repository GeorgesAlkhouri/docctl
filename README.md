# docctl

`docctl` is a CLI-first local document retrieval tool for humans and agents.

## Features
- Local persistent index backed by Chroma
- Sentence-aware chunking with LlamaIndex `SentenceSplitter`
- PDF ingestion with page-level provenance metadata
- Deterministic `--json` output for agent workflows
- Human-debuggable errors and stable exit codes

## Requirements
- Python 3.12
- `uv`

## Setup
```bash
uv sync
```

## CLI commands
```bash
uv run docctl --help
```

Main commands:
- `docctl ingest <path>`
- `docctl search <query>`
- `docctl show <chunk_id>`
- `docctl stats`
- `docctl doctor`
- `docctl session` (read-only NDJSON batch/session mode)

Global options:
- `--index-path` (default: `./.docctl`)
- `--collection` (default: `default`)
- `--json`
- `--verbose`

## Example workflow
```bash
uv run docctl --json ingest ./docs --recursive --allow-model-download
uv run docctl --json search "security gateway diagnostics" --top-k 5 --allow-model-download
uv run docctl --json show <chunk_id>
```

## NDJSON Session Workflow
```bash
cat <<'EOF' | uv run docctl --index-path ./.docctl --collection default session
{"id":"q1","op":"search","query":"security gateway diagnostics","top_k":5}
{"id":"q2","op":"stats"}
EOF
```

## Tests
```bash
uv run pytest tests/unit tests/integration tests/acceptance -q
```

## Lint And Format
```bash
make lint
make typecheck
make security-lint
make import-lint
make format-check
```

Autofix:

```bash
make format
```

## Contributor Onboarding
Before making changes, read:
1. [AGENTS.md](AGENTS.md)
2. [ARCHITECTURE.md](ARCHITECTURE.md)
3. Relevant indexes under `docs/`:
   - [docs/design-docs/index.md](docs/design-docs/index.md)
   - [docs/product-specs/index.md](docs/product-specs/index.md)
   - [docs/references/index.md](docs/references/index.md)
