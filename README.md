<p align="center">
  <img src="docs/assets/docctl_logo.png" alt="docctl logo" width="560" />
</p>

<h1 align="center">docctl</h1>

<p align="center">
  Local-first CLI for ingesting PDFs and retrieving provenance-grounded answers
  with predictable machine-readable output.
</p>

<p align="center">
  <a href=".github/workflows/ci.yml">
    <img alt="CI" src="https://img.shields.io/github/actions/workflow/status/GeorgesAlkhouri/docctl/ci.yml?branch=main&style=for-the-badge&label=ci&logo=githubactions&logoColor=white" />
  </a>
  <a href="https://sonarcloud.io/summary/new_code?id=GeorgesAlkhouri_docctl">
    <img alt="Quality Gate" src="https://img.shields.io/sonar/quality_gate/GeorgesAlkhouri_docctl?server=https%3A%2F%2Fsonarcloud.io&style=for-the-badge&label=quality%20gate&logo=sonar&logoColor=white" />
  </a>
  <a href="https://codecov.io/gh/GeorgesAlkhouri/docctl">
    <img alt="Codecov" src="https://img.shields.io/codecov/c/github/GeorgesAlkhouri/docctl?style=for-the-badge&logo=codecov&logoColor=white&label=codecov" />
  </a>
</p>

<p align="center">
  <a href="https://www.python.org/downloads/release/python-3120/">
    <img alt="Python 3.12" src="https://img.shields.io/badge/python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  </a>
  <a href="https://github.com/GeorgesAlkhouri/docctl">
    <img alt="Local-first" src="https://img.shields.io/badge/local--first-no%20cloud%20required-2EA44F?style=for-the-badge&logo=homeassistant&logoColor=white" />
  </a>
  <a href="https://docs.trychroma.com/">
    <img alt="Chroma" src="https://img.shields.io/badge/chroma-vector%20store-FF6F00?style=for-the-badge&logo=sqlite&logoColor=white" />
  </a>
</p>

## Why docctl
- Runs locally with a persistent Chroma-backed index.
- Ingests PDFs with provenance metadata (`doc_id`, `source`, `title`, `page`).
- Uses sentence-aware chunking for better retrieval quality.
- Supports deterministic `--json` output for automation and agents.
- Exposes stable CLI workflows for ingest, search, diagnostics, and inventory.

## Quickstart
Requirements:
- Python 3.12
- `uv`

```bash
# 1) Install dependencies
uv sync --frozen --dev

# 2) Verify CLI
uv run docctl --help

# 3) Ingest PDFs (mutates local index)
uv run docctl ingest ./docs --recursive --approve-write --allow-model-download

# 4) Search indexed content
uv run docctl search "security gateway diagnostics" --top-k 5 --allow-model-download

# 5) Show one chunk by id (replace with an id from search output)
uv run docctl show <chunk_id_from_search> --allow-model-download
```

## Command Overview
| Command | Purpose |
|---|---|
| `docctl ingest <path>` | Ingest one PDF or a directory of PDFs (mutates local index state). |
| `docctl search <query>` | Search indexed content with optional metadata filters. |
| `docctl show <chunk_id>` | Show one indexed chunk by exact id. |
| `docctl stats` | Show index statistics. |
| `docctl catalog` | Show index summary and per-document inventory. |
| `docctl doctor` | Run local diagnostics for index and embedding setup. |
| `docctl session` | Run a read-only NDJSON request session on stdin/stdout. |

## JSON and Session Mode
Use `--json` for deterministic machine-readable output:

```bash
uv run docctl --json search "security gateway diagnostics" --top-k 5 --allow-model-download
```

Use `session` for NDJSON request/response flows:

```bash
cat <<'EOF' | uv run docctl session --allow-model-download
{"id":"q1","op":"search","query":"security gateway diagnostics","top_k":5}
{"id":"q2","op":"catalog"}
EOF
```

## Configuration
Global options:
- `--index-path` (default: `.docctl`)
- `--collection` (default: `default`)
- `--json` (deterministic JSON payloads on stdout)
- `--verbose` (extra diagnostics)

Model downloads are explicit:
- Use `--allow-model-download` when embedding artifacts are not already available.

Mutation boundaries:
- `ingest` is mutating.
- `search`, `show`, `stats`, `catalog`, `doctor`, and `session` are read-only.

## Development
Run core quality checks:

```bash
make lint
make format-check
make typecheck
make security-lint
make import-lint
make test
make test-cov
make check-markdown-links
```

Apply formatting fixes:

```bash
make format
```

## Documentation Map
- [ARCHITECTURE.md](ARCHITECTURE.md)
- [docs/design-docs/index.md](docs/design-docs/index.md)
- [docs/product-specs/index.md](docs/product-specs/index.md)
- [docs/references/index.md](docs/references/index.md)
- [docs/RELIABILITY.md](docs/RELIABILITY.md)
- [docs/SECURITY.md](docs/SECURITY.md)
- [docs/PLANS.md](docs/PLANS.md)

## Contributing
For implementation and validation workflow, start with:
1. [AGENTS.md](AGENTS.md)
2. [ARCHITECTURE.md](ARCHITECTURE.md)
3. The indexed docs under `docs/` listed above.

## Agent Integration (Optional)
Agent implementers can use the repository skill in [SKILL.md](SKILL.md) for session-first retrieval and provenance-grounded workflows.
