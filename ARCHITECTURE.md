# ARCHITECTURE.md

## Target State
`docctl` is a CLI-first local document retrieval tool optimized for agent and human operability.
The repository is designed for:
- explicit boundaries,
- predictable module responsibilities,
- index-first documentation,
- mechanically verified quality checks.

## Package Topology
Primary runtime code lives in `src/docctl/`.

- `cli.py`
  - User entrypoint and command contract.
  - Responsible for argument parsing, output mode selection, and exit behavior.
- `services.py`
  - Orchestration layer for command workflows (`ingest`, `search`, `show`, `stats`, `doctor`).
- `pdf_extract.py`
  - PDF text extraction and text-normalization pipeline.
- `chunking.py`
  - Sentence-aware chunk generation and metadata propagation.
- `index_store.py`
  - Chroma persistence adapter and collection operations.
- `embeddings.py`
  - Embedding model initialization and vector generation boundary.
- `models.py`, `errors.py`, `config.py`, `jsonio.py`, `ids.py`
  - Shared data contracts, stable errors, configuration defaults, deterministic JSON, and IDs.

## Dependency Direction
Required dependency direction:
1. Helper modules (`models`, `errors`, `config`, `jsonio`, `ids`) are foundational.
2. Capability modules (`pdf_extract`, `chunking`, `index_store`, `embeddings`) depend on helpers.
3. `services` composes helpers and capability modules.
4. `cli` depends on `services` and shared contracts only.

Disallowed pattern examples:
- Low-level modules importing CLI code.
- Business flow logic split into CLI handlers instead of `services.py`.
- Ad-hoc JSON output bypassing `jsonio.py` deterministic serializer.

## Quality Gates
All changes must satisfy:
1. `make check-markdown-links`
2. `uv run pytest tests/unit tests/integration tests/acceptance -q`

Recommended behavior validation for workflow changes:
- `uv run docctl --help`
- real smoke loop: `ingest -> search -> show`

## Documentation Governance
- `AGENTS.md` is the map, not the encyclopedia.
- Deep context belongs in `docs/` and is index-first.
- Documentation updates must stay synchronized with behavior changes.
