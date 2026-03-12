# DDES-0004 Release Automation and Trusted Publishing

## Intent
Define a low-friction release path for `docctl` that keeps versioning,
GitHub releases, and PyPI publication deterministic and auditable.

## Decision
- Use `python-semantic-release` to derive versions and changelog entries from
  Conventional Commits.
- Keep `project.version` in `pyproject.toml`, but let semantic-release manage
  updates to that field.
- Require a manual `workflow_dispatch` release workflow on `main` for release
  creation.
- Publish to TestPyPI and PyPI from a separate workflow triggered by
  `release.published`.
- Use PyPI Trusted Publishing instead of long-lived API tokens.

## Workflow
1. Maintainer triggers the `Release` workflow from `main`.
2. The workflow runs the full repository validation suite.
3. Semantic-release updates `pyproject.toml`, `CHANGELOG.md`, and `uv.lock`,
   creates a release commit and tag, pushes them, and opens a published
   GitHub Release.
4. The `Publish PyPI` workflow rebuilds artifacts from the release tag, runs
   `twine check`, publishes to TestPyPI, and then publishes to PyPI after
   environment approval.

## Rationale
- Release creation remains explicit and auditable.
- PyPI credentials stay isolated to the publish workflow.
- Trusted Publishing removes token rotation burden and narrows credential risk.
- Building from the release tag ensures published artifacts match the tagged
  source, not the mutable state of the release-cutting job workspace.

## Consequences
- Commits intended for `main` must use Conventional Commits.
- The repository must configure pending Trusted Publishers on TestPyPI and PyPI.
- The package license is MIT, but the default runtime-downloaded embedding
  model can carry different terms and must be documented separately.
