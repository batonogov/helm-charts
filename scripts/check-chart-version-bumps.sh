#!/usr/bin/env bash
set -euo pipefail

base_ref="${1:-${BASE_REF:-origin/main}}"

if ! git rev-parse --verify "$base_ref" >/dev/null 2>&1; then
  echo "base ref not found: $base_ref" >&2
  exit 1
fi

chart_version_from_stdin() {
  awk '
    /^[[:space:]]*version[[:space:]]*:/ {
      sub(/^[^:]*:[[:space:]]*/, "")
      sub(/[[:space:]]+#.*$/, "")
      gsub(/^[ "]+|[ "]+$/, "")
      print
      exit
    }
  '
}

chart_version_from_file() {
  chart_version_from_stdin < "$1"
}

parse_semver_core() {
  local version="${1%%+*}"
  version="${version%%-*}"

  local major minor patch extra
  IFS=. read -r major minor patch extra <<< "$version"

  if [[ -n "${extra:-}" ]] ||
    [[ ! "$major" =~ ^[0-9]+$ ]] ||
    [[ ! "$minor" =~ ^[0-9]+$ ]] ||
    [[ ! "$patch" =~ ^[0-9]+$ ]]; then
    return 1
  fi

  printf '%s %s %s\n' "$major" "$minor" "$patch"
}

semver_core_gt() {
  local current="$1"
  local previous="$2"
  local current_parts previous_parts

  current_parts="$(parse_semver_core "$current")" || return 2
  previous_parts="$(parse_semver_core "$previous")" || return 2

  local current_major current_minor current_patch
  local previous_major previous_minor previous_patch
  read -r current_major current_minor current_patch <<< "$current_parts"
  read -r previous_major previous_minor previous_patch <<< "$previous_parts"

  if (( current_major != previous_major )); then
    if (( current_major > previous_major )); then
      return 0
    fi
    return 1
  fi

  if (( current_minor != previous_minor )); then
    if (( current_minor > previous_minor )); then
      return 0
    fi
    return 1
  fi

  if (( current_patch > previous_patch )); then
    return 0
  fi
  return 1
}

is_release_affecting_chart_file() {
  local rel="$1"

  case "$rel" in
    Chart.yaml | values.yaml | values.schema.json | README.md | README.md.gotmpl | .helmignore)
      return 0
      ;;
    templates/* | crds/* | files/*)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

add_unique_chart() {
  local chart="$1"
  local existing

  for existing in "${affected_charts[@]:-}"; do
    [[ -n "$existing" ]] || continue
    [[ "$existing" == "$chart" ]] && return
  done

  affected_charts+=("$chart")
  affected_count=$((affected_count + 1))
}

changed_files="$(
  {
    git diff --name-only "$base_ref"...HEAD
    git diff --name-only
    git diff --name-only --cached
    git ls-files --others --exclude-standard
  } | sort -u
)"

affected_charts=()
affected_count=0
while IFS= read -r file; do
  [[ -n "$file" ]] || continue
  [[ "$file" =~ ^charts/([^/]+)/(.+)$ ]] || continue

  chart="charts/${BASH_REMATCH[1]}"
  rel="${BASH_REMATCH[2]}"

  if is_release_affecting_chart_file "$rel"; then
    add_unique_chart "$chart"
  fi
done <<< "$changed_files"

if (( affected_count == 0 )); then
  echo "No release-affecting chart changes detected."
  exit 0
fi

failed=0
for chart in "${affected_charts[@]}"; do
  if [[ ! -f "$chart/Chart.yaml" ]]; then
    echo "Skipping removed chart: $chart"
    continue
  fi

  if ! git cat-file -e "$base_ref:$chart/Chart.yaml" 2>/dev/null; then
    echo "New chart detected, version bump check skipped: $chart"
    continue
  fi

  previous_version="$(git show "$base_ref:$chart/Chart.yaml" | chart_version_from_stdin)"
  current_version="$(chart_version_from_file "$chart/Chart.yaml")"

  if [[ -z "$previous_version" || -z "$current_version" ]]; then
    echo "::error file=$chart/Chart.yaml::Unable to read chart version"
    failed=1
    continue
  fi

  if semver_core_gt "$current_version" "$previous_version"; then
    echo "Version bump OK: $chart $previous_version -> $current_version"
  else
    echo "::error file=$chart/Chart.yaml::Release-affecting chart changes require version bump greater than $previous_version; current is $current_version"
    failed=1
  fi
done

exit "$failed"
