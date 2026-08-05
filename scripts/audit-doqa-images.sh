#!/usr/bin/env sh
# Audit DoQA vendor application images for compatibility between two chart
# states. For every component whose image tag changed, fetches the image
# configs (no layer download) and reports differences in Env, Entrypoint,
# and Cmd — the things that decide whether the chart still wires the image
# correctly (e.g. a newly required env var or a changed startup command).
#
# Use this when bumping appVersion: it answers "did the vendor add an env
# var or change how a service starts that the chart does not account for?"
# without installing anything. It complements diffing configs_<ver>.zip,
# which shows vendor config changes but not what a rebuilt image itself
# expects at runtime.
#
# Usage:
#   scripts/audit-doqa-images.sh <old_values.yaml> <new_values.yaml>
#
# Typical invocation compares the chart on main with a version-bump branch:
#   git show main:charts/doqa/values.yaml > /tmp/old.yaml
#   git show <branch>:charts/doqa/values.yaml > /tmp/new.yaml
#   scripts/audit-doqa-images.sh /tmp/old.yaml /tmp/new.yaml
#
# Requires crane (brew install crane) and jq. The vendor registry
# registry.control.doqa.app serves application images anonymously, so no
# credentials are needed.
#
# Exit status: 0 if no image-contract differences were found across the
# changed tags, 1 if any Env/Entrypoint/Cmd difference (or a fetch failure)
# was reported.
set -eu

require() {
  command -v "$1" >/dev/null 2>&1 || { echo "$1 is required. $2" >&2; exit 1; }
}
require crane "Install it with: brew install crane"
require jq "Install it with: brew install jq"

OLD_VALUES="${1:?usage: audit-doqa-images.sh <old_values.yaml> <new_values.yaml>}"
NEW_VALUES="${2:?usage: audit-doqa-images.sh <old_values.yaml> <new_values.yaml>}"

REGISTRY="registry.control.doqa.app"
# DoQA application repositories exactly as they appear under image.repository
# in values.yaml (the doqa/ namespace is part of the registry path). Vendor
# infrastructure images (nginx, soketi) are chart-pinned, not app-versioned,
# and are intentionally excluded.
REPOSITORIES="
doqa/doqa-backend
doqa/doqa-frontend
doqa/doqa-parsing-autotests
doqa/doqa-autotest-result-parser
doqa/doqa-statistic
doqa/doqa-notify
doqa/doqa-llm
doqa/doqa-telegram-bot
"

# Print the tag value of the image block whose repository: line equals $2.
# values.yaml groups repository: and tag: under each component's image: block.
tag_for() {
  awk -v repo="$2" '
    $0 ~ "repository:[[:space:]]+" repo "([[:space:]]|$)" { found = 1; next }
    found && /tag:/ { sub(/.*tag:[[:space:]]*/, ""); gsub(/[[:space:]]/, ""); print; exit }
  ' "$1"
}

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

status=0
for repo in $REPOSITORIES; do
  old_tag="$(tag_for "$OLD_VALUES" "$repo")"
  new_tag="$(tag_for "$NEW_VALUES" "$repo")"
  if [ -z "$old_tag" ] || [ -z "$new_tag" ]; then
    echo "skip  $repo (tag not found in one of the values files)"
    continue
  fi
  if [ "$old_tag" = "$new_tag" ]; then
    echo "ok    $repo ($old_tag unchanged)"
    continue
  fi
  printf 'diff  %s: %s -> %s\n' "$repo" "$old_tag" "$new_tag"
  if crane config "$REGISTRY/$repo:$old_tag" >"$WORK_DIR/old.json" 2>/dev/null \
    && crane config "$REGISTRY/$repo:$new_tag" >"$WORK_DIR/new.json" 2>/dev/null; then
    jq -r '.config.Env[]?' "$WORK_DIR/old.json" | sort >"$WORK_DIR/old.txt"
    jq -r '.config.Env[]?' "$WORK_DIR/new.json" | sort >"$WORK_DIR/new.txt"
    env_diff="$(diff "$WORK_DIR/old.txt" "$WORK_DIR/new.txt" || true)"
    jq -c '[.config.Entrypoint, .config.Cmd]' "$WORK_DIR/old.json" >"$WORK_DIR/old.txt"
    jq -c '[.config.Entrypoint, .config.Cmd]' "$WORK_DIR/new.json" >"$WORK_DIR/new.txt"
    cmd_diff="$(diff "$WORK_DIR/old.txt" "$WORK_DIR/new.txt" || true)"
    if [ -n "$env_diff" ]; then
      echo "      ENV (changed):"
      printf '%s\n' "$env_diff" | sed 's/^/        /'
      status=1
    fi
    if [ -n "$cmd_diff" ]; then
      echo "      CMD/ENTRYPOINT (changed):"
      printf '%s\n' "$cmd_diff" | sed 's/^/        /'
      status=1
    fi
    if [ -z "$env_diff" ] && [ -z "$cmd_diff" ]; then
      echo "      no env/cmd/entrypoint changes"
    fi
  else
    echo "      could not fetch one of the image configs (network error or tag missing)"
    status=1
  fi
done

echo
if [ "$status" -eq 0 ]; then
  echo "RESULT: no image-contract differences (env/cmd/entrypoint) across changed tags."
else
  echo "RESULT: differences listed above — review before bumping appVersion."
fi
exit "$status"
