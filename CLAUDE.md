# AGENTS.md

Repository-level guidance for coding agents working in this Helm chart monorepo.

## Repository map

Charts live in `charts/<name>/`, are versioned independently, and are published through GitHub Releases plus the `gh-pages` Helm index at `https://batonogov.github.io/helm-charts/index.yaml`. Release archives are GitHub assets; they are not committed to `gh-pages`.

Currently shipped charts (do not copy their current versions into this file; `Chart.yaml` and the upstream sources are authoritative):

- `charts/doqa` — self-hosted DoQA TCMS for Kubernetes 1.32+. Use the vendor's **box** artifacts, not the cloud release page, to discover updates.
- `charts/xray-health-exporter` — Prometheus exporter for Xray-core tunnel health. GHCR `v*` tags are Renovate's source; `Chart.yaml` stores `appVersion` without the `v` prefix.

Repository automation:

- `.github/workflows/lint-test.yaml` — PR chart detection, `ct lint`, and generated README verification.
- `.github/workflows/release.yaml` — serialized chart publication from `main`.
- `.github/ct.yaml` — chart-testing policy, including version-increment enforcement.
- `.pre-commit-config.yaml` and `scripts/` — local formatting, docs, lint, and render checks.
- `renovate.json` — xray-health-exporter GHCR updates; `.github/dependabot.yml` — GitHub Actions updates.

## Common commands

```bash
# Full local validation. The local hooks run helm-docs, helm lint, and
# helm template for every chart in addition to repository hygiene checks.
pre-commit run --all-files

# Individual validation stages; each checks all charts.
scripts/check-helm-docs.sh
scripts/helm-lint-all.sh
scripts/helm-template-all.sh

# Render individual charts with their repository test values.
helm template test-doqa charts/doqa -f charts/doqa/ci/test-values.yaml >/dev/null
helm template test-xray charts/xray-health-exporter -f charts/xray-health-exporter/ci/test-values.yaml >/dev/null

# Mirrors the chart-testing portion of PR CI.
ct lint --config .github/ct.yaml --target-branch main
```

Do not use bare `helm template ... charts/doqa`: defaults intentionally require `ingress.className`. Use `ci/test-values.yaml`, set an ingress class, or disable the Ingress explicitly. The xray chart likewise needs at least one tunnel/subscription or an `existingConfigSecret`; its test values provide a placeholder.

There are no unit tests or in-cluster CI tests. PR CI runs `ct lint` for changed charts and, when any chart changed, verifies `helm-docs` output across all charts. End-to-end installation is manual.

## Versioning, generated files, and release flow

- Bump `version:` in a chart's `Chart.yaml` for every change under that chart directory detected by `ct list-changed` (currently including `ci/test-values.yaml`). `ct lint` enforces `check-version-increment: true`. Do not bump chart versions for repository-only files such as this one.
- Keep `values.yaml`, its helm-docs comments, and `values.schema.json` synchronized. Edit narrative documentation in `README.md.gotmpl`, then regenerate `README.md`; do not hand-edit generated value tables.
- `appVersion` tracks the upstream application. It is not a substitute for the chart version and, for DoQA, does not control the independently pinned component images.
- A push to `main` runs `chart-releaser-action` with `skip_existing: true` and `mark_as_latest: true`. New chart versions become releases tagged `<chart>-<version>`, and the action updates `gh-pages/index.yaml`; already-published versions are skipped.

## Chart authoring conventions

- Use Helm API v2 and the repository's current Kubernetes constraint (`kubeVersion: ">=1.32.0-0"`). The repository-wide minimum is Helm 3.14 because of xray-health-exporter; DoQA also supports Helm 3.13. Helm 4 is supported, while CI exercises a pinned Helm 3 release.
- Each chart directory includes `ci/test-values.yaml` for reproducible rendering. `.helmignore` excludes `ci/` from release archives.
- Do not add Bitnami or other sub-chart dependencies. Use an in-tree resource plus an external-service mode where appropriate. CNPG is the PostgreSQL pattern; Redis, RabbitMQ, and MinIO use small in-tree single-replica templates where needed.
- In-tree dependencies do not remove cluster prerequisites. For example, DoQA's default CNPG `Cluster` needs the CNPG operator, and an enabled Ingress needs a valid `ingress.className` and controller.
- Add a chart under `charts/<new-name>/`; `ct list-changed` discovers it automatically. This repository intentionally has no `Chart.lock` or `helm dep update` workflow.

