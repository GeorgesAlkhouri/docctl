<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/GeorgesAlkhouri/docctl/main/docs/assets/docctl_logo_dark.png" />
    <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/GeorgesAlkhouri/docctl/main/docs/assets/docctl_logo_light.png" />
    <img alt="docctl logo" src="https://raw.githubusercontent.com/GeorgesAlkhouri/docctl/main/docs/assets/docctl_logo_light.png" width="560" />
  </picture>
</p>

<p align="center">
  Local-first CLI for agent and human document retrieval with provenance-grounded answers,
  local vector-store, and predictable machine-readable output.
</p>

<p align="center">
  <a href="https://github.com/GeorgesAlkhouri/docctl/actions/workflows/ci.yml">
    <img alt="CI" src="https://img.shields.io/github/actions/workflow/status/GeorgesAlkhouri/docctl/ci.yml?branch=main&style=for-the-badge&label=ci&logo=githubactions&logoColor=white" />
  </a>
  <a href="https://github.com/GeorgesAlkhouri/docctl/actions/workflows/security-trivy.yml">
    <img alt="Trivy" src="https://img.shields.io/github/actions/workflow/status/GeorgesAlkhouri/docctl/security-trivy.yml?branch=main&style=for-the-badge&label=trivy&logo=githubactions&logoColor=white" />
  </a>
  <a href="https://sonarcloud.io/summary/new_code?id=GeorgesAlkhouri_docctl">
    <img alt="Quality Gate" src="https://img.shields.io/sonar/quality_gate/GeorgesAlkhouri_docctl?server=https%3A%2F%2Fsonarcloud.io&style=for-the-badge&label=quality%20gate&logo=sonar&logoColor=white" />
  </a>
  <a href="https://codecov.io/gh/GeorgesAlkhouri/docctl">
    <img alt="Codecov" src="https://img.shields.io/codecov/c/github/GeorgesAlkhouri/docctl?style=for-the-badge&logo=codecov&logoColor=white&label=codecov" />
  </a>
</p>

<p align="center">
  <a href="https://www.python.org/downloads/">
    <img alt="Python 3.12 | 3.13" src="https://img.shields.io/badge/python-3.12%20%7C%203.13-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  </a>
  <a href="https://github.com/GeorgesAlkhouri/docctl">
    <img alt="Local-first" src="https://img.shields.io/badge/local--first-no%20cloud%20required-2EA44F?style=for-the-badge&logo=homeassistant&logoColor=white" />
  </a>
  <a href="https://docs.trychroma.com/">
    <img alt="Chroma" src="https://img.shields.io/badge/chroma-vector%20store-FF6F00?style=for-the-badge&logo=sqlite&logoColor=white" />
  </a>
</p>

## Why docctl
- Optimized for agentic retrieval loops with fast multi-step questions and answers.
- Runs locally with a persistent Chroma-backed index.
- Ingests `.pdf`, `.docx`, `.txt`, and `.md` with provenance metadata (`doc_id`, `source`, `title`).
- Uses sentence-aware chunking for better retrieval quality.
- Supports deterministic `--json` output for automation and agents.
- Exposes stable CLI workflows for ingest, search, diagnostics, and inventory.

## Agent Integration
Use [SKILL.md](https://github.com/GeorgesAlkhouri/docctl/blob/main/SKILL.md) when you want an agent to drive `docctl` end-to-end.
The skill makes `session` for fast iterative retrieval.

## Quickstart
Requirements:
- Python 3.12 or 3.13
- `pip`

```bash
# 1) Install from PyPI
pip install docctl

# 2) Verify CLI
docctl --help

# 3) Ingest supported files
docctl ingest ./docs --recursive --approve-write --allow-model-download

# 4) Search indexed content
docctl search "security gateway diagnostics" --top-k 5 --allow-model-download

# 5) Show one chunk by id (replace with an id from search output)
docctl show <chunk_id_from_search> --allow-model-download
```

## Command Overview
| Command | Purpose |
|---|---|
| `docctl ingest <path>` | Ingest one supported file or a directory of supported files (mutates local index state). |
| `docctl export <archive_path>` | Export current index data to one `.zip` snapshot file. |
| `docctl import <archive_path>` | Import index data from one `.zip` snapshot file (mutating). |
| `docctl search <query>` | Search indexed content with optional metadata filters. |
| `docctl show <chunk_id>` | Show one indexed chunk by exact id. |
| `docctl stats` | Show index statistics. |
| `docctl catalog` | Show index summary and per-document inventory. |
| `docctl doctor` | Run local diagnostics for index and embedding setup. |
| `docctl session` | Run a read-only NDJSON request session on stdin/stdout. |
| `docctl session start` | Start singleton detached session worker (errors if already running). |
| `docctl session status` | Show singleton detached session worker status. |
| `docctl session exec` | Execute NDJSON requests through singleton detached worker. |
| `docctl session stop` | Stop singleton detached session worker. |

## JSON and Session Mode
Use `--json` for deterministic machine-readable output:

```bash
docctl --json search "security gateway diagnostics" --top-k 5 --allow-model-download
```

Use `session` for NDJSON request/response flows. For agents, this is the preferred fast path whenever one workflow needs two or more read operations:

```bash
cat <<'EOF' | docctl session --allow-model-download
{"id":"q1","op":"search","query":"security gateway diagnostics","top_k":5}
{"id":"q2","op":"catalog"}
EOF
```

Use detached singleton worker mode when you want warm reuse across CLI invocations:

```bash
# Start singleton worker (default idle timeout: 900 seconds)
docctl --json session start

# Execute NDJSON requests through detached worker
cat <<'EOF' | docctl session exec
{"id":"q1","op":"search","query":"security gateway diagnostics","top_k":5}
{"id":"q2","op":"catalog"}
EOF

# Stop worker explicitly
docctl --json session stop
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
- `ingest` and `import` are mutating.
- `search`, `show`, `stats`, `catalog`, `doctor`, and `session` are read-only.
- `export` is read-only.

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

Build release artifacts locally:

```bash
make build-dist
make check-dist
make release-dry-run
```

## Documentation Map
- [ARCHITECTURE.md](https://github.com/GeorgesAlkhouri/docctl/blob/main/ARCHITECTURE.md)
- [docs/design-docs/index.md](https://github.com/GeorgesAlkhouri/docctl/blob/main/docs/design-docs/index.md)
- [docs/product-specs/index.md](https://github.com/GeorgesAlkhouri/docctl/blob/main/docs/product-specs/index.md)
- [docs/references/index.md](https://github.com/GeorgesAlkhouri/docctl/blob/main/docs/references/index.md)
- [SECURITY.md](https://github.com/GeorgesAlkhouri/docctl/blob/main/SECURITY.md) (canonical vulnerability disclosure policy)
- [docs/RELIABILITY.md](https://github.com/GeorgesAlkhouri/docctl/blob/main/docs/RELIABILITY.md)
- [docs/SECURITY.md](https://github.com/GeorgesAlkhouri/docctl/blob/main/docs/SECURITY.md) (internal implementation security guardrails)
- [docs/PLANS.md](https://github.com/GeorgesAlkhouri/docctl/blob/main/docs/PLANS.md)

## Contributing
For implementation and validation workflow, start with:
1. [AGENTS.md](https://github.com/GeorgesAlkhouri/docctl/blob/main/AGENTS.md)
2. [ARCHITECTURE.md](https://github.com/GeorgesAlkhouri/docctl/blob/main/ARCHITECTURE.md)
3. The indexed docs under `docs/` listed above.
