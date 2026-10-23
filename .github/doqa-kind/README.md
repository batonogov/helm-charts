# DoQA live integration tests

The `doqa-kind` workflow complements lint/render checks with real Kubernetes
installations. Each scenario has its own disposable kind cluster, kubeconfig
and CNPG operator. No external cluster, application license or repository
secret is required. Tool/operator versions and the Kubernetes image digest are
pinned in `versions.env`; the operator manifest and tool downloads are verified
with SHA256.

## Scenarios

- **Fresh**: package the current chart, install the `.tgz`, wait for every
  Deployment and CNPG, exercise frontend/API through nginx, validate the FPM
  override and check container stability. Write and read PostgreSQL, Laravel
  cache and MinIO sentinels, including the public object route through nginx.
- **Upgrade**: select the latest published stable release tagged `doqa-*`,
  independently of releases for other charts. Verify the release asset using
  its GitHub SHA256 digest, install it, write sentinels and snapshot hashes of
  Secret data, PVC UIDs and effective Laravel state prefixes. Upgrade using the
  same original override file and the candidate archive, then repeat checks
  and compare the snapshot. Same-version upgrades are covered when only
  repository files changed. A candidate older than the baseline is rejected.

The baseline version, asset URL and checksum are saved in diagnostics, making
the exact tested upgrade path visible. New releases automatically advance the
baseline; the workflow is not permanently tied to version 0.9.0.

`values.yaml` uses kind's `standard` StorageClass and one replica/consumer for
the main replicated services. It disables Ingress and TLS; checks reach the
internal nginx Service. MinIO/mc use the vendor images on empty CI storage,
identically on both sides of an upgrade. Default MinIO image availability,
Ingress controllers, certificate issuance, HA/failover, backup/restore and
licensed user workflows are outside this test's scope. The optional Telegram
bot is not enabled. Successful readiness is supplemented by HTTP/data checks;
it does not imply that every licensed business operation was exercised.

## CI and merge checks

The workflow runs on pull requests and via `workflow_dispatch`. A cheap job
detects changes to DoQA, this workflow, its fixtures or scripts. Only relevant
changes start the fresh/upgrade matrix. The final **DoQA integration** check
always runs, so it can be selected as a required branch/ruleset check without
leaving unrelated PRs pending. Repository administrators must configure that
requirement separately. This workflow does not change release permissions or
publish charts.

Each matrix job has a 45-minute limit. Diagnostics are collected before cleanup
and retained for seven days: resource status, events, bounded current/previous
container logs and non-secret result/baseline metadata. Secret contents,
kubeconfig and rendered Helm manifests are excluded. Logs have known Secret
values redacted; logs are skipped if redaction cannot be prepared. The test
deletes only the kind cluster it created.

## Local reproduction

Requirements: Docker, Python 3.9+, Helm 3.22.1, curl and network access to GitHub,
Kubernetes binaries and container registries. Linux amd64 matches CI and the
vendor application images. Setup also supports macOS arm64 tools, but running
the amd64 application images requires working container emulation.

From the repository root, use a unique cluster name and fresh working directory:

```bash
export DOQA_KIND_NAME=doqa-live-local
export DOQA_KIND_WORK="$PWD/.tmp/doqa-kind-local"
export KUBECONFIG="$DOQA_KIND_WORK/kubeconfig"
export HELM_PLUGINS="$DOQA_KIND_WORK/helm-plugins"
export PATH="$DOQA_KIND_WORK/bin:$PATH"
bash scripts/doqa-kind/setup.sh
python3 scripts/doqa-kind/check.py fresh
python3 scripts/doqa-kind/diagnostics.py
kind delete cluster --name "$DOQA_KIND_NAME"
```

Run `upgrade` instead of `fresh` in another new cluster to reproduce the upgrade
scenario. `GH_TOKEN` is optional locally and only used to avoid GitHub API rate
limits when resolving published releases. Always run diagnostics and cleanup
after a failed local test as well.

The design follows the separation of lint and kind integration checks used by
[Prometheus Community](https://github.com/prometheus-community/helm-charts/blob/main/.github/workflows/ci.yaml)
and [Grafana](https://github.com/grafana/helm-charts/blob/main/.github/workflows/lint-test.yaml).
DoQA uses an explicit integration script rather than installing every `ci/`
profile through `ct install`: existing profiles include render-only external
endpoints, and live checks need CNPG setup and state-preservation assertions.
