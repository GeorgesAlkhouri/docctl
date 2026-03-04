---
name: "docctl-agent"
description: "Agent skill for docctl PDF ingestion and provenance-grounded retrieval."
---

# docctl Agent Skill

## When to use
- Use for document-grounded Q&A over local PDF corpora.
- Use when answers must include provenance (`source`, `page`, `title`, `chunk_id`).
- Use when the agent can execute shell commands.

## Scope and non-scope
- In scope:
  - `docctl ingest`, `search`, `show`, `stats`, `doctor`, and `session` orchestration.
  - Full lifecycle behavior: bootstrap ingest plus retrieval loops.
  - Metadata-constrained retrieval using `doc_id`, `source`, `title`, and `page`.
- Out of scope (agent-owned responsibilities):
  - Query rewriting and query decomposition.
  - Conversation context handling and prior-turn memory policy.
  - Project-specific instruction interpretation and policy reasoning.
  - Hybrid keyword/full-text retrieval design.
  - Reranking implementation.

## Inputs and assumptions
- Expected inputs:
  - user question,
  - optional corpus path(s),
  - optional retrieval filters (`doc_id`, `source`, `title`, `page`),
  - optional index settings.
- Default CLI assumptions:
  - `--index-path ./.docctl`
  - `--collection default`
  - `--json` enabled for machine consumption.
- Safety assumption:
  - `ingest` is mutating and should only run under explicit lifecycle conditions.

## Operational workflow (ordered)
1. Run readiness checks.
   - Default to `docctl catalog` for readiness and full index inventory.
   - Run `docctl stats` only when quick aggregate counts are specifically needed.
   - Run `docctl doctor` only when diagnostics are needed (for example command failures, config issues, or unexpected index behavior).
2. Apply bootstrap ingest rules (full lifecycle).
   - If index is missing or empty, run `docctl ingest <path>`.
   - Reingest only on explicit user intent or stale corpus signals (file updates/new files).
3. Prepare retrieval query in the agent layer.
   - Rewrite/expand/paraphrase outside `docctl` if needed.
4. Execute retrieval (session-first).
   - Primary: `docctl session` with `op:"search"` for iterative loops.
   - Secondary fallback: one-shot `docctl search`.
5. Run bounded evidence expansion loop.
   - If no or weak results, broaden query and/or relax filters.
   - Increase `top_k` per policy and retry up to max attempts.
6. Inspect top evidence chunks.
   - Call `show` for selected chunk IDs before synthesis when precision matters.
   - Treat high-value returned sentences/snippets as a lead and inspect the full returned chunk before final synthesis to capture qualifiers and surrounding context.
7. Synthesize answer with explicit citations.
   - Include provenance and state uncertainty when evidence is insufficient.

## Tool guidance (docctl command contracts)
- `ingest`:
  - Mutating operation.
  - Use when index is uninitialized/empty or corpus is stale.
  - Avoid repeated reingest unless needed.
- `search`:
  - Use for one-shot retrieval.
  - Relevant options: `--doc-id`, `--source`, `--title`, `--page`, `--top-k`, `--min-score`.
- `session`:
  - Use for iterative retrieval workflows.
  - Supported operations: `search`, `show`, `stats`, `catalog`, `doctor`.
  - Search request accepts optional fields: `doc_id`, `source`, `title`, `page`, `top_k`, `min_score`.
- `show`:
  - Use to inspect and quote exact chunk evidence by `chunk_id`.
- `stats`:
  - Do not run by default in retrieval loops.
  - Use when quick aggregate counts are needed.
- `catalog`:
  - Use to inspect per-document inventory (`doc_id`, `source`, `title`, `pages`, `chunks`) with summary stats.
- `doctor`:
  - Do not run by default in retrieval loops because it adds latency.
  - Use only to diagnose environment/config failures or unexpected runtime behavior.

## Retrieval policy defaults
- Attempt 1 (baseline):
  - `top_k=5`, user query as-is, apply user-specified filters.
- Attempt 2 (broaden):
  - `top_k=10`, relax restrictive filters unless user explicitly requires them.
- Attempt 3 (final):
  - rewrite/broaden query in agent layer, keep only essential filters.
- Hard stop after 3 attempts.
- Evidence selection rule:
  - prioritize chunks with clear provenance and direct semantic match.

## Failure handling and recovery
- Missing corpus path and empty index:
  - ask for corpus path or explicit permission to ingest known path.
- Empty index:
  - ingest if allowed by lifecycle policy; otherwise return actionable instruction.
- Tool or schema errors:
  - surface exact corrective action (for example invalid field type in session request).
- No verifiable evidence after bounded retries:
  - return `cannot verify from indexed documents` and list missing information.

## Output contract for downstream agents
Return a structured payload (or equivalent human-readable response) with:
- `answer`: grounded response text.
- `citations`: list of objects with:
  - `source`
  - `page`
  - `chunk_id`
  - `title`
- `confidence`: one of `high`, `medium`, `low`.
- `limitations`: explicit gaps or uncertainty.
- `next_actions`: concrete follow-up steps.

## Minimal examples
CLI ingest/catalog/search/show:
```bash
uv run docctl --index-path ./.docctl --collection default --json ingest ./docs --recursive --allow-model-download
uv run docctl --index-path ./.docctl --collection default --json catalog
uv run docctl --index-path ./.docctl --collection default --json search "gateway diagnostics" --top-k 5 --title "operations-manual"
uv run docctl --index-path ./.docctl --collection default --json show <chunk_id>
```

NDJSON session loop:
```bash
cat <<'EOF' | uv run docctl --index-path ./.docctl --collection default session
{"id":"q1","op":"search","query":"gateway diagnostics","top_k":5,"title":"operations-manual"}
{"id":"q2","op":"show","chunk_id":"<chunk_id-from-q1>"}
{"id":"q3","op":"catalog"}
EOF
```

## Evaluation checklist
- Trigger correctness:
  - skill is used only for docctl-retrieval tasks, not unrelated workflows.
- Tool-use correctness:
  - sequence follows readiness -> ingest-if-needed -> retrieval -> evidence inspection.
- Citation completeness:
  - claims map to retrieved chunks with `source` and `page`.
- Boundary adherence:
  - query rewriting is handled by the agent, not attributed to `docctl`.
- Regression control:
  - rerun workflow checks after any meaningful change to this skill text.

## Accuracy note on ranking behavior
- Current `docctl` retrieval ranking is vector-distance based.
- Built-in reranking/hybrid retrieval is future work, not current behavior.
