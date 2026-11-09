# batonogov helm charts

[![Artifact Hub](https://img.shields.io/endpoint?url=https://artifacthub.io/badge/repository/batonogov)](https://artifacthub.io/packages/search?repo=batonogov)
[![lint-test](https://github.com/batonogov/helm-charts/actions/workflows/lint-test.yaml/badge.svg)](https://github.com/batonogov/helm-charts/actions/workflows/lint-test.yaml)
[![release](https://github.com/batonogov/helm-charts/actions/workflows/release.yaml/badge.svg)](https://github.com/batonogov/helm-charts/actions/workflows/release.yaml)
[![License](https://img.shields.io/github/license/batonogov/helm-charts)](LICENSE)

Helm chart catalog. Charts published to GitHub Pages via [chart-releaser-action](https://github.com/helm/chart-releaser-action) on every push to `main`.

## Usage

```bash
helm repo add batonogov https://batonogov.github.io/helm-charts
helm repo update
helm search repo batonogov
```

## Charts

| Name | Description |
|---|---|
| [doqa](charts/doqa) | DoQA Test Case Management System (TCMS) self-hosted |
| [xray-health-exporter](charts/xray-health-exporter) | Prometheus exporter for Xray-core tunnel health |

## Repository conventions

- Each chart lives in its own directory under `charts/<name>/`.
- Each chart is versioned independently per semver. Release tags are prefixed with the chart name, e.g. `doqa-0.1.0`.
- `charts/<name>/README.md` is generated from `values.yaml` + `README.md.gotmpl` by [helm-docs](https://github.com/norwoodj/helm-docs). CI fails if it gets out of sync.
- Helm v3.14+ or Helm v4 is supported.

## Local development

```bash
brew install helm helm-docs chart-testing kind pre-commit
# install local git hooks
pre-commit install
# regenerate chart README from values.yaml
helm-docs --chart-search-root charts
# lint a chart locally
ct lint --config .github/ct.yaml --target-branch main
# render templates
helm template my-release charts/doqa -f charts/doqa/ci/test-values.yaml
# run the same local checks as the git hooks
pre-commit run --all-files
```

## Pre-commit hooks

Install hooks once to run checks automatically on commit:

```bash
pre-commit install
```

Run all hooks manually before pushing:

```bash
pre-commit run --all-files
```

Update pinned remote hook versions periodically:

```bash
pre-commit autoupdate
pre-commit run --all-files
```

## CI

- `lint-test.yaml` (PR to `main` or manual run): detects changed charts, runs `ct lint` with chart version increment checks, and verifies generated `helm-docs` output is committed. Its required status check is `lint`.
- `doqa-kind.yaml` (PR or manual run): tests the packaged DoQA chart in disposable kind clusters. Separate jobs cover a fresh installation, an upgrade from the latest published stable DoQA chart, and an explicit-baseline upgrade from published `0.10.0` to the candidate with explicit generated Secret names. The `DoQA integration` check reports success for unrelated changes without starting a cluster. See [live test setup and scope](.github/doqa-kind/README.md).
- `xray-kind.yaml` (PR or manual run): installs xray-health-exporter in a disposable kind cluster, checks the real HTTP `/health` endpoint, and verifies leader election with two replicas. Its `xray integration` check reports success for unrelated changes without starting a cluster.
- `release.yaml` (push to `main`): runs repository validation, rejects changed charts whose current version is already tagged, and publishes new chart versions to the `gh-pages` branch with [chart-releaser-action](https://github.com/helm/chart-releaser-action). Release jobs are serialized per branch to avoid concurrent index updates.
- `renovate.json`: configures Renovate to update `xray-health-exporter` from GHCR image tags, bump the chart patch `version`, and keep generated README badges aligned. Enable the Renovate GitHub App for this repository to run it.

Configure the repository's required pull-request checks as `lint`, `DoQA integration`, and `xray integration`. The two integration aggregates always report a result, including for unrelated changes.

## Signed releases

New releases are signed with an OpenPGP key. The release workflow requires the
following repository Actions settings before it can publish (including the first
push after this workflow change is merged):

| Type | Name | Value |
|---|---|---|
| Secret | `GPG_PRIVATE_KEY` | ASCII-armored private signing key |
| Secret | `GPG_PASSPHRASE` | Nonempty passphrase protecting that key |
| Variable | `GPG_KEY_NAME` | Exact key user ID, such as `Chart Releases <releases@example.com>` |
| Variable | `GPG_KEY_FINGERPRINT` | Full 40-character primary key fingerprint, without spaces |

Generate a dedicated RSA signing key using `gpg --full-generate-key` (RSA 4096,
signing capability, a strong passphrase, and an appropriate expiration date).
Inspect its fingerprint with `gpg --list-secret-keys --keyid-format long`.
Export the private key directly into GitHub Secrets from a trusted machine:

```bash
# Replace FINGERPRINT with the full fingerprint of the release key.
gpg --armor --export-secret-keys FINGERPRINT |
  gh secret set GPG_PRIVATE_KEY --repo batonogov/helm-charts
gh secret set GPG_PASSPHRASE --repo batonogov/helm-charts
gh variable set GPG_KEY_NAME --repo batonogov/helm-charts --body 'Chart Releases <releases@example.com>'
gh variable set GPG_KEY_FINGERPRINT --repo batonogov/helm-charts --body FINGERPRINT
gpg --armor --export FINGERPRINT > helm-signing-key.asc
```

Publish `helm-signing-key.asc` at a stable HTTPS URL and announce the fingerprint
through a trusted channel before the first signed release. Retain old public keys
when rotating keys so users can verify historical packages. Never commit the
private key or passphrase. The workflow stops if settings are missing, the selected
key is unavailable, or a signed test package fails verification; it does not fall
back to unsigned publication. Temporary private material is removed even on failure.

Chart Releaser uploads `<chart>-<version>.tgz.prov` alongside each new `.tgz` in
GitHub Releases. Artifact Hub detects the provenance file during indexing and
shows **Signed** for that version. Existing releases are not modified; a chart's
next new version will receive a signature. This repository-only change does not
bump chart versions. The **Signed** badge indicates signature availability, not a
security audit or verification of the container images.

Users can download the published public key, check its fingerprint against the
announced value, and verify a signed chart:

```bash
gpg --show-keys --with-fingerprint helm-signing-key.asc
gpg --dearmor < helm-signing-key.asc > helm-signing-key.gpg
helm pull batonogov/doqa --version VERSION --verify --keyring ./helm-signing-key.gpg
# Or add --verify --keyring ./helm-signing-key.gpg to helm install.
```

See [Helm provenance](https://helm.sh/docs/v3/topics/provenance/) and
[Artifact Hub's signing-key annotation](https://artifacthub.io/docs/topics/annotations/helm/).
Once the public-key URL and fingerprint are established, chart metadata can also
include `artifacthub.io/signKey` to expose them in Artifact Hub.

## Chart updates

The project skill [`update-helm-charts`](.agents/skills/update-helm-charts/SKILL.md) covers the full lifecycle: upstream discovery, compatibility audit, updates, iterative review and fixes, a PR with green CI, merge, and verification of the published release and Helm index. In Empryo, load it from `/skills` and request the full update cycle. It follows `AGENTS.md` and automates commits, push, PR updates, merge, and publication verification without per-stage confirmation prompts, subject to active tool approval gates. Required checks, reviews, and branch protection are never bypassed.

## Contributing

Open a pull request against `main`. Bump the `version:` in `Chart.yaml` of any chart with release-affecting changes — CI enforces this for templates, values, chart metadata, packaged files, and generated chart README changes. `chart-releaser-action` only publishes versions that haven't been released yet.

## License

See [LICENSE](LICENSE).
