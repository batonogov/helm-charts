#!/usr/bin/env sh
# Audit DoQA vendor application images for compatibility between two chart
# states. For every component whose image tag changed, fetches the image
# configs (no layer download) and reports differences in Env, Entrypoint,
# Cmd, User, and WorkingDir — the things that decide whether the chart still
# wires the image correctly (e.g. a newly required env var or a changed startup command).
#
# Use this when bumping appVersion: it answers "did the vendor add an env
# var, runtime user, working directory or startup command the chart does not account for?"
# without pulling image layers. It complements diffing configs_<ver>.zip,
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
# Requires crane (brew install crane), jq, and Python 3 with PyYAML
# (python3 -m pip install PyYAML==6.0.3). The vendor registry
# registry.control.doqa.app serves application images anonymously, so no
# credentials are needed.
#
# Exit status: 0 if repository/tag validation passed and no image-contract
# differences were found across changed tags, 1 for an invalid values inventory,
# a missing tag, an image-contract difference, or a fetch failure.
set -eu

require() {
  command -v "$1" >/dev/null 2>&1 || { echo "$1 is required. $2" >&2; exit 1; }
}
require crane "Install it with: brew install crane"
require jq "Install it with: brew install jq"
require python3 "Install Python 3 before running this audit"
if ! python3 -c 'import yaml' >/dev/null 2>&1; then
  echo "PyYAML is required. Install it with: python3 -m pip install PyYAML==6.0.3" >&2
  exit 1
fi

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
doqa/doqa-statistic
doqa/doqa-notify
doqa/doqa-llm
doqa/doqa-telegram-bot
"
INFRASTRUCTURE_REPOSITORIES="
docker.io/redis
docker.io/rabbitmq
quay.io/minio/minio
quay.io/minio/mc
service/soketi
service/nginx
"

image_inventory() {
  python3 - "$1" <<'PY'
import sys

import yaml

path = sys.argv[1]
try:
    with open(path, encoding="utf-8") as source:
        document = yaml.safe_load(source)
except (OSError, UnicodeError, yaml.YAMLError) as error:
    raise SystemExit(f"{path}: cannot parse values YAML: {error}")
if not isinstance(document, dict):
    raise SystemExit(f"{path}: values root must be a mapping")

images = {}
visited = set()


def visit(node):
    if not isinstance(node, (dict, list)):
        return
    identity = id(node)
    if identity in visited:
        return
    visited.add(identity)
    if isinstance(node, dict):
        if "image" in node:
            image = node["image"]
            if not isinstance(image, dict):
                raise ValueError("image must be a mapping")
            if "repository" in image or "tag" in image:
                repository = image.get("repository")
                tag = image.get("tag")
                if not isinstance(repository, str) or not repository.strip():
                    raise ValueError("image repository must be a nonempty string")
                if not isinstance(tag, str) or not tag.strip():
                    raise ValueError(f"tag not found or invalid for image repository {repository}")
                if repository in images and images[repository] != tag:
                    raise ValueError(f"conflicting tags for image repository {repository}")
                images[repository] = tag
        for value in node.values():
            visit(value)
    else:
        for value in node:
            visit(value)


try:
    visit(document)
except ValueError as error:
    raise SystemExit(f"{path}: {error}")
for repository, tag in sorted(images.items()):
    print(f"{repository}\t{tag}")
PY
}

repositories_in() {
  cut -f1 "$1"
}

contains() {
  case "
$1
" in
    *"
$2
"*) return 0 ;;
    *) return 1 ;;
  esac
}

check_repositories() {
  values="$1"
  actual="$(repositories_in "$2")"
  for repo in $actual; do
    if ! contains "$REPOSITORIES" "$repo" && ! contains "$INFRASTRUCTURE_REPOSITORIES" "$repo"; then
      echo "error $values: unknown image repository $repo" >&2
      status=1
    fi
  done
  for repo in $REPOSITORIES; do
    if ! contains "$actual" "$repo"; then
      echo "error $values: missing DoQA application image repository $repo" >&2
      status=1
    fi
  done
}

tag_for() {
  awk -F '\t' -v repo="$2" '$1 == repo { print $2; exit }' "$1"
}

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT
image_inventory "$OLD_VALUES" >"$WORK_DIR/old.inventory"
image_inventory "$NEW_VALUES" >"$WORK_DIR/new.inventory"

status=0
check_repositories "$OLD_VALUES" "$WORK_DIR/old.inventory"
check_repositories "$NEW_VALUES" "$WORK_DIR/new.inventory"
for repo in $REPOSITORIES; do
  old_tag="$(tag_for "$WORK_DIR/old.inventory" "$repo")"
  new_tag="$(tag_for "$WORK_DIR/new.inventory" "$repo")"
  if [ -z "$old_tag" ] || [ -z "$new_tag" ]; then
    echo "error $repo (tag not found in one of the values files)" >&2
    status=1
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
    jq -c '[.config.User // "", .config.WorkingDir // ""]' "$WORK_DIR/old.json" >"$WORK_DIR/old.txt"
    jq -c '[.config.User // "", .config.WorkingDir // ""]' "$WORK_DIR/new.json" >"$WORK_DIR/new.txt"
    identity_diff="$(diff "$WORK_DIR/old.txt" "$WORK_DIR/new.txt" || true)"
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
    if [ -n "$identity_diff" ]; then
      echo "      USER/WORKDIR (changed):"
      printf '%s\n' "$identity_diff" | sed 's/^/        /'
      status=1
    fi
    if [ -z "$env_diff" ] && [ -z "$cmd_diff" ] && [ -z "$identity_diff" ]; then
      echo "      no env/cmd/entrypoint/user/workdir changes"
    fi
  else
    echo "      could not fetch one of the image configs (network error or tag missing)"
    status=1
  fi
done

echo
if [ "$status" -eq 0 ]; then
  echo "RESULT: no image-contract differences (env/cmd/entrypoint/user/workdir) across changed tags."
else
  echo "RESULT: audit failed or differences listed above — review before bumping appVersion."
fi
exit "$status"
