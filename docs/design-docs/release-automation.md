# DDES-0004 Release Automation and Trusted Publishing

## Intent
Define a low-friction release path for `docctl` that keeps versioning,
GitHub releases, and PyPI publication deterministic and auditable.

## Decision
- Use `python-semantic-release` to derive versions and changelog entries from
  Conventional Commits.
- Keep `project.version` in `pyproject.toml`, but let semantic-release manage
  updates to that field.
- Use Dependabot for `uv` and `github-actions` with grouped updates and bounded
  pull request volume.
- Keep Dependabot commit prefixes on `chore(...)` paths so dependency update
  merges do not auto-bump semantic versions.
- Require a manual `workflow_dispatch` release workflow on `main` for release
  creation.
- Require a repository secret named `RELEASE_TOKEN` for the release workflow so
  automation can push the semantic-release commit and tag under the
  repository's pull-request-only branch rules.
- Publish to TestPyPI and PyPI from a separate workflow triggered by
  `release.published`.
- Use PyPI Trusted Publishing instead of long-lived API tokens.

## Workflow
1. Dependabot opens scheduled update pull requests for `uv` and
   `github-actions`.
2. Repository automation enables auto-merge only for low-risk updates:
   - patch updates for direct development dependencies,
   - patch updates for GitHub Actions.
3. Runtime dependency updates and higher-risk updates remain manual review and
   merge.
4. Maintainer triggers the `Release` workflow from `main` when merged changes
   warrant a package release.
5. The workflow runs the release validation suite for releasable code and
   packaging surfaces.
   - Markdown link checks stay in the regular CI workflow and are not part of
     the release-cutting job.
6. Semantic-release updates `pyproject.toml`, `CHANGELOG.md`, and `uv.lock`,
   creates a release commit and tag, pushes them, and opens a published
   GitHub Release.
7. The `Publish PyPI` workflow rebuilds artifacts from the release tag, runs
   `twine check`, publishes to TestPyPI, and then publishes to PyPI after
   environment approval.

## Rationale
- Dependency freshness improves while preserving explicit release control.
- Auto-merge is constrained to low-risk patch classes to reduce regression risk.
- Release creation remains explicit and auditable.
- PyPI credentials stay isolated to the publish workflow.
- Trusted Publishing removes token rotation burden and narrows credential risk.
- Building from the release tag ensures published artifacts match the tagged
  source, not the mutable state of the release-cutting job workspace.
- An explicit source manifest keeps documentation, benchmarks, tests, and
  repository automation files out of the source distribution.

## Consequences
- Commits intended for `main` must use Conventional Commits.
- Dependency update pull requests merged with `chore(...)` commit prefixes will
  not trigger semantic-release version bumps.
- Maintainers must run the manual `Release` workflow when dependency updates are
  intended for published distribution.
- The repository must configure pending Trusted Publishers on TestPyPI and PyPI.
- The repository should enforce required checks including dependency review and
  core CI status checks before merge.
- The package license is MIT, but the default runtime-downloaded embedding
  model can carry different terms and must be documented separately.
