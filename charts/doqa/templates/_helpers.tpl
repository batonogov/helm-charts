{{/*
Chart name (truncated to 63 chars).
*/}}
{{- define "doqa.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Fully qualified app name.
*/}}
{{- define "doqa.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Resource name with a reserved suffix. The fullname is shortened only as much
as needed, keeping ordinary names unchanged and the complete name within 63
characters. A truncated prefix carries a hash of the complete fullname to avoid
collisions. Suffix is passed without the leading hyphen.
*/}}
{{- define "doqa.resourceName" -}}
{{- $suffix := .suffix -}}
{{- $fullname := include "doqa.fullname" .ctx -}}
{{- if $suffix -}}
{{- $prefixLength := sub 63 (add1 (len $suffix)) | int -}}
{{- $prefix := $fullname -}}
{{- if gt (len $fullname) $prefixLength -}}
{{- $hash := sha256sum $fullname | trunc 8 -}}
{{- $prefixLength = sub $prefixLength 9 | int -}}
{{- $prefix = printf "%s-%s" ($fullname | trunc $prefixLength | trimSuffix "-") $hash -}}
{{- end -}}
{{- printf "%s-%s" $prefix $suffix -}}
{{- else -}}
{{- $fullname -}}
{{- end -}}
{{- end }}

{{/*
Render an explicit Secret only when it is already managed by this release.
This retains 0.10.0-generated Secrets after their names become explicit values;
genuinely pre-existing Secrets and offline lookups remain unrendered.
*/}}
{{- define "doqa.shouldRenderSecret" -}}
{{- if not .explicit -}}
true
{{- else -}}
{{- $existing := lookup "v1" "Secret" .ctx.Release.Namespace .name -}}
{{- if $existing -}}
{{- $annotations := $existing.metadata.annotations | default dict -}}
{{- if and (eq (get $annotations "meta.helm.sh/release-name" | default "") .ctx.Release.Name) (eq (get $annotations "meta.helm.sh/release-namespace" | default "") .ctx.Release.Namespace) -}}
true
{{- end -}}
{{- end -}}
{{- end -}}
{{- end }}

