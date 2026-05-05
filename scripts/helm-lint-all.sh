#!/usr/bin/env sh
set -eu

if ! command -v helm >/dev/null 2>&1; then
  echo "helm is required. Install it with: brew install helm" >&2
  exit 1
fi

for chart in charts/*; do
  if [ -f "$chart/Chart.yaml" ]; then
    helm lint "$chart"
  fi
done
