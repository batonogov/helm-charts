# doqa

DoQA Test Case Management System (TCMS) self-hosted on Kubernetes

![Version: 0.1.2](https://img.shields.io/badge/Version-0.1.2-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square) ![AppVersion: 4.0.0-box](https://img.shields.io/badge/AppVersion-4.0.0--box-informational?style=flat-square)

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

Components mirror the vendor docker-compose for v4.0.0:

- `backend` (php-fpm Laravel API), `queue` (`queue:work`), `cron` (`schedule:work`)
- `frontend` (Nuxt SPA)
- `autotest-parser`, `autotest-result-parser` (RabbitMQ-driven)
- `statistic`, `notification` (+ Celery worker), `telegram-bot` (optional)
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
| `<release>-api-keys` | `statistic-api-key`, `notification-api-key` |
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
| appFrontendUrl | string | `""` | Frontend URL (defaults to appUrl when empty) |
| appUrl | string | `"doqa.example.com"` | DoQA application URL (host without protocol, e.g. "doqa.example.com") |
| autotestParser.affinity | object | `{}` |  |
| autotestParser.image.repository | string | `"doqa/doqa-parsing-autotests"` | Autotest parser image repository |
| autotestParser.image.tag | string | `"3.0.2-box"` | Autotest parser image tag |
| autotestParser.nodeSelector | object | `{}` |  |
| autotestParser.replicas | int | `1` | Autotest parser replica count |
| autotestParser.resources | object | `{}` | Container resources |
| autotestParser.tolerations | list | `[]` |  |
| autotestResultParser.affinity | object | `{}` |  |
| autotestResultParser.image.repository | string | `"doqa/doqa-autotest-result-parser"` | Result parser image repository |
| autotestResultParser.image.tag | string | `"1.0.1-box"` | Result parser image tag |
| autotestResultParser.nodeSelector | object | `{}` |  |
| autotestResultParser.replicas | int | `1` | Result parser replica count |
| autotestResultParser.resources | object | `{}` | Container resources |
| autotestResultParser.tolerations | list | `[]` |  |
| backend.affinity | object | `{}` |  |
| backend.image.repository | string | `"doqa/doqa-backend"` | Backend image repository (relative to image.registry) |
| backend.image.tag | string | `"4.0.2-box"` | Backend image tag |
| backend.nodeSelector | object | `{}` |  |
| backend.replicas | int | `2` | Backend replica count |
| backend.resources | object | `{}` | Container resources |
| backend.skipMigrate | bool | `false` |  |
| backend.tolerations | list | `[]` |  |
| cron.affinity | object | `{}` |  |
| cron.nodeSelector | object | `{}` |  |
| cron.resources | object | `{}` | Container resources |
| cron.tolerations | list | `[]` |  |
| debug | bool | `false` | Enable verbose debug logging |
| extraAnnotations | object | `{}` | Extra annotations added to every resource |
| extraLabels | object | `{}` | Extra labels added to every resource |
| frontend.affinity | object | `{}` |  |
| frontend.image.repository | string | `"doqa/doqa-frontend"` | Frontend image repository (relative to image.registry) |
| frontend.image.tag | string | `"4.0.2-box"` | Frontend image tag |
| frontend.nodeSelector | object | `{}` |  |
| frontend.replicas | int | `2` | Frontend replica count |
| frontend.resources | object | `{}` | Container resources |
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
| mail.encryption | string | `"tls"` | Encryption (tls/ssl/null) |
| mail.fromAddress | string | `""` | Sender address |
| mail.fromName | string | `"DoQA"` | Sender display name |
| mail.host | string | `""` | SMTP host (leave empty to disable mail) |
| mail.mailer | string | `"smtp"` | Mailer driver |
| mail.port | int | `587` | SMTP port |
| mail.username | string | `""` | SMTP user |
| mailIssue | string | `"support@doqa.app"` | Issue/support email exposed to backend (`MAIL_ISSUE`) |
| minio.bucket | string | `"doqa"` | Bucket name |
| minio.bucketUrl | string | `""` | Public bucket URL (defaults to "<scheme>://<appUrl>/<bucket>" when empty, served via internal nginx) |
| minio.client.image.repository | string | `"quay.io/minio/mc"` | mc client image (used by bucket-init Job) |
| minio.client.image.tag | string | `"RELEASE.2025-08-13T08-35-41Z"` | mc tag |
| minio.create | bool | `true` | Provision an in-tree MinIO Deployment+PVC + bucket-init Job |
| minio.endpoint | string | `""` | External MinIO/S3 endpoint (used only when create=false). For in-tree MinIO chart computes internal URL automatically |
| minio.image.repository | string | `"quay.io/minio/minio"` | MinIO image |
| minio.image.tag | string | `"RELEASE.2025-04-22T22-12-26Z"` | MinIO tag |
| minio.region | string | `"ru-1"` | Region |
| minio.resources | object | `{}` | Container resources |
| minio.storage.size | string | `"4Gi"` | PVC size for MinIO |
| minio.storage.storageClass | string | `""` | StorageClass for MinIO PVC |
| nameOverride | string | `""` | Override the chart name part of resource names |
| networkPolicy.enabled | bool | `false` | Enable NetworkPolicy resources. Creates a default-deny-ingress policy and explicit allow rules for all internal traffic paths |
| nginx.affinity | object | `{}` |  |
| nginx.clientMaxBodySize | string | `"150M"` | Maximum upload size |
| nginx.image.repository | string | `"service/nginx"` | Nginx image repository (override to docker.io/nginx if no vendor mirror access) |
| nginx.image.tag | string | `"1.23.3-alpine"` | Nginx image tag |
| nginx.nodeSelector | object | `{}` |  |
| nginx.replicas | int | `2` | Replica count |
| nginx.resources | object | `{}` | Container resources |
| nginx.tolerations | list | `[]` |  |
| notification.affinity | object | `{}` |  |
| notification.image.repository | string | `"doqa/doqa-notify"` | Notification image repository |
| notification.image.tag | string | `"1.0.15-box"` | Notification image tag |
| notification.nodeSelector | object | `{}` |  |
| notification.replicas | int | `1` | API replica count |
| notification.resources | object | `{}` | API container resources |
| notification.tolerations | list | `[]` |  |
| notification.worker.concurrency | int | `8` | Celery `--concurrency` value |
| notification.worker.replicas | int | `1` | Celery worker replica count |
| notification.worker.resources | object | `{}` | Worker container resources |
| podSecurityContext | object | `{}` | Pod-level securityContext applied to every Pod |
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
| queue.affinity | object | `{}` |  |
| queue.nodeSelector | object | `{}` |  |
| queue.replicas | int | `1` | Queue worker replica count |
| queue.resources | object | `{}` | Container resources |
| queue.tolerations | list | `[]` |  |
| rabbitmq.create | bool | `true` | Provision an in-tree RabbitMQ Deployment+PVC |
| rabbitmq.host | string | `""` | External RabbitMQ host (used only when create=false) |
| rabbitmq.image.repository | string | `"docker.io/rabbitmq"` | RabbitMQ image |
| rabbitmq.image.tag | string | `"4-management-alpine"` | RabbitMQ tag (management variant for built-in UI) |
| rabbitmq.port | int | `5672` | AMQP port |
| rabbitmq.resources | object | `{}` | Container resources |
| rabbitmq.storage.size | string | `"1Gi"` | PVC size for RabbitMQ |
| rabbitmq.storage.storageClass | string | `""` | StorageClass for RabbitMQ PVC |
| rabbitmq.username | string | `"admin"` | RabbitMQ user |
| rabbitmq.virtualHost | string | `"/"` | RabbitMQ virtual host |
| redis.create | bool | `true` | Provision an in-tree Redis Deployment+PVC. Single replica, no HA |
| redis.db | int | `0` | Logical Redis DB for backend cache/queues |
| redis.host | string | `""` | External Redis host (used only when create=false) |
| redis.image.repository | string | `"docker.io/redis"` | Redis image |
| redis.image.tag | string | `"7-alpine"` | Redis tag |
| redis.notification.db | string | `"doqa"` | Notification logical DB (vendor uses string "doqa") |
| redis.notification.host | string | `""` | Notification Redis host (defaults to redis host when empty) |
| redis.notification.passwordSecret.key | string | `"password"` | Key inside the password secret |
| redis.notification.passwordSecret.name | string | `""` | Notification Redis password secret |
| redis.notification.port | int | `6379` | Notification Redis port |
| redis.passwordSecret.key | string | `"password"` | Key inside the password secret |
| redis.passwordSecret.name | string | `""` | External Redis password secret (leave empty for no auth) |
| redis.port | int | `6379` | Redis port |
| redis.resources | object | `{}` | Container resources |
| redis.storage.size | string | `"1Gi"` | PVC size for Redis |
| redis.storage.storageClass | string | `""` | StorageClass for Redis PVC |
| secrets.apiKeys | string | `""` | Existing secret with keys `statistic-api-key`, `notification-api-key`. Default <release>-api-keys |
| secrets.app | string | `""` | Existing secret with keys `app-key`, `jwt-secret`. Default <release>-app-secrets |
| secrets.create | bool | `true` | Generate chart-managed secrets with random values |
| secrets.ldap | string | `""` | Existing secret with key `password`. Required only when ldap.enabled=true |
| secrets.mail | string | `""` | Existing secret with key `password`. Required only when mail.host is set and SMTP needs auth |
| secrets.minio | string | `""` | Existing secret with keys `access-key`, `secret-key`. Default <release>-minio-secrets |
| secrets.pusher | string | `""` | Existing secret with key `app-secret`. Default <release>-pusher-secret |
| secrets.rabbitmq | string | `""` | Existing secret with keys `password`, `erlang-cookie`. Default <release>-rabbitmq-secret |
| securityContext | object | `{}` | Container-level securityContext |
| serviceAccount.create | bool | `false` | Create a dedicated ServiceAccount |
| serviceAccount.name | string | `""` | Existing ServiceAccount name when create=false |
| statistic.affinity | object | `{}` |  |
| statistic.image.repository | string | `"doqa/doqa-statistic"` | Statistic image repository |
| statistic.image.tag | string | `"2.0.1-box"` | Statistic image tag |
| statistic.nodeSelector | object | `{}` |  |
| statistic.replicas | int | `1` | Replica count |
| statistic.resources | object | `{}` | Container resources |
| statistic.tolerations | list | `[]` |  |
| telegramBot.affinity | object | `{}` |  |
| telegramBot.botName | string | `""` | Bot username (BOT_NAME) |
| telegramBot.enabled | bool | `false` | Enable telegram bot |
| telegramBot.image.repository | string | `"doqa/doqa-telegram-bot"` | Telegram bot image repository |
| telegramBot.image.tag | string | `"0.1.3-box"` | Telegram bot image tag |
| telegramBot.nodeSelector | object | `{}` |  |
| telegramBot.replicas | int | `1` | Replica count |
| telegramBot.resources | object | `{}` | Container resources |
| telegramBot.tokenSecret | string | `""` | Existing secret with key `token` for the Telegram bot token |
| telegramBot.tolerations | list | `[]` |  |
| useSsl | bool | `true` | Whether the public URL is HTTPS. Affects USE_SSL env and bucket URL protocol |
| websocket.affinity | object | `{}` |  |
| websocket.image.repository | string | `"service/soketi"` | Soketi image repository (defaults to vendor mirror, override to `quay.io/soketi/soketi`) |
| websocket.image.tag | string | `"16-alpine"` | Soketi image tag |
| websocket.nodeSelector | object | `{}` |  |
| websocket.replicas | int | `1` | Replica count |
| websocket.resources | object | `{}` | Container resources |
| websocket.tolerations | list | `[]` |  |

## Upgrading

This chart targets DoQA 4.0.0+. There is no automatic migration path from
3.x deployments — vendor changed the queue broker from Redis to RabbitMQ
between 3.7 and 4.0. Plan a stepwise migration if you are coming from a
3.x install.

## Maintainers

| Name | Email | Url |
| ---- | ------ | --- |
| batonogov |  | <https://github.com/batonogov> |

## Source Code

* <https://github.com/batonogov/helm-charts>
* <https://docs.doqa.app>
