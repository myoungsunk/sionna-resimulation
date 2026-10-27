#!/usr/bin/env bash
set -euo pipefail
: "${DS_REPO_ROOT:?export DS_REPO_ROOT}" "${DS_SOURCE_ROOT:?export DS_SOURCE_ROOT}" \
  "${DS_ARTIFACTS_ROOT:?export DS_ARTIFACTS_ROOT}" "${DS_OUTPUT_ROOT:?export DS_OUTPUT_ROOT}"
args=(--repo-root "$DS_REPO_ROOT" --source-root "$DS_SOURCE_ROOT" \
      --artifacts-root "$DS_ARTIFACTS_ROOT" --output-root "$DS_OUTPUT_ROOT")
python -m pytest -q tests
python run.py "${args[@]}" --step preflight
for stage in 1 2 3 4 5 6; do
  python run.py "${args[@]}" --step "$stage"
done