## Working with `.tmp/`

`.tmp/` is gitignored and is the preferred location for vendor binaries, extracted configs, and manifest diffs used during chart development. Never commit its contents.

## Architecture of `charts/doqa`

The chart translates the vendor's `docker-compose.with-database.yml` into Kubernetes resources. It currently renders 15 Deployments with repository test values; `telegramBot.enabled=true` adds the optional sixteenth. PostgreSQL is a CNPG `Cluster`, not another Deployment. The chart uses ordinary ClusterIP Services and does not install a service mesh.

The vendor distributes a CLI and Compose configs rather than a Helm chart. Treat the current **box** artifacts as upstream; cloud releases can appear before a corresponding box package.

### Source of truth

The per-version config archive is the canonical input for chart updates. Check these endpoints directly:

```
https://doqa.app/downloads/latest.txt          → latest box version, format `<major>_<minor>_<patch>`
https://doqa.app/downloads/cli_latest.txt      → CLI binary version
https://doqa.app/downloads/support_versions.json
https://doqa.app/downloads/configs_<ver>.zip   → .env.install + docker-compose.yml +
                                                  docker-compose.with-database.yml +
                                                  nginx/{Dockerfile,default_no_ssl.conf,default_ssl.conf}
https://doqa.app/downloads/doqa                → Linux amd64 management CLI
```

The CLI copies the Compose file and materializes `.env` from `.env.install`, filling URLs and generated secrets such as application/JWT, RabbitMQ, MinIO, Pusher, statistic, notification, and LLM keys. Do not use the CLI as a substitute for diffing the archive: new services, environment variables, and nginx routes are visible directly in the zip.

Vendor component image references are explicit `IMAGE_DOQA_*` variables in `.env.install`; these are the canonical pins. The chart stores their repository/tag pairs independently in `values.yaml` and prefixes them with `image.registry`.

### How compose maps to the chart

The primary mappings are below. They are not strictly 1:1: in-tree mode consolidates the two Redis services, PostgreSQL is replaced with CNPG or an external service, and manual backup workloads are omitted.

| compose service | chart template | k8s shape |
|---|---|---|
| `doqa_php-fpm` | `templates/backend.yaml` | Deployment + Service (:8080), `migrate --force` initContainer |
| `doqa_queue` | `templates/queue.yaml` | Deployment, `queue:work --queue=high,default` |
| `doqa_cron` | `templates/cron.yaml` | Deployment, `schedule:work` (one replica, `Recreate` strategy) |
| `doqa_frontend` | `templates/frontend.yaml` | Deployment + Service (:8080) |
| `doqa_autotest_parser` | `templates/autotest-parser.yaml` | Deployment + Service (:8000), explicit env (no envFrom) |
| `doqa_autotest_result_parser` | `templates/autotest-result-parser.yaml` | Deployment, no Service |
| `service-statistic` | `templates/statistic.yaml` | Deployment + Service (:3000), explicit env |
| `service-llm` | `templates/llm.yaml` | Deployment + Service (:3000), explicit env |
| `service-notification` | `templates/notification.yaml` (api block) | Deployment + Service (:3000) |
| `worker-notification` | `templates/notification.yaml` (worker block) | Deployment, Celery |
| `telegram-bot` | `templates/telegram-bot.yaml` | Deployment, gated by `telegramBot.enabled` |
| `websocket` (Soketi) | `templates/websocket.yaml` | Deployment + Service (:6001) |
| `doqa_nginx` | `templates/nginx.yaml` + `templates/nginx-configmap.yaml` | Deployment + Service (:80) — internal router behind Ingress |
| `doqa_postgres` (`with-database.yml` variant) | `templates/postgresql-cnpg.yaml` | CNPG `Cluster` CR (when `postgresql.cnpg.create=true`) |
| `doqa_redis` | `templates/redis.yaml` | Deployment + Service + PVC |
| `doqa_rabbitmq` | `templates/rabbitmq.yaml` | Deployment + Service + PVC |
| `minio` | `templates/minio.yaml` (top block) | Deployment + Service + PVC |
| `createbuckets` (manual Compose profile) | `templates/minio.yaml` (Job block) | `post-install`/`post-upgrade` Helm hook Job |
| `redis` (notification-only, second instance in compose) | `templates/redis.yaml` | In-tree mode reuses primary Redis; external mode may set `redis.notification.host` separately |
| `minio_backup`/`minio_restore`/`doqa_backup_postgres`/`doqa_restore_postgres` | **not implemented** — vendor uses `profiles: manual`, invoked via `./doqa backup`/`restore` | — (out of scope) |

