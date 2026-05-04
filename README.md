# batonogov helm charts

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
brew install helm helm-docs chart-testing kind
# regenerate chart README from values.yaml
helm-docs --chart-search-root charts
# run local chart smoke tests (lint, render with ci/test-values.yaml, package)
bash scripts/helm-smoke-test.sh
# verify release-affecting chart edits bumped Chart.yaml version
bash scripts/check-chart-version-bumps.sh origin/main
# lint a chart locally
ct lint --config .github/ct.yaml --target-branch main
# render templates
helm template my-release charts/doqa -f charts/doqa/ci/test-values.yaml
```

## CI

- `lint-test.yaml` (PR to `main` or manual run): detects changed charts, verifies required chart version bumps, runs `ct lint`, runs `bash scripts/helm-smoke-test.sh` for explicit lint/render/package coverage, and verifies generated `helm-docs` output is committed.
- `release.yaml` (push to `main`): publishes new chart versions to the `gh-pages` branch with [chart-releaser-action](https://github.com/helm/chart-releaser-action). Release jobs are serialized per branch to avoid concurrent index updates.
- `renovate.json`: configures Renovate to update `xray-health-exporter` from GHCR image tags, bump the chart patch `version`, and keep generated README badges aligned. Enable the Renovate GitHub App for this repository to run it.

## Contributing

Open a pull request against `main`. Bump the `version:` in `Chart.yaml` of any chart with release-affecting changes — CI enforces this for templates, values, chart metadata, packaged files, and generated chart README changes. `chart-releaser-action` only publishes versions that haven't been released yet.

## License

See [LICENSE](LICENSE).
