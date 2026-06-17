# doqa

DoQA Test Case Management System (TCMS) self-hosted on Kubernetes

![Version: 0.3.2](https://img.shields.io/badge/Version-0.3.2-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square) ![AppVersion: 4.1.0-box](https://img.shields.io/badge/AppVersion-4.1.0--box-informational?style=flat-square)

**Homepage:** <https://doqa.app>

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
- Helm 3.14+ (Helm 4 supported)
- An Ingress controller routable from the public DNS pointing to `appUrl`
- For TLS: cert-manager with a working ClusterIssuer (or a pre-provisioned TLS secret)
- For PostgreSQL via CNPG (default): the
  [CloudNativePG](https://cloudnative-pg.io/) operator already installed in
  the cluster (typically in `cnpg-system`)
- Storage class supporting `ReadWriteOnce` PVCs

The DoQA application images live at `registry.control.doqa.app` and pull
anonymously — no `imagePullSecrets` are required by default.

## Architecture

Components mirror the vendor docker-compose for v4.1.0:

- `backend` (php-fpm Laravel API), `queue` (`queue:work`), `cron` (`schedule:work`)
- `frontend` (Nuxt SPA)
- `autotest-parser`, `autotest-result-parser` (RabbitMQ-driven)
- `statistic`, `llm`, `notification` (+ Celery worker), `telegram-bot` (optional)
- `websocket` (Soketi, Pusher protocol)
- `nginx` (internal router) → exposed via Ingress

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
| `<release>-app-secrets` | `app-key`, `jwt-secret` |
| `<release>-api-keys` | `statistic-api-key`, `notification-api-key`, `llm-api-key` |
| `<release>-pusher-secret` | `app-secret` |
| `<release>-rabbitmq-secret` | `password`, `erlang-cookie` |
| `<release>-minio-secrets` | `access-key`, `secret-key` |

The mail and LDAP passwords are always user-provided through `secrets.mail`
and `secrets.ldap`.

## Requirements

Kubernetes: `>=1.32.0-0`

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| affinity | object | `{}` | Default affinity applied to all components. Per-component values override this. |
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
| autotestParser.image.tag | string | `"4.1.0-box"` | Autotest parser image tag |
| autotestParser.nodeSelector | object | `{}` |  |
| autotestParser.replicas | int | `1` | Autotest parser replica count |
| autotestParser.resources | object | `{"limits":{"cpu":"250m","memory":"256Mi"},"requests":{"cpu":"100m","memory":"128Mi"}}` | Resource requests and limits |
| autotestParser.tolerations | list | `[]` |  |
| autotestResultParser.affinity | object | `{}` |  |
| autotestResultParser.image.repository | string | `"doqa/doqa-autotest-result-parser"` | Result parser image repository |
| autotestResultParser.image.tag | string | `"2.0.0-box"` | Result parser image tag |
| autotestResultParser.nodeSelector | object | `{}` |  |
| autotestResultParser.replicas | int | `1` | Result parser replica count |
| autotestResultParser.resources | object | `{"limits":{"cpu":"250m","memory":"256Mi"},"requests":{"cpu":"100m","memory":"128Mi"}}` | Resource requests and limits |
| autotestResultParser.tolerations | list | `[]` |  |
| backend.affinity | object | `{}` |  |
| backend.image.repository | string | `"doqa/doqa-backend"` | Backend image repository (relative to image.registry) |
| backend.image.tag | string | `"4.1.13-box"` | Backend image tag |
| backend.nodeSelector | object | `{}` |  |
| backend.replicas | int | `2` | Backend replica count |
| backend.resources | object | `{"limits":{"cpu":"500m","memory":"512Mi"},"requests":{"cpu":"250m","memory":"256Mi"}}` | Resource requests and limits |
| backend.skipMigrate | bool | `false` |  |
| backend.tolerations | list | `[]` |  |
| cron.affinity | object | `{}` |  |
| cron.nodeSelector | object | `{}` |  |
| cron.resources | object | `{"limits":{"cpu":"250m","memory":"256Mi"},"requests":{"cpu":"100m","memory":"128Mi"}}` | Resource requests and limits |
| cron.tolerations | list | `[]` |  |
| debug | bool | `false` | Enable verbose debug logging |
| defaultSecurityContext.container.allowPrivilegeEscalation | bool | `false` |  |
| defaultSecurityContext.container.capabilities.drop[0] | string | `"ALL"` |  |
| defaultSecurityContext.pod | object | `{}` |  |
| extraAnnotations | object | `{}` | Extra annotations added to every resource |
| extraLabels | object | `{}` | Extra labels added to every resource |
| extraVolumeMounts | list | `[]` | Extra volume mounts to add to all containers |
| extraVolumes | list | `[]` | Extra volumes to add to all Deployments |
| frontend.affinity | object | `{}` |  |
| frontend.image.repository | string | `"doqa/doqa-frontend"` | Frontend image repository (relative to image.registry) |
| frontend.image.tag | string | `"4.1.4-box"` | Frontend image tag |
| frontend.nodeSelector | object | `{}` |  |
| frontend.replicas | int | `2` | Frontend replica count |
| frontend.resources | object | `{"limits":{"cpu":"500m","memory":"512Mi"},"requests":{"cpu":"250m","memory":"256Mi"}}` | Resource requests and limits |
| frontend.tolerations | list | `[]` |  |
| fullnameOverride | string | `""` | Override the full name of resources |
| image.pullPolicy | string | `"IfNotPresent"` | Default imagePullPolicy |
| image.pullSecrets | list | `[]` | imagePullSecrets applied to every Deployment |
| image.registry | string | `"registry.control.doqa.app"` | Container registry hosting DoQA images |
| ingress.annotations | object | `{}` | Extra annotations (e.g. cert-manager.io/cluster-issuer) |
| ingress.className | string | `""` | IngressClassName (e.g. nginx, traefik) |
| ingress.enabled | bool | `true` | Create the Ingress resource |
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
| llm.image.tag | string | `"1.0.5-box"` | LLM image tag |
| llm.nodeSelector | object | `{}` |  |
| llm.replicas | int | `1` | Replica count |
| llm.resources | object | `{"limits":{"cpu":"250m","memory":"256Mi"},"requests":{"cpu":"100m","memory":"128Mi"}}` | Resource requests and limits |
| llm.tolerations | list | `[]` |  |
| mail.encryption | string | `"tls"` | Encryption (tls/ssl/null) |
| mail.fromAddress | string | `""` | Sender address |
| mail.fromName | string | `"DoQA"` | Sender display name |
| mail.host | string | `""` | SMTP host (leave empty to disable mail) |
| mail.mailer | string | `"smtp"` | Mailer driver |
| mail.port | int | `587` | SMTP port |
| mail.username | string | `""` | SMTP user |
| mailIssue | string | `"support@doqa.app"` | Issue/support email exposed to backend (`MAIL_ISSUE`) |
| minio.affinity | object | `{}` | Affinity for MinIO pods. Overrides global affinity |
| minio.bucket | string | `"doqa"` | Bucket name |
| minio.bucketUrl | string | `""` | Public bucket URL (defaults to "<scheme>://<appUrl>/<bucket>" when empty, served via internal nginx) |
| minio.client.image.repository | string | `"quay.io/minio/mc"` | mc client image (used by bucket-init Job) |
| minio.client.image.tag | string | `"RELEASE.2025-08-13T08-35-41Z"` | mc tag |
| minio.create | bool | `true` | Provision an in-tree MinIO Deployment+PVC + bucket-init Job |
| minio.endpoint | string | `""` | External MinIO/S3 endpoint (used only when create=false). For in-tree MinIO chart computes internal URL automatically |
| minio.image.repository | string | `"quay.io/minio/minio"` | MinIO image |
| minio.image.tag | string | `"RELEASE.2025-04-22T22-12-26Z"` | MinIO tag |
| minio.nodeSelector | object | `{}` | Node selector for MinIO pods. Overrides global nodeSelector |
| minio.region | string | `"ru-1"` | Region |
| minio.resources | object | `{"limits":{"cpu":"500m","memory":"512Mi"},"requests":{"cpu":"250m","memory":"256Mi"}}` | Resource requests and limits |
| minio.storage.size | string | `"4Gi"` | PVC size for MinIO |
| minio.storage.storageClass | string | `""` | StorageClass for MinIO PVC |
| minio.tolerations | list | `[]` | Tolerations for MinIO pods. Overrides global tolerations |
| nameOverride | string | `""` | Override the chart name part of resource names |
| networkPolicy.enabled | bool | `false` | Enable NetworkPolicy resources. Creates a default-deny-ingress policy and explicit allow rules for all internal traffic paths |
| nginx.affinity | object | `{}` |  |
| nginx.clientMaxBodySize | string | `"150M"` | Maximum upload size |
| nginx.image.repository | string | `"service/nginx"` | Nginx image repository (override to docker.io/nginx if no vendor mirror access) |
| nginx.image.tag | string | `"1.23.3-alpine"` | Nginx image tag |
| nginx.nodeSelector | object | `{}` |  |
| nginx.replicas | int | `2` | Replica count |
| nginx.resources | object | `{"limits":{"cpu":"50m","memory":"64Mi"},"requests":{"cpu":"25m","memory":"32Mi"}}` | Resource requests and limits |
| nginx.tolerations | list | `[]` |  |
| nodeSelector | object | `{}` | Default node selector applied to all components. Per-component values override this. |
| notification.affinity | object | `{}` |  |
| notification.image.repository | string | `"doqa/doqa-notify"` | Notification image repository |
| notification.image.tag | string | `"2.0.2-box"` | Notification image tag |
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
| pusher.appId | string | `"web-socket"` | Pusher protocol app id |
| pusher.appKey | string | `"web-socket"` | Pusher protocol app key |
| pusher.port | int | `6001` | Soketi exposed port |
| pusher.scheme | string | `"http"` | Pusher protocol scheme used for internal websocket calls |
| queue.affinity | object | `{}` |  |
| queue.nodeSelector | object | `{}` |  |
| queue.replicas | int | `3` | Queue worker replica count |
| queue.resources | object | `{"limits":{"cpu":"250m","memory":"256Mi"},"requests":{"cpu":"100m","memory":"128Mi"}}` | Resource requests and limits |
| queue.tolerations | list | `[]` |  |
| rabbitmq.affinity | object | `{}` | Affinity for RabbitMQ pods. Overrides global affinity |
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
| redis.image.tag | string | `"7-alpine"` | Redis tag |
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
| secrets.app | string | `""` | Existing secret with keys `app-key`, `jwt-secret`. Default <release>-app-secrets |
| secrets.create | bool | `true` | Generate chart-managed secrets with random values |
| secrets.ldap | string | `""` | Existing secret with key `password`. Required only when ldap.enabled=true |
| secrets.mail | string | `""` | Existing secret with key `password`. Required only when mail.host is set and SMTP needs auth |
| secrets.minio | string | `""` | Existing secret with keys `access-key`, `secret-key`. Default <release>-minio-secrets |
| secrets.pusher | string | `""` | Existing secret with key `app-secret`. Default <release>-pusher-secret |
| secrets.rabbitmq | string | `""` | Existing secret with keys `password`, `erlang-cookie`. Default <release>-rabbitmq-secret |
| serviceAccount.create | bool | `false` | Create a dedicated ServiceAccount |
| serviceAccount.name | string | `""` | Existing ServiceAccount name when create=false |
| serviceMonitor.enabled | bool | `false` | Create a Prometheus Operator ServiceMonitor for the backend Service |
| serviceMonitor.interval | string | `""` | Scrape interval (Prometheus duration format, e.g. 30s, 1m) |
| serviceMonitor.labels | object | `{}` | Labels for Prometheus to select the ServiceMonitor |
| serviceMonitor.namespace | string | `""` | Namespace to deploy the ServiceMonitor into (defaults to the release namespace when empty) |
| serviceMonitor.scrapeTimeout | string | `""` | Scrape timeout (Prometheus duration format, e.g. 10s, 30s) |
| statistic.affinity | object | `{}` |  |
| statistic.image.repository | string | `"doqa/doqa-statistic"` | Statistic image repository |
| statistic.image.tag | string | `"3.0.0-box"` | Statistic image tag |
| statistic.nodeSelector | object | `{}` |  |
| statistic.replicas | int | `1` | Replica count |
| statistic.resources | object | `{"limits":{"cpu":"250m","memory":"256Mi"},"requests":{"cpu":"100m","memory":"128Mi"}}` | Resource requests and limits |
| statistic.tolerations | list | `[]` |  |
| telegramBot.affinity | object | `{}` |  |
| telegramBot.botName | string | `""` | Bot username (BOT_NAME) |
| telegramBot.enabled | bool | `false` | Enable telegram bot |
| telegramBot.image.repository | string | `"doqa/doqa-telegram-bot"` | Telegram bot image repository |
| telegramBot.image.tag | string | `"1.0.1-box"` | Telegram bot image tag |
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
| websocket.image.repository | string | `"service/soketi"` | Soketi image repository (defaults to vendor mirror, override to `quay.io/soketi/soketi`) |
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
