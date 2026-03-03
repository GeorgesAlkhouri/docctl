# DDES-0002 Linting and Static Analysis Policy for Agentic Python Delivery

## Intent
Define a repository-standard linting policy that is fast enough for bounded validate loops and strong
enough to reduce common agent-authored defects.

## Decision
Adopt `ruff check` and `ruff format` as the mandatory baseline for every change set.

## Why Ruff Baseline
1. Single-tool lint and formatting keeps local feedback fast.
2. Rule coverage catches syntax/runtime-risk issues early (`E4`, `E7`, `E9`, `F`).
3. Import ordering (`I`) reduces noisy diffs and merge churn.
4. Formatting as code (`ruff format`) removes stylistic variability from agent output.

## Required Commands
Run during every bounded validate loop:

```bash
make lint
make format-check
```

Autofix path when needed:

```bash
make format
```

## Proposed Additional Linters for This Agentic Repo
The tools below are proposed next additions, not yet mandatory.

| tool | category | proposal | reason for agentic workflows |
|---|---|---|---|
| mypy | static typing | phase 2 | catches contract drift and `None`/type mismatches early |
| Bandit | security static analysis | phase 2 | flags risky API patterns before review |
| import-linter | architecture boundary linting | phase 3 | enforces dependency direction in `ARCHITECTURE.md` mechanically |

## Adoption Guidance
1. Keep Ruff checks blocking in CI and local loops.
2. Introduce `mypy` module-by-module with explicit strictness boundaries.
3. Add Bandit with an explicit baseline/allowlist policy for noisy rules.
4. Add import-linter contracts after current module topology is encoded.

## Acceptance Check for This Decision
The policy is successful when:
1. `make lint` passes on `src/` and `tests/`.
2. `make format-check` passes on `src/` and `tests/`.
3. Markdown docs and links remain valid via `make check-markdown-links`.
