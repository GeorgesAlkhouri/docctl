# DDES-0002 Linting and Static Analysis Policy for Agentic Python Delivery

## Intent
Define a repository-standard linting policy that is fast enough for bounded validate loops and strong
enough to reduce common agent-authored defects.

## Decision
Adopt `ruff check` and `ruff format` as mandatory baseline checks, and enforce function-level complexity and
hygiene guardrails using stable Ruff rule families.

## Ruff Rule Baseline
Blocking lint selection includes:
- correctness/import rules: `E4`, `E7`, `E9`, `F`, `I`
- bug-prone patterns: `B`
- complexity and control-flow smell signals: `C90`, `RET`, `SIM`
- unused-argument hygiene: `ARG`
- structural pressure limits: `PLR0911`, `PLR0912`, `PLR0913`, `PLR0915`

Configured thresholds:
- `mccabe.max-complexity = 8`
- `pylint.max-args = 5`
- `pylint.max-positional-args = 4`
- `pylint.max-branches = 10`
- `pylint.max-locals = 12`
- `pylint.max-public-methods = 12`
- `pylint.max-returns = 5`
- `pylint.max-statements = 35`
- `pylint.max-nested-blocks = 4`

Known intentional exceptions:
- `tests/**/*.py` ignores `ARG`, `PLR0913`, `PLR0915`
- `src/docctl/cli.py` ignores `PLR0913` (Typer command signatures)

To avoid false positives from Typer signatures, `flake8-bugbear` treats
`typer.Argument` and `typer.Option` as immutable calls.

## Preview Rules
Preview-only Ruff rules are intentionally non-blocking in CI.
Use local opt-in checks for exploratory hardening:

```bash
make lint-preview
```

Current preview set:
- `PLR0904`
- `PLR0914`
- `PLR0917`
- `PLR1702`

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

## Additional Linters
| tool | category | status | reason for agentic workflows |
|---|---|---|---|
| mypy | static typing | implemented | catches contract drift and `None`/type mismatches early |
| Bandit | security static analysis | implemented | flags risky API patterns before review |
| import-linter | architecture boundary linting | implemented | enforces dependency direction in `ARCHITECTURE.md` mechanically |

## Adoption Guidance
1. Keep Ruff checks blocking in CI and local loops.
2. Keep `mypy` non-strict initially and ratchet strictness by module.
3. Keep Bandit blocking and document any future allowlist rationale inline.
4. Keep import-linter contracts synchronized with `ARCHITECTURE.md`.

## Acceptance Check for This Decision
The policy is successful when:
1. `make lint` passes on `src/` and `tests/`.
2. `make format-check` passes on `src/` and `tests/`.
3. `make typecheck`, `make security-lint`, and `make import-lint` pass on `src/`.
4. Markdown docs and links remain valid via `make check-markdown-links`.
