#!/usr/bin/env sh
set -eu

if ! command -v helm-docs >/dev/null 2>&1; then
  echo "helm-docs is required. Install it with: brew install helm-docs" >&2
  exit 1
fi

helm-docs --chart-search-root charts

if ! git diff --quiet -- 'charts/**/README.md'; then
  echo "helm-docs output is out of sync. Review and stage the regenerated README.md files." >&2
  git diff -- 'charts/**/README.md'
  exit 1
fi
