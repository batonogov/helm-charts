# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A monorepo of Helm charts published as a public Helm repository on GitHub Pages. Each chart lives in `charts/<name>/`, is versioned independently per semver, and is released via `chart-releaser-action`. The published index is served from `https://batonogov.github.io/helm-charts/index.yaml`; the actual `.tgz` packages are GitHub Release assets, not stored in `gh-pages`.

Currently shipped charts:
- `charts/doqa` — DoQA Test Case Management System (TCMS), self-hosted on Kubernetes 1.32+. Targets `appVersion 4.0.0-box`.
- `charts/xray-health-exporter` — Prometheus exporter for Xray-core tunnel health. Targets `appVersion 1.2.0`.

## Common commands

```bash
# Render a chart's templates (catch logic errors quickly)
helm lint charts/doqa
helm template my-release charts/doqa
helm template my-release charts/doqa -f charts/doqa/ci/test-values.yaml

# Run local smoke tests for all charts, or pass one or more chart paths.
bash scripts/helm-smoke-test.sh
bash scripts/helm-smoke-test.sh charts/doqa charts/xray-health-exporter

# Verify release-affecting chart edits bumped Chart.yaml version.
bash scripts/check-chart-version-bumps.sh origin/main

# Regenerate a chart's README.md from values.yaml + README.md.gotmpl.
# CI fails on PRs if the regenerated README differs from what's committed.
helm-docs --chart-search-root charts

# Lint with chart-testing (mirrors PR CI)
ct lint --config .github/ct.yaml --target-branch main
```

There are no unit tests — validation is the custom chart version bump check, `ct lint`, explicit Helm smoke tests (`helm lint`, `helm template` with `ci/test-values.yaml`, `helm package`), and a `helm-docs` sync check on PRs. End-to-end installation is verified manually against a real cluster.

## Release flow

A push to `main` triggers `.github/workflows/release.yaml` → `chart-releaser-action` packages every chart whose `version:` in `Chart.yaml` is not yet released, creates a GitHub Release per chart (tag format `<chart>-<version>`, e.g. `doqa-0.1.0`), and updates `gh-pages/index.yaml`. Charts with an unchanged version are skipped.

**Bump `version:` in the chart's `Chart.yaml` when shipping a release-affecting change** (templates, default values, `appVersion`, image tags, packaged files, README content). Don't bump for `ci/test-values.yaml` tweaks or repo-level files — that just churns release versions without giving users anything new. `ct.yaml` keeps `check-version-increment: false`; `scripts/check-chart-version-bumps.sh` enforces the narrower repository policy in CI.

The `gh-pages` branch must exist before the first release (one-time bootstrap). GitHub Pages settings must point to `gh-pages` / root.

## Chart authoring conventions

- `apiVersion: v2`, `kubeVersion: ">=1.32.0-0"` (target user clusters).
- `values.yaml` is annotated with helm-docs comments (`# -- description`); `helm-docs` regenerates `README.md` from `values.yaml` + `README.md.gotmpl`. Don't hand-edit `README.md`.
- Each chart bundles `ci/test-values.yaml` for reproducing the verified test deploy.
- **No bitnami sub-charts**, anywhere. For PostgreSQL use the CNPG operator (in-tree `Cluster` CR + external alternative). For Redis/RabbitMQ/MinIO/etc. use minimal in-tree Deployment+PVC templates (single replica, no HA — fine for the "newcomer onboarding" sub-chart-replacement role) plus an external alternative under a `<name>.create` flag. Default `create: true` so `helm install <chart>` from a fresh user produces a working stack.
- Adding a new chart: drop it under `charts/<new-name>/`. `ct list-changed` auto-detects on PR, lint-test workflow runs against it. No `Chart.lock` / `helm dep update` workflow — we don't ship sub-chart dependencies.

## Working with `.tmp/`

`.tmp/` is gitignored. Use it for ad-hoc recon during chart development — vendor binaries, extracted configs, manifest diffs. Don't commit anything from there.

## Architecture of `charts/doqa`

This chart deploys the full DoQA v4.0.0 stack — 14 Deployments + Service mesh that mirror the vendor's `docker-compose.with-database.yml`. The vendor does not publish a Helm chart and won't (confirmed with their support); the chart is reverse-engineered from their CLI's behaviour.

