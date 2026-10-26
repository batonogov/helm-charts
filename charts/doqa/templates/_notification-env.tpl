{{/*
Shared env block for notification API, worker, and telegram-bot — matches the YAML anchor in vendor's compose.
*/}}
{{- define "doqa.notificationEnv" -}}
- name: BOT_NAME
  value: {{ .Values.telegramBot.botName | quote }}
{{- if .Values.telegramBot.tokenSecret }}
- name: BOT_TOKEN
  valueFrom:
    secretKeyRef:
      name: {{ .Values.telegramBot.tokenSecret }}
      key: token
{{- end }}
- name: PUSHER_PORT
  value: {{ .Values.pusher.port | int | quote }}
- name: PUSHER_APP_HOST
  value: {{ include "doqa.resourceName" (dict "ctx" . "suffix" "websocket") | quote }}
- name: PUSHER_APP_ID
  value: {{ .Values.pusher.appId | quote }}
- name: PUSHER_APP_KEY
  value: {{ .Values.pusher.appKey | quote }}
- name: PUSHER_APP_SECRET
  valueFrom:
    secretKeyRef:
      name: {{ include "doqa.secret.pusher" . }}
      key: app-secret
- name: PUSHER_SSL
  value: {{ eq .Values.pusher.scheme "https" | quote }}
- name: MAIL_HOST
  value: {{ .Values.mail.host | quote }}
- name: MAIL_PORT
  value: {{ .Values.mail.port | quote }}
- name: MAIL_USERNAME
  value: {{ .Values.mail.username | quote }}
{{- if .Values.secrets.mail }}
- name: MAIL_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ .Values.secrets.mail }}
      key: password
{{- end }}
- name: DB_CONNECTION
  value: pgsql
- name: DB_HOST
  value: {{ include "doqa.postgresql.host" . | quote }}
- name: DB_PORT
  value: {{ .Values.postgresql.port | quote }}
- name: DB_DATABASE
  value: {{ .Values.postgresql.database | quote }}
- name: DB_USERNAME
  value: {{ .Values.postgresql.username | quote }}
- name: DB_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ include "doqa.postgresql.passwordSecretName" . }}
      key: {{ include "doqa.postgresql.passwordSecretKey" . }}
- name: REDIS_HOST
  value: {{ include "doqa.redis.notification.host" . | quote }}
- name: REDIS_PORT
  value: {{ .Values.redis.notification.port | quote }}
- name: REDIS_DB
  value: {{ .Values.redis.notification.db | quote }}
{{- if .Values.redis.notification.passwordSecret.name }}
- name: REDIS_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ .Values.redis.notification.passwordSecret.name }}
      key: {{ .Values.redis.notification.passwordSecret.key }}
{{- else if and (not .Values.redis.notification.host) .Values.redis.passwordSecret.name }}
- name: REDIS_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ .Values.redis.passwordSecret.name }}
      key: {{ .Values.redis.passwordSecret.key }}
{{- else }}
- name: REDIS_PASSWORD
  value: ""
{{- end }}
- name: DEBUG
  value: {{ .Values.debug | quote }}
- name: API_KEY
  valueFrom:
    secretKeyRef:
      name: {{ include "doqa.secret.apiKeys" . }}
      key: notification-api-key
- name: STUB_AUTH
  value: "False"
- name: PREFIX_ROOT_PATH
  value: "/"
- name: APP_TITLE
  value: {{ printf "%s - Notification" .Values.product.name | quote }}
- name: PRODUCT_NAME
  value: {{ .Values.product.name | quote }}
- name: PRODUCT_FROM_DISPLAY
  value: {{ .Values.product.fromDisplay | quote }}
- name: PRODUCT_SUPPORT_EMAIL
  value: {{ .Values.product.supportEmail | quote }}
- name: PRODUCT_DOCS_URL
  value: {{ .Values.product.docsUrl | quote }}
- name: PRODUCT_SITE_URL
  value: {{ .Values.product.siteUrl | quote }}
- name: PRODUCT_TELEGRAM_URL
  value: {{ .Values.product.telegramUrl | quote }}
- name: PRODUCT_SUPPORT_TELEGRAM_URL
  value: {{ .Values.product.supportTelegramUrl | quote }}
- name: PRODUCT_VK_URL
  value: {{ .Values.product.vkUrl | quote }}
- name: PRODUCT_YOUTUBE_URL
  value: {{ .Values.product.youtubeUrl | quote }}
- name: IS_BOX
  value: "true"
{{- end }}