{{- define "doqa.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "doqa.labels" -}}
helm.sh/chart: {{ include "doqa.chart" . }}
{{ include "doqa.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- with .Values.extraLabels }}
{{ toYaml . }}
{{- end }}
{{- end }}

{{- define "doqa.selectorLabels" -}}
app.kubernetes.io/name: {{ include "doqa.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "doqa.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "doqa.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Image reference helper. Relative repositories use the global image registry,
while fully qualified repositories (registry host contains "." or ":", or is
localhost) are rendered unchanged.
Usage: {{ include "doqa.image" (dict "img" .Values.backend.image "root" .) }}
*/}}
{{- define "doqa.image" -}}
{{- $reg := .root.Values.image.registry -}}
{{- $repo := .img.repository -}}
{{- $qualified := or (hasPrefix "localhost/" $repo) (regexMatch "^[^/]+[.:][^/]*/" $repo) -}}
{{- if and $reg (not $qualified) -}}{{ $reg }}/{{- end -}}
{{ $repo }}:{{ .img.tag }}
{{- end }}

{{/* User-provided Pod labels, excluding labels reserved by chart selectors. */}}
{{- define "doqa.podLabels" -}}
{{- $filtered := dict -}}
{{- range $k, $v := . -}}
{{- if and (ne $k "app.kubernetes.io/name") (ne $k "app.kubernetes.io/instance") (ne $k "app.kubernetes.io/component") -}}
{{- $_ := set $filtered $k $v -}}
{{- end -}}
{{- end -}}
{{- with $filtered -}}{{- toYaml . -}}{{- end -}}
{{- end -}}

{{- define "doqa.imagePullSecrets" -}}
{{- with .Values.image.pullSecrets }}
imagePullSecrets:
{{- toYaml . | nindent 2 }}
{{- end }}
{{- end }}

{{- define "doqa.frontendUrl" -}}
{{- default .Values.appUrl .Values.appFrontendUrl }}
{{- end }}

{{- define "doqa.bucketUrl" -}}
{{- if .Values.minio.bucketUrl }}
{{- .Values.minio.bucketUrl }}
{{- else }}
{{- $scheme := ternary "https" "http" .Values.useSsl }}
{{- printf "%s://%s/%s" $scheme .Values.appUrl .Values.minio.bucket }}
{{- end }}
{{- end }}

{{/*
Pod-level securityContext. Merges defaultSecurityContext.pod with component-specific overrides.
Usage: {{ include "doqa.podSecurityContext" (dict "component" .Values.backend "root" .) }}
*/}}
{{- define "doqa.podSecurityContext" -}}
{{- $defaults := .root.Values.defaultSecurityContext.pod | default dict -}}
{{- $overrides := .component.podSecurityContext | default dict -}}
{{- $pod := merge $overrides $defaults -}}
{{- with $pod }}
securityContext:
{{- toYaml . | nindent 2 }}
{{- end }}
{{- end }}

{{/*
Container-level securityContext. Merges defaultSecurityContext.container with component-specific overrides.
Usage: {{ include "doqa.containerSecurityContext" (dict "component" .Values.backend "root" .) }}
*/}}
{{- define "doqa.containerSecurityContext" -}}
{{- $defaults := .root.Values.defaultSecurityContext.container | default dict -}}
{{- $overrides := .component.containerSecurityContext | default dict -}}
{{- $container := merge $overrides $defaults -}}
{{- with $container }}
securityContext:
{{- toYaml . | nindent 2 }}
{{- end }}
{{- end }}

{{/* ===== Host resolution helpers ===== */}}

{{/* Reserve space for CNPG's generated -app Secret and -rw Service. */}}
{{- define "doqa.postgresql.clusterName" -}}
{{- include "doqa.resourceName" (dict "ctx" . "suffix" "cnpg-app") | trimSuffix "-app" -}}
{{- end -}}

{{/*
PostgreSQL host. CNPG creates a `<cluster>-rw` Service.
*/}}
{{- define "doqa.postgresql.host" -}}
{{- if .Values.postgresql.cnpg.create -}}
{{- printf "%s-rw" (include "doqa.postgresql.clusterName" .) -}}
{{- else -}}
{{- required "postgresql.host is required when postgresql.cnpg.create=false" .Values.postgresql.host -}}
{{- end -}}
{{- end -}}

{{/*
PostgreSQL password secret name + key.
CNPG auto-creates `<cluster>-app` secret with username/password.
*/}}
{{- define "doqa.postgresql.passwordSecretName" -}}
{{- if .Values.postgresql.cnpg.create -}}
{{- printf "%s-app" (include "doqa.postgresql.clusterName" .) -}}
{{- else -}}
{{- required "postgresql.passwordSecret.name is required when postgresql.cnpg.create=false" .Values.postgresql.passwordSecret.name -}}
{{- end -}}
{{- end -}}

{{- define "doqa.postgresql.passwordSecretKey" -}}
{{- if .Values.postgresql.cnpg.create -}}
password
{{- else -}}
{{- default "password" .Values.postgresql.passwordSecret.key -}}
{{- end -}}
{{- end -}}

{{/*
Redis host (in-tree Service vs external).
*/}}
{{- define "doqa.redis.host" -}}
{{- if .Values.redis.create -}}
{{- include "doqa.resourceName" (dict "ctx" . "suffix" "redis") -}}
{{- else -}}
{{- required "redis.host is required when redis.create=false" .Values.redis.host -}}
{{- end -}}
{{- end -}}

{{/*
Notification Redis host. Falls back to primary redis when not separately configured.
For in-tree mode reuses the same Redis instance with different logical DB key prefix.
*/}}
{{- define "doqa.redis.notification.host" -}}
{{- if .Values.redis.create -}}
{{- include "doqa.resourceName" (dict "ctx" . "suffix" "redis") -}}
{{- else -}}
{{- default .Values.redis.host .Values.redis.notification.host -}}
{{- end -}}
{{- end -}}

{{/*
RabbitMQ host (in-tree Service vs external).
*/}}
{{- define "doqa.rabbitmq.host" -}}
{{- if .Values.rabbitmq.create -}}
{{- include "doqa.resourceName" (dict "ctx" . "suffix" "rabbitmq") -}}
{{- else -}}
{{- required "rabbitmq.host is required when rabbitmq.create=false" .Values.rabbitmq.host -}}
{{- end -}}
{{- end -}}

{{/*
MinIO endpoint (URL with scheme). In-tree MinIO uses cluster-local Service:9000.
*/}}
{{- define "doqa.minio.endpoint" -}}
{{- if .Values.minio.create -}}
{{- printf "http://%s:9000" (include "doqa.resourceName" (dict "ctx" . "suffix" "minio")) -}}
{{- else -}}
{{- required "minio.endpoint is required when minio.create=false" .Values.minio.endpoint -}}
{{- end -}}
{{- end -}}

{{/* ===== Secret name helpers =====
Resolution rules per secret:
  - if `secrets.<name>` is set, use it (external).
  - else if chart generates this secret (`secrets.create=true` AND, for infra
    secrets, the corresponding `<infra>.create=true`), default to `<release>-<name>`.
  - otherwise fail with `required` so the user gets a clear error instead of a
    pod CrashLoop on a missing Secret reference.
*/}}

{{- define "doqa.secret.app" -}}
{{- if .Values.secrets.app -}}
{{- .Values.secrets.app -}}
{{- else if not .Values.secrets.create -}}
{{- required "secrets.app must be set when secrets.create=false (existing Secret with keys app-key, jwt-secret, internal-system-key)" "" -}}
{{- else -}}
{{- include "doqa.resourceName" (dict "ctx" . "suffix" "app-secrets") -}}
{{- end -}}
{{- end -}}

{{- define "doqa.secret.apiKeys" -}}
{{- if .Values.secrets.apiKeys -}}
{{- .Values.secrets.apiKeys -}}
{{- else if not .Values.secrets.create -}}
{{- required "secrets.apiKeys must be set when secrets.create=false (existing Secret with keys statistic-api-key, notification-api-key, llm-api-key)" "" -}}
{{- else -}}
{{- include "doqa.resourceName" (dict "ctx" . "suffix" "api-keys") -}}
{{- end -}}
{{- end -}}

{{- define "doqa.secret.pusher" -}}
{{- if .Values.secrets.pusher -}}
{{- .Values.secrets.pusher -}}
{{- else if not .Values.secrets.create -}}
{{- required "secrets.pusher must be set when secrets.create=false (existing Secret with key app-secret)" "" -}}
{{- else -}}
{{- include "doqa.resourceName" (dict "ctx" . "suffix" "pusher-secret") -}}
{{- end -}}
{{- end -}}

{{/*
RabbitMQ secret. Chart generates it only when `rabbitmq.create=true` AND
`secrets.create=true` — for an external broker the chart cannot know its
password, so the user must provide the secret name.
*/}}
{{- define "doqa.secret.rabbitmq" -}}
{{- if .Values.secrets.rabbitmq -}}
{{- .Values.secrets.rabbitmq -}}
{{- else if or (not .Values.secrets.create) (not .Values.rabbitmq.create) -}}
{{- required "secrets.rabbitmq must be set when rabbitmq.create=false or secrets.create=false (existing Secret with keys password, erlang-cookie)" "" -}}
{{- else -}}
{{- include "doqa.resourceName" (dict "ctx" . "suffix" "rabbitmq-secret") -}}
{{- end -}}
{{- end -}}

{{/*
MinIO secret. Same logic as RabbitMQ: chart cannot generate creds for an
external object store.
*/}}
{{- define "doqa.secret.minio" -}}
{{- if .Values.secrets.minio -}}
{{- .Values.secrets.minio -}}
{{- else if or (not .Values.secrets.create) (not .Values.minio.create) -}}
{{- required "secrets.minio must be set when minio.create=false or secrets.create=false (existing Secret with keys access-key, secret-key)" "" -}}
{{- else -}}
{{- include "doqa.resourceName" (dict "ctx" . "suffix" "minio-secrets") -}}
{{- end -}}
{{- end -}}

{{/*
Mail secret — chart never auto-generates this. Returns "" if not set.
*/}}
{{- define "doqa.secret.mail" -}}
{{- .Values.secrets.mail | default "" -}}
{{- end -}}

{{/* Existing APP_KEY values, including legacy 24-byte keys, are never rotated. */}}
{{- define "doqa.stableAppKey" -}}
{{- $existing := lookup "v1" "Secret" .ctx.Release.Namespace .name -}}
{{- if and $existing (index $existing.data "app-key") -}}
{{- index $existing.data "app-key" | b64dec -}}
{{- else -}}
{{- printf "base64:%s" (randBytes 32) -}}
{{- end -}}
{{- end -}}

{{/* ===== Stable random secret value (lookup-aware) =====
Reads an existing key from an already-deployed Secret, otherwise generates randAlphaNum of the requested length.
*/}}
{{- define "doqa.stableSecret" -}}
{{- $existing := lookup "v1" "Secret" .ctx.Release.Namespace .name -}}
{{- if and $existing (index $existing.data .key) -}}
{{- index $existing.data .key | b64dec -}}
{{- else -}}
{{- randAlphaNum (.len | int) -}}
{{- end -}}
{{- end -}}

{{/* ===== ConfigMap envFrom for backend/queue/cron ===== */}}
{{- define "doqa.backendEnvFrom" -}}
- configMapRef:
    name: {{ include "doqa.resourceName" (dict "ctx" . "suffix" "env") }}
{{- end }}

{{/*
Per-pod env entries that read from secrets (DB password, app keys, mail/minio/api keys, ldap, redis, rabbitmq, bot token).
*/}}
{{- define "doqa.backendSecretEnv" -}}
- name: APP_KEY
  valueFrom:
    secretKeyRef:
      name: {{ include "doqa.secret.app" . }}
      key: app-key
- name: JWT_SECRET
  valueFrom:
    secretKeyRef:
      name: {{ include "doqa.secret.app" . }}
      key: jwt-secret
- name: INTERNAL_SYSTEM_KEY
  valueFrom:
    secretKeyRef:
      name: {{ include "doqa.secret.app" . }}
      key: internal-system-key
- name: DB_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ include "doqa.postgresql.passwordSecretName" . }}
      key: {{ include "doqa.postgresql.passwordSecretKey" . }}
{{- if .Values.redis.passwordSecret.name }}
- name: REDIS_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ .Values.redis.passwordSecret.name }}
      key: {{ .Values.redis.passwordSecret.key }}
{{- end }}
- name: MINIO_KEY
  valueFrom:
    secretKeyRef:
      name: {{ include "doqa.secret.minio" . }}
      key: access-key
