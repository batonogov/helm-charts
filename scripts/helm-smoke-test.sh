#!/usr/bin/env bash
set -euo pipefail

if ! command -v helm >/dev/null 2>&1; then
  echo "helm is required" >&2
  exit 127
fi

charts=("$@")
if [[ ${#charts[@]} -eq 0 ]]; then
  charts=()
  while IFS= read -r chart; do
    charts+=("$chart")
  done < <(find charts -mindepth 2 -maxdepth 2 -name Chart.yaml -print | sed 's#/Chart.yaml$##' | sort)
fi

if [[ ${#charts[@]} -eq 0 ]]; then
  echo "no charts found" >&2
  exit 1
fi

tmp_dir="${TMPDIR:-/tmp}/helm-chart-smoke"
mkdir -p "$tmp_dir"

for chart in "${charts[@]}"; do
  if [[ ! -f "$chart/Chart.yaml" ]]; then
    echo "not a chart directory: $chart" >&2
    exit 1
  fi

  name="$(basename "$chart")"
  release="ci-$name"
  rendered="$tmp_dir/$name.yaml"
  values_file="$chart/ci/test-values.yaml"
  value_args=()

  if [[ -f "$values_file" ]]; then
    value_args+=(--values "$values_file")
  fi

  echo "==> helm lint $chart"
  helm lint "$chart" "${value_args[@]}"

  echo "==> helm template $chart"
  helm template "$release" "$chart" "${value_args[@]}" --debug > "$rendered"

  echo "==> helm package $chart"
  helm package "$chart" --destination "$tmp_dir" >/dev/null
done
