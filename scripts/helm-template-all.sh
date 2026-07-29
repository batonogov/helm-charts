#!/usr/bin/env sh
set -eu

if ! command -v helm >/dev/null 2>&1; then
  echo "helm is required. Install it with: brew install helm" >&2
  exit 1
fi

kube_version=1.32.0

for chart in charts/*; do
  if [ -f "$chart/Chart.yaml" ]; then
    chart_name=$(basename "$chart")
    test_values="$chart/ci/test-values.yaml"
    if [ -f "$test_values" ]; then
      helm template "test-$chart_name" "$chart" --kube-version "$kube_version" -f "$test_values" >/dev/null
      for profile_values in "$chart"/ci/*-values.yaml; do
        if [ -f "$profile_values" ] && [ "$profile_values" != "$test_values" ]; then
          profile_name=$(basename "$profile_values" -values.yaml)
          helm template "test-$chart_name-$profile_name" "$chart" --kube-version "$kube_version" -f "$profile_values" >/dev/null
        fi
      done
    else
      helm template "test-$chart_name" "$chart" --kube-version "$kube_version" >/dev/null
    fi
  fi
done
