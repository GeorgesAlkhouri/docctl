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

## Agent-First Rules
- Use progressive disclosure: index first, details second.
- Source of truth is repository-local, versioned content.
- Use authoritative, professional sources (official vendor documentation,
  standards bodies, primary project documentation, and reputable security or
  operations references), and avoid relying on informal or unverified sources.

## Housekeeping Rules
- Any new or changed document MUST update the corresponding index file in the same change set.
- Internal markdown links MUST pass `make check-markdown-links` before completion.
- Broken, stale, or contradictory docs are defects and MUST be corrected in follow-up work.

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
- Python test framework in this repository is `pytest`.
- All programming artifacts MUST be in English: identifiers, modules, classes,
  functions, comments, log/error messages, CLI flags, and JSON keys.
