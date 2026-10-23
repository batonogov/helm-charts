# doqa

DoQA Test Case Management System (TCMS) self-hosted on Kubernetes

![Version: 0.10.0](https://img.shields.io/badge/Version-0.10.0-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square) ![AppVersion: 4.3.5-box](https://img.shields.io/badge/AppVersion-4.3.5--box-informational?style=flat-square)

**Homepage:** <https://doqa.app>

> **Community status**: this is an unofficial, independently maintained Helm
> chart. It is used in production by its maintainer, but it is not developed or
> supported by the DoQA vendor. Application licensing and vendor support remain
> with [DoQA](https://doqa.app).
>
> **Licensing**: DoQA box-versions require a vendor license key to activate
> (super-user creation is gated). This chart deploys the stack but does not
> bypass licensing — request a key from <https://doqa.app>.

## TL;DR

```bash
helm repo add batonogov https://batonogov.github.io/helm-charts
helm install doqa batonogov/doqa -n doqa --create-namespace \
  --set appUrl=doqa.example.com \
  --set ingress.className=traefik \
  --set ingress.annotations."cert-manager\.io/cluster-issuer"=letsencrypt
```

## Prerequisites

- Kubernetes 1.32+
- Helm 3.13+ (Helm 4 supported) — templates use only functions available since Helm 3.0 (`lookup`, `required`, `toYaml`, `sha256sum`, JSON schema validation); no Helm 3.14-only features are required
- An Ingress controller routable from the public DNS pointing to `appUrl`
- For TLS: cert-manager with a working ClusterIssuer (or a pre-provisioned TLS secret)
- For PostgreSQL via CNPG (default): the
  [CloudNativePG](https://cloudnative-pg.io/) operator already installed in
  the cluster (typically in `cnpg-system`)
- Storage class supporting `ReadWriteOnce` PVCs

The DoQA application images live at `registry.control.doqa.app` and pull
anonymously — no `imagePullSecrets` are required by default.

## Compatibility and support boundaries

| Area | Status | Notes |
|---|---|---|
| DoQA Box | Supported | Component versions are pinned in `values.yaml`; verified against the vendor archive `configs_4_3_4.zip` |
| Kubernetes | Supported | `1.32+`, as declared by `Chart.yaml`; manifests use stable Kubernetes APIs |
| Helm | Tested | Helm `3.16` in CI and Helm 4 locally; Helm `3.13+` is supported |
| Node platform | Supported | `linux/amd64`; the current vendor images are single-platform amd64 images |
| Ingress | Configurable | Standard `networking.k8s.io/v1` Ingress; Traefik is the repository test profile, while other controllers use `ingress.className` and annotations |
| Persistent storage | Configurable | Any CSI StorageClass supporting `ReadWriteOnce`; Longhorn is only the repository test profile |
| PostgreSQL | Configurable | CloudNativePG by default, or an external PostgreSQL service |
| Restricted platforms | Not claimed | ARM, OpenShift, IPv6-only clusters, and enforced Pod Security `restricted` have not been validated |

The default security context drops all capabilities and disables privilege
escalation. It deliberately does not force `runAsNonRoot`, a fixed UID, or a
read-only root filesystem because the pinned vendor images have heterogeneous
runtime users. Use `defaultSecurityContext` and per-component overrides only
after validating the selected images. The MinIO bucket-init Job uses its own
`minio.client` security contexts plus the configured ServiceAccount, global or
client-specific scheduling, labels, and annotations. It does not inherit
`defaultSecurityContext` because the current `mc` image runs as root.

## Architecture

Components mirror the vendor docker-compose for v4.3.4:

- `backend` (php-fpm Laravel API), `queue` (`queue:work`), `cron` (`schedule:work`)
- `autotests-worker` (`autotests:work`, declares the RabbitMQ queues),
  `llm-bulk-queue` (`queue:work` on the long-timeout `llm-bulk` queue)
- `frontend` (Nuxt SPA)
- `autotest-parser` (FastAPI, RabbitMQ-driven)
- `statistic`, `llm`, `notification` (+ Celery worker), `telegram-bot` (optional)
- `websocket` (Soketi, Pusher protocol)
- `nginx` (internal router) → exposed via Ingress

The canonical upstream input is the vendor's
[`configs_4_3_4.zip`](https://doqa.app/downloads/configs_4_3_4.zip), including
`.env.install`, both Compose files, and nginx configuration. The DoQA
application services, environment variables, routes, and application image pins
stay aligned with that archive. Kubernetes infrastructure is deliberately
adapted: CNPG or an external PostgreSQL replaces the Compose database, in-tree
mode consolidates the two Redis services, dependency images are pinned by the
chart, TLS terminates at the Ingress, and the MinIO bucket is created by a Helm
hook Job.

Stateful dependencies are provisioned by the chart by default and can be
swapped to external services with `<component>.create=false`:

| Component | Default | External alternative |
|---|---|---|
| PostgreSQL | CNPG `Cluster` (1 instance) | `postgresql.cnpg.create=false` + `postgresql.host` |
| Redis | In-tree Deployment + PVC | `redis.create=false` + `redis.host` |
| RabbitMQ | In-tree Deployment + PVC | `rabbitmq.create=false` + `rabbitmq.host` |
| MinIO | In-tree Deployment + PVC + bucket-init Job | `minio.create=false` + `minio.endpoint` |

## Secrets

By default the chart **generates** application secrets (`secrets.create=true`)
with stable values via `lookup` — they survive `helm upgrade`. Set
`secrets.create=false` to plug in pre-existing secrets:

| Secret | Keys |
|---|---|
| `<release>-app-secrets` | `app-key`, `jwt-secret`, `internal-system-key` |
| `<release>-api-keys` | `statistic-api-key`, `notification-api-key`, `llm-api-key` |
| `<release>-pusher-secret` | `app-secret` |
| `<release>-rabbitmq-secret` | `password`, `erlang-cookie` |
| `<release>-minio-secrets` | `access-key`, `secret-key` |

The mail and LDAP passwords are always user-provided through `secrets.mail`
and `secrets.ldap`.

### GitOps and offline rendering

Generated secrets remain stable during direct `helm upgrade` because Helm's
`lookup` function reads the existing release Secrets. Renderers without live
cluster access, including `helm template` and offline GitOps rendering
pipelines, cannot perform that lookup and will generate different random values
on subsequent renders. For those workflows, set `secrets.create=false` and
provide stable values through pre-created Secrets, External Secrets, Sealed
Secrets, or an equivalent secret management system.

## Requirements

Kubernetes: `>=1.32.0-0`

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| affinity | object | `{}` | Default affinity applied to all components. Per-component values override this. |
| apiBaseUrl | string | `""` | Optional explicit API base URL (`API_BASE_URL`). Leave empty to use internal backend service. |
| appFrontendUrl | string | `""` | Frontend URL (defaults to appUrl when empty) |
| appUrl | string | `"doqa.example.com"` | DoQA application URL (host without protocol, e.g. "doqa.example.com") |
| autoscaling.backend.maxReplicas | int | `5` | Maximum replicas for backend HPA |
| autoscaling.backend.minReplicas | int | `2` | Minimum replicas for backend HPA |
| autoscaling.backend.targetCPUUtilizationPercentage | int | `80` | Target CPU utilization percentage for backend HPA |
| autoscaling.enabled | bool | `false` | Enable HorizontalPodAutoscaler for backend, frontend, and queue Deployments. When enabled, the replicas field is removed from those Deployments (HPA manages replicas) |
| autoscaling.frontend.maxReplicas | int | `5` | Maximum replicas for frontend HPA |
| autoscaling.frontend.minReplicas | int | `2` | Minimum replicas for frontend HPA |
| autoscaling.frontend.targetCPUUtilizationPercentage | int | `80` | Target CPU utilization percentage for frontend HPA |
| autoscaling.queue.maxReplicas | int | `5` | Maximum replicas for queue HPA |
| autoscaling.queue.minReplicas | int | `3` | Minimum replicas for queue HPA |
| autoscaling.queue.targetCPUUtilizationPercentage | int | `80` | Target CPU utilization percentage for queue HPA |
| autotestParser.affinity | object | `{}` |  |
| autotestParser.image.repository | string | `"doqa/doqa-parsing-autotests"` | Autotest parser image repository |
| autotestParser.image.tag | string | `"4.3.1-box"` | Autotest parser image tag |
| autotestParser.nodeSelector | object | `{}` |  |
| autotestParser.replicas | int | `1` | Autotest parser replica count |
| autotestParser.resources | object | `{"limits":{"cpu":"250m","memory":"256Mi"},"requests":{"cpu":"100m","memory":"128Mi"}}` | Resource requests and limits |
| autotestParser.tolerations | list | `[]` |  |
| autotestsWorker.affinity | object | `{}` |  |
| autotestsWorker.nodeSelector | object | `{}` |  |
| autotestsWorker.prefetch | int | `10` | RabbitMQ prefetch per `autotests:work` process (vendor AUTOTESTS_PREFETCH) |
| autotestsWorker.replicas | int | `3` | Autotests worker replica count (vendor scales it with QUEUE_WORKERS) |
| autotestsWorker.resources | object | `{"limits":{"cpu":"250m","memory":"256Mi"},"requests":{"cpu":"100m","memory":"128Mi"}}` | Resource requests and limits |
| autotestsWorker.tolerations | list | `[]` |  |
| autotestsWorker.waitForRabbitmq | bool | `true` | Wait for RabbitMQ AMQP readiness before starting the worker. Vendor 4.3.1 gates the autotests service on a healthy broker; the chart mirrors that by probing the broker first. |
| autotestsWorker.workerProcesses | int | `3` | Parallel `autotests:work` processes per pod (vendor AUTOTESTS_WORKER_PROCESSES) |
| backend.affinity | object | `{}` |  |
| backend.containerSecurityContext | object | `{"capabilities":{"add":["CHOWN","DAC_OVERRIDE","SETUID","SETGID"]}}` | Capabilities required to start nginx/FPM in the vendor backend. Global chart restrictions remain in effect. |
| backend.image.repository | string | `"doqa/doqa-backend"` | Backend image repository (relative to image.registry) |
| backend.image.tag | string | `"4.3.6-box"` | Backend image tag |
| backend.livenessProbe | object | `{"initialDelaySeconds":60,"periodSeconds":30,"tcpSocket":{"port":"http"},"timeoutSeconds":10}` | TCP liveness avoids restarting the backend on FPM saturation or database unavailability. null disables the probe. |
| backend.migrate.waitForRabbitmq | bool | `true` | Wait for RabbitMQ AMQP readiness before running migrations. Vendor 4.2.0 added a compose dependency on rabbitmq because some migrations dispatch jobs; the chart mirrors that by probing the broker first. |
| backend.nodeSelector | object | `{}` |  |
| backend.phpFpm.enabled | bool | `false` | Use the current image configuration with an overridden pool size. Size memory for your workload. |
| backend.phpFpm.maxChildren | int | `5` | Maximum worker count; other pool settings are inherited from the image and validated by the init container. |
| backend.readinessProbe | object | `{"exec":{"command":["sh","-ec","code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8080/)\ncase \"$code\" in 2??|3??|4??) exit 0 ;; *) exit 1 ;; esac"]},"initialDelaySeconds":15,"periodSeconds":10,"timeoutSeconds":8}` | Application readiness check: HTTP 2xx–4xx succeed; 5xx and transport errors fail. null disables the probe. |
| backend.replicas | int | `2` | Backend replica count |
| backend.resources | object | `{"limits":{"cpu":"500m","memory":"512Mi"},"requests":{"cpu":"250m","memory":"256Mi"}}` | Resource requests and limits |
| backend.skipMigrate | bool | `false` | Disable only the migration init container; the vendor image CMD may run migrations independently |
| backend.tolerations | list | `[]` |  |
| cron.affinity | object | `{}` |  |
| cron.nodeSelector | object | `{}` |  |
| cron.resources | object | `{"limits":{"cpu":"250m","memory":"256Mi"},"requests":{"cpu":"100m","memory":"128Mi"}}` | Resource requests and limits |
| cron.tolerations | list | `[]` |  |
| debug | bool | `false` | Enable verbose debug logging |
| defaultSecurityContext.container.allowPrivilegeEscalation | bool | `false` |  |
| defaultSecurityContext.container.capabilities.drop[0] | string | `"ALL"` |  |
| defaultSecurityContext.pod | object | `{}` |  |
| doqaBackendUrl | string | `""` | Optional backend URL (`DOQA_BACKEND_URL`) passed to backend workloads and the autotest-parser. Empty matches the vendor default. |
| extraAnnotations | object | `{}` | Extra annotations added to every resource. Keys with a `checksum/` prefix (e.g. `checksum/env`, `checksum/config`) are chart-managed and reserved; any such key supplied here is silently dropped at render time to avoid colliding with the chart's own checksum annotations. |
| extraLabels | object | `{}` | Extra labels added to every resource |
| extraVolumeMounts | list | `[]` | Extra volume mounts to add to all containers |
| extraVolumes | list | `[]` | Extra volumes to add to all Deployments |
| frontend.affinity | object | `{}` |  |
| frontend.containerSecurityContext | object | `{"capabilities":{"add":["CHOWN","DAC_OVERRIDE","SETUID","SETGID"]}}` | Capabilities required to start nginx in the component image; privilege escalation remains disabled. |
| frontend.image.repository | string | `"doqa/doqa-frontend"` | Frontend image repository (relative to image.registry) |
| frontend.image.tag | string | `"4.3.3-box"` | Frontend image tag |
| frontend.nodeSelector | object | `{}` |  |
| frontend.replicas | int | `2` | Frontend replica count |
| frontend.resources | object | `{"limits":{"cpu":"500m","memory":"512Mi"},"requests":{"cpu":"250m","memory":"256Mi"}}` | Resource requests and limits |
| frontend.tolerations | list | `[]` |  |
| fullnameOverride | string | `""` | Override the full name of resources. SET-ONCE-AT-INSTALL: changing this on an existing release renames every chart-managed resource (Helm drops the old-named objects and creates new ones), orphaning the CNPG Cluster and the redis/rabbitmq/minio PVCs (data loss). Do not change after first install. |
| image.pullPolicy | string | `"IfNotPresent"` | Default imagePullPolicy |
| image.pullSecrets | list | `[]` | imagePullSecrets applied to all chart-managed workload pods |
| image.registry | string | `"registry.control.doqa.app"` | Container registry hosting DoQA images |
| ingress.annotations | object | `{}` | Extra annotations (e.g. cert-manager.io/cluster-issuer) |
| ingress.className | string | `""` | REQUIRED when `ingress.enabled=true`. IngressClassName the controller listens on (e.g. nginx, traefik). Empty value fails rendering with a clear error. |
| ingress.enabled | bool | `true` | Create the Ingress resource. Defaults to true. When enabled, `ingress.className` is REQUIRED and rendering fails with a clear error if it is empty (no Ingress controller claims an empty className). |
| ingress.tls.enabled | bool | `true` | Enable TLS in the Ingress |
| ingress.tls.secretName | string | `""` | Existing TLS secret name (empty = <release>-tls) |
| ldap.baseDn | string | `""` | Search base DN |
| ldap.enabled | bool | `false` | Enable LDAP login |
| ldap.encryption | string | `""` | Encryption (ssl/tls/"") |
| ldap.host | string | `""` | LDAP host |
| ldap.port | int | `389` | LDAP port |
| ldap.sasl | bool | `false` | Use SASL bind |
| ldap.username | string | `""` | Bind DN of the technical account |
| llm.affinity | object | `{}` |  |
| llm.image.repository | string | `"doqa/doqa-llm"` | LLM image repository |
| llm.image.tag | string | `"4.3.0-box"` | LLM image tag |
| llm.nodeSelector | object | `{}` |  |
| llm.replicas | int | `1` | Replica count |
| llm.resources | object | `{"limits":{"cpu":"250m","memory":"256Mi"},"requests":{"cpu":"100m","memory":"128Mi"}}` | Resource requests and limits |
| llm.tolerations | list | `[]` |  |
| llmBulkQueue.affinity | object | `{}` |  |
| llmBulkQueue.nodeSelector | object | `{}` |  |
| llmBulkQueue.replicas | int | `1` | LLM bulk queue worker replica count (vendor runs a single replica) |
| llmBulkQueue.resources | object | `{"limits":{"cpu":"250m","memory":"256Mi"},"requests":{"cpu":"100m","memory":"128Mi"}}` | Resource requests and limits |
| llmBulkQueue.tolerations | list | `[]` |  |
| llmBulkQueue.waitForRabbitmq | bool | `true` | Wait for RabbitMQ AMQP readiness before starting the worker. Vendor 4.3.1 gates the llm-bulk service on a healthy broker; the chart mirrors that by probing the broker first. |
| mail.encryption | string | `"tls"` | Encryption (tls/ssl/null) |
| mail.fromAddress | string | `""` | Sender address |
| mail.fromName | string | `"DoQA"` | Sender display name |
| mail.host | string | `""` | SMTP host (leave empty to disable mail) |
| mail.mailer | string | `"smtp"` | Mailer driver |
| mail.port | int | `587` | SMTP port |
| mail.username | string | `""` | SMTP user |
| mailIssue | string | `"support@doqa.app"` | Issue/support email exposed to backend (`ISSUE_MAIL`) |
| minio.affinity | object | `{}` | Affinity for MinIO pods. Overrides global affinity |
| minio.bucket | string | `"doqa"` | Bucket name |
| minio.bucketUrl | string | `""` | Public bucket URL (defaults to "<scheme>://<appUrl>/<bucket>" when empty, served via internal nginx) |
| minio.client.affinity | object | `{}` | Affinity for the bucket-init Job. Overrides global affinity |
| minio.client.containerSecurityContext | object | `{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]}}` | Container security context for the bucket-init Job. Kept separate from defaultSecurityContext because the current mc image runs as root |
| minio.client.image.repository | string | `"quay.io/minio/mc"` | mc client image (used by bucket-init Job) |
| minio.client.image.tag | string | `"RELEASE.2025-08-13T08-35-41Z"` | mc tag |
| minio.client.nodeSelector | object | `{}` | Node selector for the bucket-init Job. Overrides global nodeSelector |
| minio.client.podSecurityContext | object | `{}` | Pod security context for the bucket-init Job |
| minio.client.resources | object | `{"limits":{"cpu":"100m","memory":"128Mi"},"requests":{"cpu":"10m","memory":"32Mi"}}` | Resource requests and limits for the bucket-init Job |
| minio.client.tolerations | list | `[]` | Tolerations for the bucket-init Job. Overrides global tolerations |
| minio.create | bool | `true` | Provision an in-tree MinIO Deployment+PVC + bucket-init Job |
| minio.endpoint | string | `""` | External MinIO/S3 endpoint (used only when create=false). For in-tree MinIO chart computes internal URL automatically |
| minio.image.repository | string | `"quay.io/minio/minio"` | MinIO image |
| minio.image.tag | string | `"RELEASE.2025-10-15T17-29-55Z"` | MinIO tag |
| minio.nodeSelector | object | `{}` | Node selector for MinIO pods. Overrides global nodeSelector |
| minio.region | string | `"ru-1"` | Region |
| minio.resources | object | `{"limits":{"cpu":"500m","memory":"512Mi"},"requests":{"cpu":"250m","memory":"256Mi"}}` | Resource requests and limits |
| minio.storage.size | string | `"4Gi"` | PVC size for MinIO |
| minio.storage.storageClass | string | `""` | StorageClass for MinIO PVC |
| minio.tolerations | list | `[]` | Tolerations for MinIO pods. Overrides global tolerations |
| nameOverride | string | `""` | Override the chart name part of resource names. SET-ONCE-AT-INSTALL: `app.kubernetes.io/name` (derived from this) lands in every Deployment's `.spec.selector`, which Kubernetes treats as immutable. Changing nameOverride on an existing release makes the upgrade fail with `field is immutable` on all Deployments until the value is reverted or the release is reinstalled. nameOverride also feeds doqa.fullname (when fullnameOverride is unset), so it additionally renames every chart-managed resource and orphans the redis/rabbitmq/minio PVCs. |
| networkPolicy.enabled | bool | `false` | Enable NetworkPolicy resources. Creates a default-deny-ingress policy and explicit allow rules for all internal traffic paths |
| nginx.affinity | object | `{}` |  |
| nginx.clientMaxBodySize | string | `"0"` | Maximum upload size. `0` disables the limit (matches vendor 4.2.0 nginx). |
| nginx.containerSecurityContext | object | `{"capabilities":{"add":["CHOWN","DAC_OVERRIDE","SETUID","SETGID","NET_BIND_SERVICE"]}}` | Capabilities required to start nginx in the component image; privilege escalation remains disabled. |
| nginx.image.repository | string | `"service/nginx"` | Vendor nginx image repository, relative to image.registry. A fully qualified repository may be used for an exact private mirror. |
| nginx.image.tag | string | `"1.23.3-alpine"` | Nginx image tag |
| nginx.nodeSelector | object | `{}` |  |
| nginx.proxyReadTimeout | string | `"60s"` | Upstream read timeout; increase in deployment values if needed. |
| nginx.replicas | int | `2` | Replica count |
| nginx.resources | object | `{"limits":{"cpu":"50m","memory":"64Mi"},"requests":{"cpu":"25m","memory":"32Mi"}}` | Resource requests and limits |
| nginx.tolerations | list | `[]` |  |
| nginx.trustForwardedProto | bool | `false` | Trust the original scheme only behind a trusted Ingress that overwrites X-Forwarded-Proto. Disable for direct router exposure. |
| nginx.websocketReadTimeout | string | `"60s"` | Separate WebSocket read timeout; align with heartbeat and Ingress settings. |
| nodeSelector | object | `{}` | Default node selector applied to all components. Per-component values override this. |
| notification.affinity | object | `{}` |  |
| notification.image.repository | string | `"doqa/doqa-notify"` | Notification image repository |
| notification.image.tag | string | `"4.3.0-box"` | Notification image tag |
| notification.nodeSelector | object | `{}` |  |
| notification.replicas | int | `1` | API replica count |
| notification.resources | object | `{"limits":{"cpu":"250m","memory":"256Mi"},"requests":{"cpu":"100m","memory":"128Mi"}}` | Resource requests and limits |
| notification.tolerations | list | `[]` |  |
| notification.worker.concurrency | int | `8` | Celery `--concurrency` value |
| notification.worker.replicas | int | `1` | Celery worker replica count |
| notification.worker.resources | object | `{"limits":{"cpu":"250m","memory":"256Mi"},"requests":{"cpu":"100m","memory":"128Mi"}}` | Worker resource requests and limits |
| podAnnotations | object | `{}` | Extra annotations to add to all pod templates. Per-component overrides are not supported — use this single map. |
| podDisruptionBudget.backend.minAvailable | int | `1` | Minimum number of backend pods that must remain available during disruptions |
| podDisruptionBudget.enabled | bool | `false` | Create PodDisruptionBudget resources for multi-replica components |
| podDisruptionBudget.frontend.minAvailable | int | `1` | Minimum number of frontend pods that must remain available during disruptions |
| podDisruptionBudget.queue.minAvailable | int | `1` | Minimum number of queue pods that must remain available during disruptions |
| podLabels | object | `{}` | Extra labels added to all chart-managed pod templates. Selector labels are reserved and ignored here. |
| postgresql.cnpg.create | bool | `true` | Provision a new CNPG `Cluster` resource. Requires CNPG operator in cluster |
| postgresql.cnpg.imageName | string | `"ghcr.io/cloudnative-pg/postgresql:17"` | CNPG postgres image |
| postgresql.cnpg.instances | int | `1` | Number of CNPG instances |
| postgresql.cnpg.storage.size | string | `"4Gi"` | PVC size for each CNPG instance |
| postgresql.cnpg.storage.storageClass | string | `""` | StorageClass for CNPG PVCs (empty = cluster default) |
| postgresql.database | string | `"doqa"` | Database name |
| postgresql.host | string | `""` | External PostgreSQL host (used only when cnpg.create=false) |
| postgresql.passwordSecret.key | string | `"password"` | Key inside the password secret |
| postgresql.passwordSecret.name | string | `""` | External secret name with the password (used when cnpg.create=false) |
| postgresql.port | int | `5432` | PostgreSQL port |
| postgresql.username | string | `"doqa"` | Database user |
| product.appBrand | string | `"DoQA"` | Backend application brand. (`APP_BRAND`) |
| product.appName | string | `"DoQA"` | Backend application name. (`APP_NAME`) |
| product.docsUrl | string | `"https://docs.doqa.app"` | Product documentation URL. (`PRODUCT_DOCS_URL`) |
| product.fromDisplay | string | `"DoQA"` | Notification email sender display name. (`PRODUCT_FROM_DISPLAY`) |
| product.id | string | `"doqa"` | Product slug. Custom products also require a matching frontend image. (`PRODUCT`) |
| product.name | string | `"DoQA"` | Product display name, also used in Python service titles. (`PRODUCT_NAME`) |
| product.siteUrl | string | `"https://doqa.app"` | Product website URL. (`PRODUCT_SITE_URL`) |
| product.supportEmail | string | `"support@doqa.app"` | Product support email used by notifications. (`PRODUCT_SUPPORT_EMAIL`) |
| product.supportTelegramUrl | string | `"https://t.me/doqa_team"` | Product support Telegram URL; empty hides the link. (`PRODUCT_SUPPORT_TELEGRAM_URL`) |
| product.telegramNewsUrl | string | `"https://t.me/DoQA_news_bot"` | Product Telegram news URL exposed to backend workloads; empty hides the link. (`PRODUCT_TELEGRAM_NEWS_URL`) |
| product.telegramUrl | string | `"https://t.me/DoQATMS"` | Product Telegram URL; empty hides the link. (`PRODUCT_TELEGRAM_URL`) |
| product.vkUrl | string | `"https://vk.com/doqa_tms"` | Product VK URL; empty hides the link. (`PRODUCT_VK_URL`) |
| product.youtubeUrl | string | `"https://www.youtube.com/channel/UCTzbumj-8d9ijeU3gEWWTPQ"` | Product YouTube URL; empty hides the link. (`PRODUCT_YOUTUBE_URL`) |
| pusher.appId | string | `"web-socket"` | Pusher protocol app id |
| pusher.appKey | string | `"web-socket"` | Pusher protocol app key |
| pusher.port | int | `6001` | Soketi exposed port |
| pusher.scheme | string | `"http"` | Pusher protocol scheme used for internal websocket calls |
| queue.affinity | object | `{}` |  |
| queue.nodeSelector | object | `{}` |  |
| queue.replicas | int | `3` | Queue worker replica count |
| queue.resources | object | `{"limits":{"cpu":"250m","memory":"256Mi"},"requests":{"cpu":"100m","memory":"128Mi"}}` | Resource requests and limits |
| queue.tolerations | list | `[]` |  |
| queue.waitForRabbitmq | bool | `true` | Wait for RabbitMQ AMQP readiness before starting the worker. Vendor 4.2.1 added a compose dependency on rabbitmq for the queue service; the chart mirrors that by probing the broker first. |
| rabbitmq.affinity | object | `{}` | Affinity for RabbitMQ pods. Overrides global affinity |
| rabbitmq.containerSecurityContext | object | `{"capabilities":{"add":["CHOWN","DAC_OVERRIDE","SETUID","SETGID"]}}` | Entrypoint capabilities for setting PVC ownership and switching to the rabbitmq user |
| rabbitmq.create | bool | `true` | Provision an in-tree RabbitMQ Deployment+PVC |
| rabbitmq.host | string | `""` | External RabbitMQ host (used only when create=false) |
| rabbitmq.image.repository | string | `"docker.io/rabbitmq"` | RabbitMQ image |
| rabbitmq.image.tag | string | `"4-management-alpine"` | RabbitMQ tag (management variant for built-in UI) |
| rabbitmq.nodeSelector | object | `{}` | Node selector for RabbitMQ pods. Overrides global nodeSelector |
| rabbitmq.port | int | `5672` | AMQP port |
| rabbitmq.resources | object | `{"limits":{"cpu":"250m","memory":"256Mi"},"requests":{"cpu":"100m","memory":"128Mi"}}` | Resource requests and limits |
| rabbitmq.storage.size | string | `"1Gi"` | PVC size for RabbitMQ |
| rabbitmq.storage.storageClass | string | `""` | StorageClass for RabbitMQ PVC |
| rabbitmq.tolerations | list | `[]` | Tolerations for RabbitMQ pods. Overrides global tolerations |
| rabbitmq.username | string | `"admin"` | RabbitMQ user |
| rabbitmq.virtualHost | string | `"/"` | RabbitMQ virtual host |
| redis.affinity | object | `{}` | Affinity for Redis pods. Overrides global affinity |
| redis.create | bool | `true` | Provision an in-tree Redis Deployment+PVC. Single replica, no HA |
| redis.db | int | `0` | Logical Redis DB for backend cache/queues |
| redis.host | string | `""` | External Redis host (used only when create=false) |
| redis.image.repository | string | `"docker.io/redis"` | Redis image |
| redis.image.tag | string | `"8-alpine"` | Redis tag |
| redis.nodeSelector | object | `{}` | Node selector for Redis pods. Overrides global nodeSelector |
| redis.notification.db | string | `"doqa"` | Notification logical DB (vendor uses string "doqa") |
| redis.notification.host | string | `""` | Notification Redis host (defaults to redis host when empty) |
| redis.notification.passwordSecret.key | string | `"password"` | Key inside the password secret |
| redis.notification.passwordSecret.name | string | `""` | Notification Redis password secret |
| redis.notification.port | int | `6379` | Notification Redis port |
| redis.passwordSecret.key | string | `"password"` | Key inside the password secret |
| redis.passwordSecret.name | string | `""` | External Redis password secret (leave empty for no auth) |
| redis.port | int | `6379` | Redis port |
| redis.resources | object | `{"limits":{"cpu":"250m","memory":"256Mi"},"requests":{"cpu":"100m","memory":"128Mi"}}` | Resource requests and limits |
| redis.storage.size | string | `"1Gi"` | PVC size for Redis |
| redis.storage.storageClass | string | `""` | StorageClass for Redis PVC |
| redis.tolerations | list | `[]` | Tolerations for Redis pods. Overrides global tolerations |
| secrets.apiKeys | string | `""` | Existing secret with keys `statistic-api-key`, `notification-api-key`, `llm-api-key`. Default <release>-api-keys |
| secrets.app | string | `""` | Existing secret with keys `app-key`, `jwt-secret`, `internal-system-key`. Default <release>-app-secrets |
| secrets.create | bool | `true` | Generate chart-managed secrets with random values |
| secrets.ldap | string | `""` | Existing secret with key `password`. Required only when ldap.enabled=true |
| secrets.mail | string | `""` | Existing secret with key `password`. Required only when mail.host is set and SMTP needs auth |
| secrets.minio | string | `""` | Existing secret with keys `access-key`, `secret-key`. Default <release>-minio-secrets |
| secrets.pusher | string | `""` | Existing secret with key `app-secret`. Default <release>-pusher-secret |
| secrets.rabbitmq | string | `""` | Existing secret with keys `password`, `erlang-cookie`. Default <release>-rabbitmq-secret |
| serviceAccount.annotations | object | `{}` | Annotations added to the chart-managed ServiceAccount |
| serviceAccount.create | bool | `false` | Create a dedicated ServiceAccount |
| serviceAccount.name | string | `""` | Existing ServiceAccount name when create=false |
| serviceMonitor.enabled | bool | `false` | Create a Prometheus Operator ServiceMonitor for the backend Service |
| serviceMonitor.interval | string | `""` | Scrape interval (Prometheus duration format, e.g. 30s, 1m) |
| serviceMonitor.labels | object | `{}` | Labels for Prometheus to select the ServiceMonitor |
| serviceMonitor.namespace | string | `""` | Namespace to deploy the ServiceMonitor into (defaults to the release namespace when empty) |
| serviceMonitor.scrapeTimeout | string | `""` | Scrape timeout (Prometheus duration format, e.g. 10s, 30s) |
| statistic.affinity | object | `{}` |  |
| statistic.image.repository | string | `"doqa/doqa-statistic"` | Statistic image repository |
| statistic.image.tag | string | `"4.3.0-box"` | Statistic image tag |
| statistic.nodeSelector | object | `{}` |  |
| statistic.replicas | int | `1` | Replica count |
| statistic.resources | object | `{"limits":{"cpu":"250m","memory":"256Mi"},"requests":{"cpu":"100m","memory":"128Mi"}}` | Resource requests and limits |
| statistic.tolerations | list | `[]` |  |
| telegramBot.affinity | object | `{}` |  |
| telegramBot.botName | string | `""` | Bot username (BOT_NAME) |
| telegramBot.enabled | bool | `false` | Enable telegram bot |
| telegramBot.image.repository | string | `"doqa/doqa-telegram-bot"` | Telegram bot image repository |
| telegramBot.image.tag | string | `"4.3.0-box"` | Telegram bot image tag |
| telegramBot.nodeSelector | object | `{}` |  |
| telegramBot.replicas | int | `1` | Replica count |
| telegramBot.resources | object | `{"limits":{"cpu":"250m","memory":"256Mi"},"requests":{"cpu":"100m","memory":"128Mi"}}` | Resource requests and limits |
| telegramBot.tokenSecret | string | `""` | Existing secret with key `token` for the Telegram bot token |
| telegramBot.tolerations | list | `[]` |  |
| tolerations | list | `[]` | Default tolerations applied to all components. Per-component values override this. |
| topologySpreadConstraints.backend | list | `[]` |  |
| topologySpreadConstraints.frontend | list | `[]` |  |
| topologySpreadConstraints.queue | list | `[]` |  |
| useSsl | bool | `true` | Whether the public URL is HTTPS. Affects USE_SSL env and bucket URL protocol |
| websocket.affinity | object | `{}` |  |
| websocket.image.repository | string | `"service/soketi"` | Vendor Soketi image repository, relative to image.registry. A fully qualified repository may be used for an exact private mirror. |
| websocket.image.tag | string | `"16-alpine"` | Soketi image tag |
| websocket.nodeSelector | object | `{}` |  |
| websocket.replicas | int | `1` | Replica count |
| websocket.resources | object | `{"limits":{"cpu":"100m","memory":"128Mi"},"requests":{"cpu":"50m","memory":"64Mi"}}` | Resource requests and limits |
| websocket.tolerations | list | `[]` |  |

## Upgrading

This chart targets DoQA 4.1.0+. There is no automatic migration path from
3.x deployments — vendor changed the queue broker from Redis to RabbitMQ
between 3.7 and 4.0. Plan a stepwise migration if you are coming from a
3.x install.

### 0.9.x → 0.10.0

- **DoQA 4.3.5**: pins backend to `4.3.6-box`, frontend to `4.3.3-box`,
  and autotest-parser to `4.3.1-box`, matching the vendor box archive.
- **Product branding**: new `product.*` values populate the backend environment,
  notification API/worker and optional Telegram bot. Python service titles use
  `product.name`. Defaults match the vendor DoQA brand; optional social links
  accept empty strings. `mail.fromName` and `mailIssue` retain their existing,
  independently configured values.
- A custom product requires its own compiled frontend image (`frontend.image`)
  in addition to `product.*` settings; these settings do not rebrand the stock SPA.
- The LLM's internal `STATISTIC_HOST` is retained: the vendor removed it only
  from the with-database Compose variant while keeping the same LLM image and
  the setting in the other variant. Kubernetes continues using its statistic Service.
- Image metadata audit found unchanged Entrypoint/Cmd for all three changed
  images. Backend PHP advances from 8.4.23 to 8.4.27; no other image Env changes
  were found. nginx configuration is unchanged. Existing PVCs and secret names
  are preserved; application migrations run during the backend rollout as before.

### 0.8.x → 0.9.0

- The scheduler remains a Deployment running `schedule:work`; no CronJob is added.
- Default MinIO and client versions are unchanged from 0.8.x; there is no
  automatic downgrade to the older vendor image. Bucket initialization supports
  both `mc` and `mcli` and fails immediately if neither client is available.
- The global securityContext remains restrictive. Backend/frontend and bundled
  RabbitMQ receive CHOWN, DAC_OVERRIDE, SETUID and SETGID; the nginx router also
  receives NET_BIND_SERVICE. Current images need these capabilities to run
  nginx/FPM and set RabbitMQ PVC ownership before switching users.
  `allowPrivilegeEscalation` remains false. This is not a PSA restricted profile;
  that environment requires compatible images and permission settings.
- Backend readiness requests `/`: HTTP 2xx–4xx succeed, while 5xx, transport
  errors and timeouts fail. In the current image, the request passes through FPM
  and returns 404; the static `/api/docs` endpoint cannot check FPM health.
  This checks availability, not business functionality. Recheck the route and
  curl availability when upgrading the image. TCP liveness is retained to avoid
  restart loops during FPM overload or database failures; it does not detect
  every hang. Both probes are configurable; `backend.readinessProbe: null` and
  `backend.livenessProbe: null` disable them. When changing probe types, set the
  previous handler to null (for example, `exec: null`), since Helm merges values maps.
- Optional `backend.phpFpm.enabled` defaults to false. An init container copies
  the configuration from the same backend image version, appends max_children,
  validates it with `php-fpm -t` and shares it with the main container via emptyDir.
  Other image settings and the original CMD are preserved. An invalid combination
  with inherited pool settings stops initialization with FPM diagnostics.
  The `fpm-config` volume name is reserved when this feature is enabled.
  `backend.phpFpm.maxChildren` defaults to 5. Size resources using measurements
  when increasing it; memory limits and replica counts do not change automatically.
- For TLS termination at a trusted Ingress, enable `nginx.trustForwardedProto: true`.
  The Ingress must overwrite incoming X-Forwarded-Proto headers. Trust is disabled
  by default. When enabled, only http/https are accepted; an empty or other value
  falls back to `$scheme`. Do not expose a header-trusting router directly to clients.
- `nginx.proxyReadTimeout` and `nginx.websocketReadTimeout` are independently
  configurable and both default to 60s. Align them with Ingress timeouts and
  WebSocket heartbeat settings for your workload.
- `backend.skipMigrate` disables only the migration init container. The current
  image CMD also runs migrations; this release does not change their lifecycle.

Example deployment settings (size these values using measurements):

```yaml
nginx:
  trustForwardedProto: true
  proxyReadTimeout: 120s
  websocketReadTimeout: 3600s
backend:
  phpFpm:
    enabled: true
    maxChildren: 20
  resources:
    requests:
      cpu: 500m
      memory: 384Mi
    limits:
      cpu: 2000m
      memory: 2Gi
```

#### MinIO images for a fresh test deployment

The registry may not provide manifests for the MinIO/mc image tags pinned in
the 0.8.x defaults. The 0.9.0 defaults preserve those values for upgrade
compatibility; for fresh installations, explicitly select images from the
DoQA 4.3.4 Compose configuration:

```yaml
minio:
  image:
    repository: registry.control.doqa.app/service/minio
    tag: 20240527.191746-r2-alpine
  client:
    image:
      repository: registry.control.doqa.app/service/mc
      tag: 20240527.191746-r2-alpine
```

This example is intended for a fresh installation with empty storage.
Do not apply it to a PVC previously used by a newer MinIO version: downgrade
compatibility has not been tested. When upgrading, retain the explicitly pinned
images of the existing deployment and plan any migration separately.

### 0.7.x → 0.8.0

- **DoQA 4.3.4**: pins backend to `4.3.3-box` and frontend to
  `4.3.1-box`, matching the vendor archive. Other component pins are unchanged.
- **Autotest-parser URLs**: the parser now receives the existing `apiBaseUrl`
  (`API_BASE_URL`) and the new `doqaBackendUrl` (`DOQA_BACKEND_URL`). The latter
  also reaches backend workloads through the shared environment ConfigMap;
  its empty default matches the vendor configuration.

### 0.6.x → 0.7.0

- **DoQA 4.3.1**: bumps backend (4.3.1-box), frontend (4.3.0-box),
  autotest-parser (4.3.0-box), statistic (4.3.0-box), notification
  (4.3.0-box), llm (4.3.0-box), and telegram-bot (4.3.0-box).
- **`autotestResultParser` removed**: vendor 4.3.1 deleted the
  `doqa_autotest_result_parser` service. The chart drops the
  `autotest-result-parser` Deployment and the whole `autotestResultParser`
  values section; remove it from your values files.
- **New worker Deployments**: vendor 4.3.1 split the queue topology.
  `queue` now consumes `default,search,requirements,autotests-domain,outbound-webhooks,import`;
  the new `autotests-worker` Deployment (`autotestsWorker.*` values, backend
  image) declares all RabbitMQ queues and runs
  `autotestsWorker.workerProcesses` parallel `autotests:work` consumers per
  pod; the new single-replica `llm-bulk-queue` Deployment
  (`llmBulkQueue.*` values) consumes `llm-bulk` with a 3660s timeout.
  The autotests-worker declares its 8 RabbitMQ queues with durable/no-args
  parameters on startup; if the broker contains hand-redeclared legacy
  queues with different parameters, the worker will fail with
  `PRECONDITION_FAILED` — stock queues created by previous chart/vendor
  versions are unaffected.
- **New generated secret**: `INTERNAL_SYSTEM_KEY` (vendor
  `GENERATE_SECRET_KEY`) is added to the chart-managed app Secret. With
  `secrets.create=true` it is generated automatically on upgrade; with
  `secrets.create=false` or `secrets.app` pointing at a pre-existing secret,
  add the new `internal-system-key` key yourself.
- **New ConfigMap keys**: `MINIO_USE_PATH_STYLE=true`,
  `QUEUE_BATCHING_CONNECTION=pgsql`, and `AUTOTEST_PARSER_SERVICE_URL`
  (computed from the autotest-parser Service name).
- **autotest-parser** now receives explicit `MINIO_*` credentials and
  `INTERNAL_SYSTEM_KEY`, matching the vendor 4.3.1 compose environment.

### 0.5.1 → 0.6.0

- **DoQA 4.2.1**: bumps backend (4.2.10-box) and frontend (4.2.9-box).
  All other component pins are unchanged.
- **Queue names**: the worker now consumes `requirements,default,import,llm-bulk`
  instead of `high,default`, following the vendor 4.2.1 compose change.
- **RabbitMQ readiness for the queue worker**: vendor 4.2.1 added a compose
  dependency on RabbitMQ for the queue service. The chart now runs a
  `wait-for-rabbitmq` initContainer on the queue Deployment. Disable it with
  `queue.waitForRabbitmq=false`.
- **RabbitMQ node identity**: the in-tree RabbitMQ pod now sets a stable
  `hostname` so the broker restarts as the same Erlang node after pod
  recreation and keeps its mnesia data on the PVC. Before this change every
  pod recreation silently discarded unprocessed messages. Do not change
  the hostname after install.
- **`ISSUE_MAIL`**: vendor renamed `MAIL_ISSUE` to `ISSUE_MAIL`; the ConfigMap
  key follows. The `mailIssue` value is unchanged.

### 0.4.0 → 0.5.0

- **DoQA 4.2.0**: bumps backend (4.2.4-box), frontend (4.2.4-box),
  autotest-parser (4.2.0-box), autotest-result-parser (4.2.0-box),
  notification (4.2.1-box), and llm (4.2.1-box). statistic (3.0.0-box)
  and telegram-bot (1.0.1-box) are unchanged.
- **Migration ordering**: vendor 4.2.0 added a compose dependency on
  RabbitMQ for the migration step because some migrations dispatch jobs.
  The chart now runs a `wait-for-rabbitmq` initContainer that probes the
  AMQP port before `php artisan migrate`. Disable it with
  `backend.migrate.waitForRabbitmq=false`.
- **nginx upload limit**: `nginx.clientMaxBodySize` now defaults to `0`
  (unlimited), matching the vendor 4.2.0 nginx configuration. Set it back
  to a byte size (e.g. `150M`) to restore an explicit cap.

### 0.3.8 → 0.4.0

With unchanged values, this upgrade does not change application images,
environment variables, nginx routes, Services, PVCs, or the CNPG Cluster.
Because the existing ConfigMap checksum includes chart metadata, Kubernetes
will roll the backend, queue, cron, both autotest parsers, and nginx once.
The backend migration initContainer runs during that rollout; with unchanged
DoQA 4.1.2 images it has no new application migration to apply. In-tree MinIO
installs rerun the idempotent bucket-init hook; external MinIO installs do not
render it.

- Fully qualified nginx and Soketi image repositories now bypass the global
  DoQA image registry, allowing exact vendor images to be served from private
  registry mirrors without changing the recommended vendor-registry defaults.
- The MinIO bucket-init Job now honors the configured ServiceAccount, pod
  labels and annotations, global or client-specific scheduling,
  client-specific security contexts, and resource requests/limits.
- Added `serviceAccount.annotations` and `podLabels` for clusters with identity
  integrations and admission policies.
- Documented the upstream source of truth, compatibility boundaries, amd64
  requirement, and GitOps secret handling. DoQA application pins remain aligned
  with the vendor `4.1.2` archive.

### 0.3.7 → 0.3.8

- **DoQA 4.1.2**: bumps backend (4.1.14-box), frontend (4.1.6-box),
  autotest-parser (4.1.3-box).
- **New env var**: `API_BASE_URL` added per upstream 4.1.2 configs.
  Defaults to empty (uses internal backend service). Set
  `apiBaseUrl` if the frontend should reach the API via a different URL.

### 0.2.x → 0.3.0

- **DoQA 4.1.0**: the chart adds the new `llm` service and updates all vendor
  application image tags.
- **Queue default changed**: `queue.replicas` now defaults to `3`, matching the
  vendor `QUEUE_WORKERS=3` setting.
- **API key secret expanded**: when `secrets.create=false` or
  `secrets.apiKeys` points to a pre-existing secret, add the new
  `llm-api-key` key. Chart-managed secrets generate it automatically during
  upgrade.

### 0.1.x → 0.2.0

- **Resource defaults**: all components now ship concrete `requests`/`limits`
  instead of empty `{}`. If your pods consume more memory than the new limits
  (e.g. backend `512Mi`), they will be OOMKilled after upgrade. Check current
  usage with `kubectl top pods` and override per-component resources in your
  values before upgrading.
- **Security context keys renamed**: `podSecurityContext` →
  `defaultSecurityContext.pod`, `securityContext` →
  `defaultSecurityContext.container`. If you customized the old keys, move
  your values to the new paths before upgrading — the old keys are silently
  ignored.

## Maintainers

| Name | Email | Url |
| ---- | ------ | --- |
| batonogov |  | <https://github.com/batonogov> |

## Source Code

* <https://github.com/batonogov/helm-charts>
* <https://docs.doqa.app>
