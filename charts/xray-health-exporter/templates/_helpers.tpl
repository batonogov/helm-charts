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

{{- define "xray-health-exporter.imageTag" -}}
{{- default .Chart.AppVersion .Values.image.tag }}
{{- end }}