`.env.install` splits into three places in the chart:

- **ConfigMap `<release>-env`** — non-secret config (APP_URL, DB_HOST, MAIL_*, MINIO_*, BROADCAST_DRIVER, PUSHER_APP_HOST/ID/KEY/PORT/SCHEME, STATISTIC/NOTIFICATION/LLM_ENDPOINT, QUEUE_WORKERS, etc.). Pulled via `envFrom` into backend/queue/cron/result-parser.
- **Per-pod `env:` blocks** for components that do not consume the ConfigMap: autotest-parser, statistic, llm, notification/worker, Telegram bot, and websocket. Adding a key to the ConfigMap does not reach these pods; wire every new upstream variable into the relevant template explicitly.
- **Secrets** — passwords/keys (APP_KEY, JWT_SECRET, DB_PASSWORD, RABBITMQ_PASSWORD/ERLANG_COOKIE, MINIO_KEY/SECRET, MAIL_PASSWORD, PUSHER_APP_SECRET, STATISTIC_API_KEY, NOTIFICATION_API_KEY, LLM_API_KEY, BOT_TOKEN). See "Secret strategy" below.

### Deliberate departures from vendor compose

These are NOT bugs — the chart re-expresses compose into k8s idioms:

- **Internal nginx kept** as Deployment+ConfigMap, mirroring the vendor route/location structure with Kubernetes-specific upstreams and headers instead of expanding every proxy path into Ingress rules.
- **TLS terminates at the Ingress**, not vendor certbot. Users can use cert-manager annotations or a pre-provisioned TLS Secret.
- **`MINIO_BUCKET_URL`** computed as `<scheme>://<appUrl>/<bucket>` (browser hits Ingress→nginx→/doqa proxy→MinIO), vs vendor's `http://minio/doqa` which only works inside compose network.
- **Bucket creation via Helm post-install hook Job** (`templates/minio.yaml:Job`) instead of vendor's Compose `createbuckets` profile. Hook delete-policy includes `hook-failed` so a completed failed Job is cleaned up.
- **Backup/restore not implemented** — vendor's `./doqa backup` runs `pg_dump` + `mc mirror` into a zip; in k8s this belongs in a separate CronJob / external tool, not the application chart.
- **PUSHER_APP_HOST and STATISTIC/NOTIFICATION/LLM_ENDPOINT** hardcoded by vendor to compose `container_name`s; chart computes them from `<release>-<component>` Service names so they survive `nameOverride`/`fullnameOverride`.

### Updating to a new vendor version

When the vendor publishes a new **box** version in `latest.txt` and the matching config zip exists:

1. Download `configs_<new>.zip`, extract it under `.tmp/`, and diff it against the last shipped archive. Check `.env.install`, both Compose files, nginx configs, and the Dockerfile.
2. Update image tags in `values.yaml` (each component has independent versioning — `doqa-backend` vs `doqa-frontend` vs `doqa-parsing-autotests` etc. ship with **different** SemVer lines).
3. Audit image compatibility: run `scripts/audit-doqa-images.sh <old_values.yaml> <new_values.yaml>` (e.g. `git show main:charts/doqa/values.yaml` vs the working tree) to confirm no component image changed its `Env`/`Entrypoint`/`Cmd` contract — a newly required env var or changed startup command the chart does not account for. This inspects the images themselves (configs only, no layer pull) and catches runtime contract changes the config zip does not surface.
4. Route every new environment variable to `templates/configmap.yaml`, the relevant explicit per-pod block, or a Secret. Verify consumption per service; do not assume ConfigMap membership is sufficient.
5. If new compose services appear, add a new template; if removed, delete one.
6. If `nginx/default_no_ssl.conf` changes, mirror the diff into `templates/nginx-configmap.yaml`.
7. Keep `values.schema.json`, helm-docs comments, `README.md.gotmpl`, and generated `README.md` synchronized with value or upgrade changes.
8. Bump `appVersion` to the new box version and bump chart `version`: patch for compatible fixes/pin changes, minor for additive chart features, major for breaking changes.
9. Run the full local checks. When practical, install with the CLI in a throwaway Linux amd64 environment and diff each service's effective environment against the rendered chart, allowing for Kubernetes Service names and deliberate departures above.

### Component inventory

`backend` (php-fpm Laravel, port 8080), `queue` (`queue:work`), `cron` (`schedule:work`), `frontend` (Nuxt :8080), `autotest-parser` (FastAPI :8000, RabbitMQ-driven), `autotest-result-parser` (RabbitMQ consumer, no HTTP), `statistic` (ASGI :3000), `llm` (ASGI :3000), `notification` (ASGI :3000) + `notification-worker` (Celery), `telegram-bot` (optional), `websocket` (Soketi :6001), and `nginx` (internal router :80). Ingress points to nginx, which routes to the internal services.

### Stateful dependencies — `<name>.create` flag pattern

Each stateful dep has a flag to switch between in-tree provisioning and external service:

| Component | When `create=true` | When `create=false` |
|---|---|---|
| `postgresql.cnpg` | CNPG `Cluster` CR (requires CNPG operator pre-installed) | `postgresql.host`/`port`/etc + `passwordSecret` |
| `redis` | in-tree Deployment+PVC (single replica) | `redis.host` |
| `rabbitmq` | in-tree Deployment+PVC + chart-managed admin secret | `rabbitmq.host` + user-supplied `secrets.rabbitmq` |
| `minio` | in-tree Deployment+PVC + post-install `mc mb` Job | `minio.endpoint` + user-supplied `secrets.minio`; bucket/policy must already exist |

These creation flags default to `true`, but installation still requires the CNPG operator, an IngressClass/controller, and usable storage, or explicit external-service overrides. The `_helpers.tpl` host-resolution functions (`doqa.postgresql.host`, `doqa.redis.host`, etc.) select Service-local DNS or user-supplied endpoints.

### Secret strategy

`secrets.create=true` always provisions three lookup-aware Secrets (app/JWT, API keys, and Pusher). With the default in-tree RabbitMQ and MinIO it also provisions their two infrastructure Secrets, for five total. Existing values are read back during upgrades so they remain stable; fresh offline renders generate new random values and should not be expected to diff deterministically. Secret lengths are key-specific rather than uniformly 32 characters.

When generation is disabled, or when external RabbitMQ/MinIO is selected, the corresponding existing Secret name is required. CNPG generates its database Secret in in-tree mode; external PostgreSQL and optional Redis authentication reference user-supplied Secrets. SMTP and LDAP passwords plus the Telegram token are also externally supplied. `MAIL_PASSWORD` is emitted when `secrets.mail` is set; LDAP credentials are emitted only for enabled LDAP with a configured secret.

### Upgrade-sensitive names and security contexts

Treat `nameOverride` and `fullnameOverride` as install-time-only values. `nameOverride` participates in immutable Deployment selectors and, unless a full override is set, resource names; changing it can fail upgrades and rename resources. `fullnameOverride` changes resource names directly. Either change can orphan stateful resources/PVCs.

