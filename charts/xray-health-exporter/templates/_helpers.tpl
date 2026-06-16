{{/*
Chart name (truncated to 63 chars).
*/}}
{{- define "xray-health-exporter.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Fully qualified app name.
*/}}
{{- define "xray-health-exporter.fullname" -}}
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

{{- define "xray-health-exporter.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "xray-health-exporter.labels" -}}
helm.sh/chart: {{ include "xray-health-exporter.chart" . }}
{{ include "xray-health-exporter.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "xray-health-exporter.selectorLabels" -}}
app.kubernetes.io/name: {{ include "xray-health-exporter.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "xray-health-exporter.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "xray-health-exporter.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{- define "xray-health-exporter.leaseName" -}}
{{- default (include "xray-health-exporter.fullname" .) .Values.leaderElection.leaseName }}
{{- end }}

{{/*
Leader election is forced on whenever replicaCount > 1, so multi-replica
deployments cannot accidentally publish duplicate xray_tunnel_* metrics.
Returns "true" or "" so callers can use `eq ... "true"`.
*/}}
{{- define "xray-health-exporter.leaderElectionEnabled" -}}
{{- if or .Values.leaderElection.enabled (gt (int .Values.replicaCount) 1) -}}
true
{{- end -}}
{{- end }}

{{/*
Image tag. Upstream publishes v-prefixed tags (`v1.2.0`) to ghcr.io while
Chart.yaml `appVersion` follows Helm convention (no prefix), so the fallback
prepends `v` to keep `helm install` working out of the box.
*/}}
{{- define "xray-health-exporter.imageTag" -}}
{{- default (printf "v%s" .Chart.AppVersion) .Values.image.tag }}
{{- end }}

{{/*
Name of the Secret holding the Basic Auth password.
Precedence: existingSecret > secretName > generated `<fullname>-basicauth`.
Sprig `default` only inspects the first non-empty "given" arg, so the
override must be nested rather than listed positionally.
*/}}
{{- define "xray-health-exporter.basicAuthSecretName" -}}
{{- default (default (printf "%s-basicauth" (include "xray-health-exporter.fullname" .)) .Values.metricsBasicAuth.secretName) .Values.metricsBasicAuth.existingSecret }}
{{- end }}

{{/*
Whether the chart should provision a Secret itself for Basic Auth.
True only when Basic Auth is enabled and the user did not point at an existing Secret.
*/}}
{{- define "xray-health-exporter.basicAuthSecretCreate" -}}
{{- if and .Values.metricsBasicAuth.enabled (not .Values.metricsBasicAuth.existingSecret) -}}
true
{{- end -}}
{{- end }}

{{/*
Effective Basic Auth username. Upstream defaults to `metricsUser` when
`METRICS_USERNAME` is empty; the chart materializes that default so the
username is concrete in the generated Secret and ServiceMonitor.
*/}}
{{- define "xray-health-exporter.basicAuthUsername" -}}
{{- .Values.metricsBasicAuth.username | default "metricsUser" }}
{{- end }}

{{/* Key in the Basic Auth Secret holding the username (default `username`). */}}
{{- define "xray-health-exporter.basicAuthUsernameKey" -}}
{{- .Values.metricsBasicAuth.usernameKey | default "username" }}
{{- end }}

{{/* Key in the Basic Auth Secret holding the password (default `password`). */}}
{{- define "xray-health-exporter.basicAuthPasswordKey" -}}
{{- .Values.metricsBasicAuth.passwordKey | default "password" }}
{{- end }}

{{/*
Fail fast when Basic Auth + ServiceMonitor are enabled but the chart-generated
Secret lives in a namespace the ServiceMonitor cannot read. The Prometheus
Operator requires the referenced Secret in the same namespace as the
ServiceMonitor; the chart creates the Secret in the release namespace. When the
ServiceMonitor targets a different namespace, the user must supply a Secret
there via `metricsBasicAuth.existingSecret`.
*/}}
{{- define "xray-health-exporter.validateBasicAuthServiceMonitor" -}}
{{- $smNs := .Values.metrics.serviceMonitor.namespace | default .Release.Namespace -}}
{{- if and .Values.metricsBasicAuth.enabled .Values.metrics.serviceMonitor.enabled (ne $smNs .Release.Namespace) (not .Values.metricsBasicAuth.existingSecret) -}}
{{- fail (printf "xray-health-exporter: metricsBasicAuth is enabled and the ServiceMonitor targets namespace %q, but the chart-generated Basic Auth Secret lives in the release namespace %q and Prometheus Operator only reads Secrets from the ServiceMonitor's namespace. Set metricsBasicAuth.existingSecret to a Secret in namespace %q (containing both the username and password keys), or move the ServiceMonitor back to the release namespace via metrics.serviceMonitor.namespace." $smNs .Release.Namespace $smNs) -}}
{{- end -}}
{{- end }}

{{/*
Fail fast when the chart cannot produce a working config: no static tunnels,
no subscriptions, and no externally-managed Secret.
*/}}
{{- define "xray-health-exporter.validateConfig" -}}
{{- if and (not .Values.existingConfigSecret) (empty .Values.config.tunnels) (empty .Values.config.subscriptions) -}}
{{- fail "xray-health-exporter: provide at least one entry in .Values.config.tunnels or .Values.config.subscriptions, or set .Values.existingConfigSecret. The exporter refuses to start otherwise." -}}
{{- end -}}
{{- end }}
