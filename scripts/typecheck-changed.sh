#!/usr/bin/env bash
set -euo pipefail

BASE_REF="${1:-${MYPY_BASE_REF:-}}"

if [[ -n "${BASE_REF}" ]] && git rev-parse --verify "${BASE_REF}" >/dev/null 2>&1; then
  diff_args=("${BASE_REF}...HEAD")
else
  diff_args=("HEAD")
fi

changed_files_raw="$(
  {
    git diff --name-only --diff-filter=ACMR "${diff_args[@]}" -- 'src/**/*.py' 'src/*.py'
    git ls-files --others --exclude-standard -- 'src/**/*.py' 'src/*.py'
  } | awk 'NF' | sort -u
)"

if [[ -z "${changed_files_raw}" ]]; then
  echo "No changed Python modules under src."
  exit 0
fi

# Source paths in this repository are space-free.
# shellcheck disable=SC2206
changed_files=(${changed_files_raw})
uv run mypy "${changed_files[@]}"