DoQA image USER metadata is heterogeneous. Do not set a global `runAsNonRoot` or fixed UID without checking every currently pinned image. Preserve the safe defaults (`allowPrivilegeEscalation: false`, drop all capabilities), and apply stronger pod/container contexts only to verified images or rebuilt variants.

### nginx routing

`templates/nginx-configmap.yaml` is hand-written nginx conf that mirrors the vendor's `default_no_ssl.conf`:

- `/` → frontend
- `/api` → backend
- `/api/autotests/{report,allure-report-item,junit-report-item,report-inner}` → autotest-parser
- `/doqa` → MinIO (resolved via `doqa.minio.endpoint` helper, scheme/host trim'd from the URL)
- `^~ /app/web-socket` → Soketi (websocket upgrade)

The Ingress sends all traffic to the nginx Service. TLS terminates at the Ingress through either a supplied Secret or an external certificate controller such as cert-manager.

### Bucket-init Job

`templates/minio.yaml` includes a Helm `post-install,post-upgrade` hook Job that provisions the MinIO bucket. It runs `mc alias set` non-fatally because that only writes local configuration, then probes the server with `mc ls`. Authentication errors exit the container instead of looping; the Job then follows its `OnFailure`/`backoffLimit` retry policy. Transient reachability failures retry inside the probe loop. Once reachable it runs `mc mb --ignore-existing` and sets anonymous access. The hook policy cleans up completed succeeded/failed Jobs and replaces an old hook before a new run.

### Out of scope and optional features

- Backup/restore (vendor's `./doqa backup`/`restore` use one-shot containers with `profiles: manual` — out of scope; user runs CronJobs separately if needed).
- The CNPG operator, certificate controller, Ingress controller, and StorageClasses are not installed by this chart.
- HPA, PDB, NetworkPolicy, and ServiceMonitor templates are included but disabled by default. HPA, PDB, and topology-spread settings cover backend/frontend/queue; ServiceMonitor targets the backend.

### Vendor licensing

DoQA is a paid product. The chart deploys the stack and the UI loads, but creating a super-user is gated by a vendor license key (`https://doqa.app`). End-to-end smoke beyond `/api/v1/info` returning 200 isn't possible without a real key.

### Test deploy values

`charts/doqa/ci/test-values.yaml` renders a traefik + longhorn + cert-manager example. It is repository test input, not portable production configuration. Adjust the hostname, IngressClass, annotations, TLS secret/controller, and StorageClasses for the target cluster.

## Architecture of `charts/xray-health-exporter`

### Version and image chain

- Renovate watches `ghcr.io/batonogov/xray-health-exporter` Docker tags through the regex marker in `Chart.yaml`.
- Upstream tags are `v<version>`; `Chart.yaml.appVersion` stores `<version>`. When `image.tag` is empty, `_helpers.tpl` renders `v<appVersion>`.
- Renovate updates `appVersion`, bumps the chart patch version, and synchronizes both chart/app badges in generated `README.md`. Preserve the marker and `renovate.json` match expressions when editing version metadata.

### Configuration and validation

- The exporter refuses to start without at least one `config.tunnels` or `config.subscriptions` entry, unless `existingConfigSecret` supplies `config.yaml`. Use `ci/test-values.yaml` for repository renders.
- Subscription URLs commonly contain credentials. Do not put real tokens in committed values or the chart-generated ConfigMap; use `existingConfigSecret`.
- Pushgateway URLs containing credentials belong in `metricsPush.urlSecret`, not plaintext `metricsPush.url`.
- `replicaCount > 1` force-enables leader election even if `leaderElection.enabled=false`, preventing duplicate tunnel metrics. Keep the Lease RBAC and ServiceAccount behavior in sync when changing replica logic.
- The upstream image is designed for UID/GID 10001 and the chart deliberately enforces non-root, read-only-root-filesystem defaults. Preserve `/tmp` as an `emptyDir` if the container filesystem remains read-only.
