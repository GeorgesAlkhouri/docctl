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

## Tests
```bash
uv run pytest tests/unit tests/integration tests/acceptance -q
```
