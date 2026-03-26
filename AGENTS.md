# AGENTS.md

## Purpose
This repository is agent-first and documentation-indexed for `docctl`.
`AGENTS.md` is intentionally short and acts as a navigation map plus rule set.

## Start Here (Index-First)
1. Read [ARCHITECTURE.md](ARCHITECTURE.md) first.
2. Open relevant indexes next:
   - [docs/design-docs/index.md](docs/design-docs/index.md)
   - [docs/product-specs/index.md](docs/product-specs/index.md)
   - [docs/references/index.md](docs/references/index.md)
3. Only then open detailed documents.

## Navigation Map
- System architecture and boundaries: [ARCHITECTURE.md](ARCHITECTURE.md)
- Design beliefs and architecture decisions: [docs/design-docs/index.md](docs/design-docs/index.md)
- Product behavior and acceptance targets: [docs/product-specs/index.md](docs/product-specs/index.md)
- Planning and execution workflow: [docs/PLANS.md](docs/PLANS.md)
- Reliability and security requirements: [docs/RELIABILITY.md](docs/RELIABILITY.md), [docs/SECURITY.md](docs/SECURITY.md)
- Curated source references: [docs/references/index.md](docs/references/index.md)
- Agent integration skill (session-first, full-lifecycle): [SKILL.md](SKILL.md)

## Agent-First Rules
- Use progressive disclosure: index first, details second.
- Source of truth is repository-local, versioned content.
- Use authoritative, professional sources (official vendor documentation,
  standards bodies, primary project documentation, and reputable security or
  operations references), and avoid relying on informal or unverified sources.
- When behavior, tooling, or validation workflow changes, update the relevant
  repository config in the same change set (`pyproject.toml`, `Makefile`,
  `.importlinter`, or equivalent tool config files).

## Housekeeping Rules
- Any new or changed document MUST update the corresponding index file in the same change set.
- Any change that introduces or alters tooling behavior MUST update the
  corresponding config file(s) in the same change set.
- Internal markdown links MUST pass `make check-markdown-links` before completion.
- Broken, stale, or contradictory docs are defects and MUST be corrected in follow-up work.
- Final implementation handoff messages MUST include a git diff distribution
  report that counts source code changes, source code test changes, and
  documentation changes.

## Root Coding Rules
### Bounded Validate Loop Policy
- Use a bounded validate loop for each acceptance criterion.
- MUST define one concrete success check before making edits (for example:
  test, reproducible command, lint/type check, or measurable metric).
- MUST implement the smallest coherent patch that can pass the selected check
  in one cycle. Optimize for a validated slice, not the smallest possible diff.
- MUST run checks every loop using current execution mode:
- Interactive mode: run fast local checks each loop.
- Delivery mode: run the full impacted validation suite before handoff or merge.
- If checks fail, MUST use failure output to revise and rerun the loop.
- If checks pass, MAY perform behavior-preserving refactors; MUST rerun checks
  after refactors.
- During interactive loops, run fast tests first. Run longer acceptance/E2E
  checks at the end of implementation before handoff.
- Python test framework in this repository is `pytest`.
- Commits intended for `main` MUST use the Conventional Commits format
  (`type(scope): summary` or `type: summary`) so semantic-release can derive
  versions and changelog entries deterministically.
- All programming artifacts MUST be in English: identifiers, modules, classes,
  functions, comments, log/error messages, CLI flags, and JSON keys.

### Integration Test Requirement Policy
- Scope definitions to avoid ambiguity:
  - Integration tests (`tests/integration/`) verify interfaces and interactions
    between integrated components/systems for a workflow slice.
  - Acceptance/E2E smoke tests (`tests/acceptance/`) verify the system is
    acceptable for a small set of top-level user/CLI journeys.
- At least one integration test MUST be added or updated when a change has any
  of these impact triggers:
  - new user-visible behavior,
  - CLI contract change,
  - cross-module workflow/orchestration change,
  - persistence or serialization contract change (`--json` payloads, NDJSON
    session behavior, snapshot/import-export behavior, manifest shape, or exit
    code mapping),
  - significant bug fix that changes runtime behavior across module boundaries.
- Pure internal refactors that preserve externally observable behavior do not
  require new integration tests.
- Temporary exceptions are allowed only when both are present:
  - explicit rationale in the active execution plan,
  - tracked follow-up item in `docs/exec-plans/tech-debt-tracker.md` (or an
    equivalent plan artifact) to add the missing integration coverage.
- Default validation order for feature work:
  - run fast unit tests first during implementation loops,
  - run impacted integration tests before handoff,
  - run the small acceptance/E2E smoke suite at the end.

### Docstring Quality Policy
- Public Python modules, classes, functions, and methods MUST include
  Google-style docstrings that describe intent and usage, not line-by-line
  implementation details.
- Docstrings MUST include sections that are appropriate to the callable (for
  example: `Args`, `Returns`, `Raises`, `Yields`) and MUST keep type
  information consistent with the function signature.
- Docstrings SHOULD document side effects, important invariants, and notable
  error conditions so agent and human operators can safely compose behavior.
- Follow the repository guidance in
  [docs/references/google-python-style-docstrings.md](docs/references/google-python-style-docstrings.md)
  when writing or revising docstrings.
