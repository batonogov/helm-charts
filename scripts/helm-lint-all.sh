#!/usr/bin/env sh
set -eu

if ! command -v helm >/dev/null 2>&1; then
  echo "helm is required. Install it with: brew install helm" >&2
  exit 1
fi

for chart in charts/*; do
  if [ -f "$chart/Chart.yaml" ]; then
    linted=false
    for profile_values in "$chart"/ci/*-values.yaml; do
      if [ -f "$profile_values" ]; then
        helm lint "$chart" -f "$profile_values"
        linted=true
      fi
    done
    if [ "$linted" = false ]; then
      helm lint "$chart"
    fi
  fi
done
