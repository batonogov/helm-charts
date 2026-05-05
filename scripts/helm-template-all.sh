#!/usr/bin/env sh
set -eu

if ! command -v helm >/dev/null 2>&1; then
  echo "helm is required. Install it with: brew install helm" >&2
  exit 1
fi

for chart in charts/*; do
  if [ -f "$chart/Chart.yaml" ]; then
    chart_name=$(basename "$chart")
    test_values="$chart/ci/test-values.yaml"
    if [ -f "$test_values" ]; then
      helm template "test-$chart_name" "$chart" -f "$test_values" >/dev/null
    else
      helm template "test-$chart_name" "$chart" >/dev/null
    fi
  fi
done
