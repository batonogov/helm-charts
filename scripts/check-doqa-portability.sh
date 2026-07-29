#!/usr/bin/env sh
set -eu

if ! command -v helm >/dev/null 2>&1; then
  echo "helm is required. Install it with: brew install helm" >&2
  exit 1
fi

chart=charts/doqa
kube_version=1.32.0

fail() {
  echo "DoQA portability check failed: $1" >&2
  exit 1
}

assert_contains() {
  rendered=$1
  expected=$2
  message=$3
  printf '%s\n' "$rendered" | grep -Fq -- "$expected" || fail "$message"
}

assert_not_contains() {
  rendered=$1
  unexpected=$2
  message=$3
  if printf '%s\n' "$rendered" | grep -Fq -- "$unexpected"; then
    fail "$message"
  fi
}

external_render=$(helm template test-doqa-external "$chart" \
  --kube-version "$kube_version" \
  -f "$chart/ci/external-values.yaml")

assert_contains "$external_render" \
  'image: "registry.example.com/doqa-mirror/service/nginx:1.23.3-alpine"' \
  "fully qualified nginx mirror repository was changed"
assert_contains "$external_render" \
  'image: "registry.example.com/doqa-mirror/service/soketi:16-alpine"' \
  "fully qualified Soketi mirror repository was changed"
assert_not_contains "$external_render" \
  'registry.control.doqa.app/registry.example.com/doqa-mirror/service/nginx' \
  "global registry was prepended to the nginx mirror"
assert_not_contains "$external_render" \
  'registry.control.doqa.app/registry.example.com/doqa-mirror/service/soketi' \
  "global registry was prepended to the Soketi mirror"

minio_render=$(helm template test-doqa "$chart" \
  --kube-version "$kube_version" \
  -f "$chart/ci/test-values.yaml" \
  --show-only templates/minio.yaml)
minio_job=$(printf '%s\n' "$minio_render" | awk '
  /^kind: Job$/ { in_job = 1 }
  in_job { print }
')

assert_contains "$minio_job" \
  'serviceAccountName: test-doqa' \
  "bucket-init Job does not use the configured ServiceAccount"
assert_contains "$minio_job" \
  'deployment-profile: in-tree' \
  "bucket-init Job does not use global pod labels"
assert_contains "$minio_job" \
  'kubernetes.io/os: linux' \
  "bucket-init Job does not use global nodeSelector"
assert_contains "$minio_job" \
  'type: RuntimeDefault' \
  "bucket-init Job does not use the client pod security context"
assert_contains "$minio_job" \
  'cpu: 10m' \
  "bucket-init Job does not render client resource requests"

service_account_render=$(helm template test-doqa "$chart" \
  --kube-version "$kube_version" \
  -f "$chart/ci/test-values.yaml" \
  --show-only templates/serviceaccount.yaml)
assert_contains "$service_account_render" \
  'example.com/owner: platform' \
  "chart-managed ServiceAccount annotations are missing"
