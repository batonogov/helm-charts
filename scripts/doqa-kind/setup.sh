#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
source .github/doqa-kind/versions.env
: "${KUBECONFIG:?Set a dedicated KUBECONFIG for this disposable cluster}"
: "${DOQA_KIND_NAME:?Set a unique disposable kind cluster name}"
: "${DOQA_KIND_WORK:?Set a directory for tools and downloaded fixtures}"
mkdir -p "$DOQA_KIND_WORK/bin"
case "$(uname -s)-$(uname -m)" in
  Linux-x86_64) platform=linux; arch=amd64 ;;
  *) echo 'Live DoQA tests require a Linux amd64 host, matching the vendor images' >&2; exit 1 ;;
esac
download() { curl --fail --location --retry 3 --connect-timeout 20 --max-time 180 "$1" -o "$2"; }
verify() {
  python3 - "$1" "$2" <<'PY'
import hashlib, pathlib, sys
actual = hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest()
if actual != sys.argv[2].split()[0]:
    raise SystemExit(f"Checksum mismatch for {sys.argv[1]}")
PY
}
kind_url="https://github.com/kubernetes-sigs/kind/releases/download/$KIND_VERSION/kind-$platform-$arch"
download "$kind_url" "$DOQA_KIND_WORK/bin/kind"
download "$kind_url.sha256sum" "$DOQA_KIND_WORK/kind.sha256sum"
verify "$DOQA_KIND_WORK/bin/kind" "$(cat "$DOQA_KIND_WORK/kind.sha256sum")"
kubectl_url="https://dl.k8s.io/release/$KUBERNETES_VERSION/bin/$platform/$arch/kubectl"
download "$kubectl_url" "$DOQA_KIND_WORK/bin/kubectl"
download "$kubectl_url.sha256" "$DOQA_KIND_WORK/kubectl.sha256"
verify "$DOQA_KIND_WORK/bin/kubectl" "$(cat "$DOQA_KIND_WORK/kubectl.sha256")"
chmod +x "$DOQA_KIND_WORK/bin/kind" "$DOQA_KIND_WORK/bin/kubectl"
export PATH="$DOQA_KIND_WORK/bin:$PATH"
kind create cluster --name "$DOQA_KIND_NAME" --image "$KIND_NODE_IMAGE" --kubeconfig "$KUBECONFIG" --wait 180s
context="kind-$DOQA_KIND_NAME"
download "https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/v$CNPG_VERSION/releases/cnpg-$CNPG_VERSION.yaml" "$DOQA_KIND_WORK/cnpg.yaml"
verify "$DOQA_KIND_WORK/cnpg.yaml" "$CNPG_SHA256"
kubectl --context "$context" apply --server-side -f "$DOQA_KIND_WORK/cnpg.yaml"
kubectl --context "$context" wait --for=condition=Established crd/clusters.postgresql.cnpg.io --timeout=120s
kubectl --context "$context" -n cnpg-system rollout status deployment/cnpg-controller-manager --timeout=300s