### Source of truth

Vendor ships installation as a Go binary (`https://doqa.app/downloads/doqa`, ELF amd64) plus per-version artifacts. The binary itself only contains the `install` subcommand on first run — it self-mutates into a post-install state that exposes `start/stop/update/cert/domain/backup/restore` once `.env`/`docker-compose.yml` exist in cwd. **All real content is in the per-version configs zip, not in the binary.** Pull these directly:

```
https://doqa.app/downloads/latest.txt          → "4_0_0"  (current)
https://doqa.app/downloads/cli_latest.txt      → CLI binary version
https://doqa.app/downloads/support_versions.json
https://doqa.app/downloads/configs_<ver>.zip   → .env.install + docker-compose.yml +
                                                  docker-compose.with-database.yml +
                                                  nginx/{Dockerfile,default_no_ssl.conf,default_ssl.conf}
```

The CLI **does not modify** the compose file: `./doqa install` copies it byte-identical into the working directory (verified via md5sum). It only patches `.env.install` → `.env` with regex substitutions for `APP_KEY` (`base64:<32>`), `JWT_SECRET`, `DB_PASSWORD`, `RABBITMQ_PASSWORD/ERLANG_COOKIE`, `MINIO_KEY/SECRET`, `PUSHER_APP_SECRET`, `STATISTIC_API_KEY`, `NOTIFICATION_API_KEY` (all `randAlphaNum 32`), plus `APP_URL` / `USE_SSL` from interactive prompts. Therefore: when DoQA ships a new minor version, fetching `configs_<ver>.zip` is sufficient — no need to spin up the CLI to discover anything new.

The vendor registry `registry.control.doqa.app` is publicly pullable (anonymous). All component image tags are explicit env vars in `.env.install` (`IMAGE_DOQA_API`, `IMAGE_DOQA_FRONTEND`, etc.) — these are the canonical version pins.

### How compose maps to the chart

Each vendor compose service has a 1:1 chart counterpart:

| compose service | chart template | k8s shape |
|---|---|---|
| `doqa_php-fpm` | `templates/backend.yaml` | Deployment + Service (:8080), `migrate --force` initContainer |
| `doqa_queue` | `templates/queue.yaml` | Deployment, `queue:work --queue=high,default` |
| `doqa_cron` | `templates/cron.yaml` | Deployment, `schedule:work` (one replica, `Recreate` strategy) |
| `doqa_frontend` | `templates/frontend.yaml` | Deployment + Service (:8080) |
| `doqa_autotest_parser` | `templates/autotest-parser.yaml` | Deployment + Service (:8000), explicit env (no envFrom) |
| `doqa_autotest_result_parser` | `templates/autotest-result-parser.yaml` | Deployment, no Service |
| `service-statistic` | `templates/statistic.yaml` | Deployment + Service (:3000), explicit env |
| `service-notification` | `templates/notification.yaml` (api block) | Deployment + Service (:3000) |
| `worker-notification` | `templates/notification.yaml` (worker block) | Deployment, Celery |
| `telegram-bot` | `templates/telegram-bot.yaml` | Deployment, gated by `telegramBot.enabled` |
| `websocket` (Soketi) | `templates/websocket.yaml` | Deployment + Service (:6001) |
| `doqa_nginx` | `templates/nginx.yaml` + `templates/nginx-configmap.yaml` | Deployment + Service (:80) — internal router behind Ingress |
| `doqa_postgres` (`with-database.yml` variant) | `templates/postgresql-cnpg.yaml` | CNPG `Cluster` CR (when `postgresql.cnpg.create=true`) |
| `doqa_redis` | `templates/redis.yaml` | Deployment + Service + PVC |
| `doqa_rabbitmq` | `templates/rabbitmq.yaml` | Deployment + Service + PVC |
| `minio` | `templates/minio.yaml` (top block) | Deployment + Service + PVC |
| `createbuckets` (one-shot in compose) | `templates/minio.yaml` (Job block) | `post-install`/`post-upgrade` Helm hook Job |
| `redis` (notification-only, second instance in compose) | reused single `redis.yaml` instance with different `REDIS_DB` | — |
| `minio_backup`/`minio_restore`/`doqa_backup_postgres`/`doqa_restore_postgres` | **not implemented** — vendor uses `profiles: manual`, invoked via `./doqa backup`/`restore` | — (out of scope) |

