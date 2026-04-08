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
  - Stable façade entrypoint consumed by `cli.py`.
  - Preserves service-level public call signatures and monkeypatch seams.
- `service_ingest.py`, `service_query.py`, `service_session.py`, `service_doctor.py`
  - Internal orchestration modules split by workflow domain.
  - Own command execution logic for ingest/query/session/doctor flows.
- `service_session_worker.py`
  - Singleton detached session worker lifecycle and local IPC transport orchestration.
  - Reuses `service_session.py` request dispatch/runtime handling.
- `service_snapshot.py`
  - Snapshot orchestration for index export/import workflows.
  - Owns zip archive validation, safe extraction, and restore policy enforcement.
- `service_manifest.py`
  - Manifest and catalog serialization helpers.
- `service_types.py`
  - Internal dataclasses/protocols for service request payloads and injected dependencies.
- `document_extract.py`
  - Multi-format extraction dispatcher for supported inputs (`.pdf`, `.docx`, `.txt`, `.md`).
- `pdf_extract.py`
  - PDF parser branch with fallback extraction and normalization.
- `chunking.py`
  - Sentence-aware chunk generation and shared metadata propagation.
- `index_store.py`
  - Chroma persistence adapter and collection operations.
- `embeddings.py`
  - Embedding model initialization and vector generation boundary.
- `reranking.py`
  - Optional second-stage cross-encoder reranking boundary used by search/session.
- `models.py`, `errors.py`, `config.py`, `jsonio.py`, `ids.py`
  - Shared data contracts, stable errors, configuration defaults, deterministic JSON, and IDs.

## Dependency Direction
Required dependency direction:
1. Helper modules (`models`, `errors`, `config`, `jsonio`, `ids`) are foundational.
2. Capability modules (`document_extract`, `pdf_extract`, `chunking`, `index_store`, `embeddings`) depend on helpers.
3. Service orchestration modules (`service_*`) compose helpers and capability modules.
4. `services` is a compatibility façade over `service_*` modules.
5. `cli` depends on `services` and shared contracts only.

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