- name: MINIO_SECRET
  valueFrom:
    secretKeyRef:
      name: {{ include "doqa.secret.minio" . }}
      key: secret-key
{{- if .Values.secrets.mail }}
- name: MAIL_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ .Values.secrets.mail }}
      key: password
{{- end }}
- name: STATISTIC_API_KEY
  valueFrom:
    secretKeyRef:
      name: {{ include "doqa.secret.apiKeys" . }}
      key: statistic-api-key
- name: NOTIFICATION_API_KEY
  valueFrom:
    secretKeyRef:
      name: {{ include "doqa.secret.apiKeys" . }}
      key: notification-api-key
- name: LLM_API_KEY
  valueFrom:
    secretKeyRef:
      name: {{ include "doqa.secret.apiKeys" . }}
      key: llm-api-key
- name: PUSHER_APP_SECRET
  valueFrom:
    secretKeyRef:
      name: {{ include "doqa.secret.pusher" . }}
      key: app-secret
- name: RABBITMQ_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ include "doqa.secret.rabbitmq" . }}
      key: password
- name: RABBITMQ_ERLANG_COOKIE
  valueFrom:
    secretKeyRef:
      name: {{ include "doqa.secret.rabbitmq" . }}
      key: erlang-cookie
{{- if and .Values.ldap.enabled .Values.secrets.ldap }}
- name: LDAP_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ .Values.secrets.ldap }}
      key: password
{{- end }}
{{- if .Values.telegramBot.tokenSecret }}
- name: BOT_TOKEN
  valueFrom:
    secretKeyRef:
      name: {{ .Values.telegramBot.tokenSecret }}
      key: token
{{- end }}
{{- end }}

{{/* ===== extraAnnotations helper =====
   Renders user-provided `extraAnnotations` while dropping any key whose name
   starts with the reserved `checksum/` prefix. Those keys are chart-managed
   (e.g. `checksum/env`, `checksum/config`) and must not collide with
   user-supplied values. Returns an empty string when nothing remains so the
   existing `with` guards at the call sites behave unchanged. */}}
{{- define "doqa.extraAnnotations" -}}
{{- $filtered := dict -}}
{{- range $k, $v := . -}}
{{- if not (hasPrefix "checksum/" $k) -}}
{{- $_ := set $filtered $k $v -}}
{{- end -}}
{{- end -}}
{{- with $filtered -}}{{- toYaml . -}}{{- end -}}
{{- end -}}

{{/* ===== Service spec helper ===== */}}
{{- define "doqa.componentService" -}}
type: ClusterIP
ports:
- port: {{ .port }}
  targetPort: {{ .targetPort | default .port }}
  protocol: TCP
  name: {{ .name }}
selector:
  {{- include "doqa.selectorLabels" .ctx | nindent 2 }}
  app.kubernetes.io/component: {{ .component }}
{{- end }}