`.env.install` (47 keys) splits into three places in the chart:
- **ConfigMap `<release>-env`** — non-secret config (APP_URL, DB_HOST, MAIL_*, MINIO_*, BROADCAST_DRIVER, PUSHER_APP_HOST/ID/KEY/PORT, STATISTIC/NOTIFICATION_ENDPOINT, etc.). Pulled via `envFrom` into backend/queue/cron/result-parser.
- **Per-pod `env:` blocks** for components vendor doesn't load `env_file=.env` for: autotest-parser (12 explicit RABBITMQ/JWT/DEBUG envs), statistic (DB+API_KEY), notification anchor, websocket (5 SOKETI_* envs).
- **Secrets** — passwords/keys (APP_KEY, JWT_SECRET, DB_PASSWORD, RABBITMQ_PASSWORD/ERLANG_COOKIE, MINIO_KEY/SECRET, MAIL_PASSWORD, PUSHER_APP_SECRET, STATISTIC_API_KEY, NOTIFICATION_API_KEY, BOT_TOKEN). See "Secret strategy" below.

### Deliberate departures from vendor compose

These are NOT bugs — the chart re-expresses compose into k8s idioms:
- **Internal nginx kept** as Deployment+ConfigMap (1:1 with vendor's `default_no_ssl.conf`) instead of expanding all proxy paths into Ingress paths. Ingress just sends everything to nginx Service. Easier to keep in sync with vendor on minor updates.
- **TLS via cert-manager**, not certbot — vendor's `cert` subcommand and `box/letsencrypt/` directory are replaced by Ingress annotations.
- **`MINIO_BUCKET_URL`** computed as `<scheme>://<appUrl>/<bucket>` (browser hits Ingress→nginx→/doqa proxy→MinIO), vs vendor's `http://minio/doqa` which only works inside compose network.
- **Bucket creation via Helm post-install hook Job** (`templates/minio.yaml:Job`) instead of vendor's compose `createbuckets` profile. Hook delete-policy includes `hook-failed` so a stuck Job doesn't pin the release.
- **Backup/restore not implemented** — vendor's `./doqa backup` runs `pg_dump` + `mc mirror` into a zip; in k8s this belongs in a separate CronJob / external tool, not the application chart.
- **PUSHER_APP_HOST and STATISTIC/NOTIFICATION_ENDPOINT** hardcoded by vendor to compose `container_name`s; chart computes them from `<release>-<component>` Service names so they survive `nameOverride`/`fullnameOverride`.

### Updating to a new vendor version

When vendor publishes a new `box` version (check `https://doqa.app/downloads/latest.txt`):

1. `curl -O https://doqa.app/downloads/configs_<new>.zip && unzip` and **diff against the last shipped version's zip**. Look at: new `IMAGE_DOQA_*` tags, new env keys (`grep -vf old.env new.env`), new compose services, new nginx location blocks.
2. Update image tags in `values.yaml` (each component has independent versioning — `doqa-backend` vs `doqa-frontend` vs `doqa-parsing-autotests` etc. ship with **different** SemVer lines).
3. If new env vars appear in `.env.install`, add them to `templates/configmap.yaml` (non-secret) or to the relevant per-pod env block / Secret.
4. If new compose services appear, add a new template; if removed, delete one.
5. If `nginx/default_no_ssl.conf` changes, mirror the diff into `templates/nginx-configmap.yaml`.
6. Bump `appVersion` in `Chart.yaml` to the new vendor version, bump `version` (semver — minor for additions, major for backward-incompatible env layout).
7. Sanity check: `./doqa install` in a throwaway `docker run --rm -it` env (Linux amd64), then `docker exec <ctr> env | sort` for each running service and diff against the chart's rendered envs (`helm template ...`). The two should match modulo Service-name vs container-name differences.

### Component inventory

`backend` (php-fpm Laravel, port 8080), `queue` (`queue:work`), `cron` (`schedule:work`), `frontend` (Nuxt :8080), `autotest-parser` (FastAPI :8000, RabbitMQ-driven), `autotest-result-parser` (RabbitMQ consumer, no HTTP), `statistic` (ASGI :3000), `notification` (ASGI :3000) + `notification-worker` (Celery), `telegram-bot` (optional), `websocket` (Soketi :6001), `nginx` (internal router :80) — Ingress points at the nginx Service which proxies to all backends by path. Vendor images live at `registry.control.doqa.app` and pull anonymously (no `imagePullSecrets` needed by default).

### Stateful dependencies — `<name>.create` flag pattern

Each stateful dep has a flag to switch between in-tree provisioning and external service:

| Component | When `create=true` | When `create=false` |
|---|---|---|
| `postgresql.cnpg` | CNPG `Cluster` CR (requires CNPG operator pre-installed) | `postgresql.host`/`port`/etc + `passwordSecret` |
| `redis` | in-tree Deployment+PVC (single replica) | `redis.host` |
| `rabbitmq` | in-tree Deployment+PVC + chart-managed admin secret | `rabbitmq.host` + user-supplied `secrets.rabbitmq` |
| `minio` | in-tree Deployment+PVC + post-install `mc mb` Job | `minio.endpoint` + user-supplied `secrets.minio` |

Defaults are all `true` so a stranger doing `helm install` gets a working stack. The `_helpers.tpl` host-resolution functions (`doqa.postgresql.host`, `doqa.redis.host`, etc.) decide between Service-local DNS and the user-supplied value.

### Secret strategy

`secrets.create=true` (default) makes the chart generate **stable** application secrets via `randAlphaNum 32` + `lookup` (existing values are read back from the live secret on `helm upgrade`, so values don't rotate). The `_helpers.tpl` secret-name resolvers (`doqa.secret.app`, `doqa.secret.apiKeys`, `doqa.secret.pusher`, `doqa.secret.rabbitmq`, `doqa.secret.minio`) `required` the matching `Values.secrets.<name>` whenever the chart cannot generate the secret (i.e. `secrets.create=false`, or `<infra>.create=false` for rabbitmq/minio where the chart doesn't know the external password). This produces a clear `helm install` error instead of a runtime CrashLoop on a missing Secret.

Mail and LDAP passwords are always user-provided (`secrets.mail`, `secrets.ldap`) — chart never auto-generates these.

### nginx routing

`templates/nginx-configmap.yaml` is hand-written nginx conf that mirrors the vendor's `default_no_ssl.conf`:
- `/` → frontend
- `/api` → backend
- `/api/autotests/{report,allure-report-item,junit-report-item,report-inner}` → autotest-parser
- `/doqa` → MinIO (resolved via `doqa.minio.endpoint` helper, scheme/host trim'd from the URL)
- `^~ /app/web-socket` → Soketi (websocket upgrade)

The Ingress sends all traffic to the nginx Service; TLS terminates at the Ingress (cert-manager).

### Bucket-init Job

`templates/minio.yaml` includes a Helm `post-install,post-upgrade` hook Job that runs `mc alias set doqa http://...:9000 "$KEY" "$SECRET"` (in a wait loop until MinIO is ready) and creates the bucket. `hook-delete-policy: before-hook-creation,hook-succeeded,hook-failed` ensures a failed Job is cleaned up — without `hook-failed` the release would lock in `pending-install`.

### What does **not** get bundled

- Backup/restore (vendor's `./doqa backup`/`restore` use one-shot containers with `profiles: manual` — out of scope; user runs CronJobs separately if needed).
- The CNPG operator itself, cert-manager, ingress controllers — all assumed pre-installed cluster-wide.
- HPA, PDB, NetworkPolicy, ServiceMonitor, topologySpreadConstraints — none in v0.1.0 (deliberate scope cut for the first release; add behind opt-in flags later).

### Vendor licensing

DoQA is a paid product. The chart deploys the stack and the UI loads, but creating a super-user is gated by a vendor license key (`https://doqa.app`). End-to-end smoke beyond `/api/v1/info` returning 200 isn't possible without a real key.

## Test deploy values

`charts/doqa/ci/test-values.yaml` is pinned to a verified-good combination: traefik ingress, longhorn storage, `letsencrypt` HTTP-01 ClusterIssuer. Adjust the `ingress.className`, storage classes, and `cert-manager.io/cluster-issuer` annotation when reusing it in another environment.
