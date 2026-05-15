# xray-health-exporter

Prometheus exporter for Xray-core tunnel health

![Version: 0.1.6](https://img.shields.io/badge/Version-0.1.6-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square) ![AppVersion: 1.2.3](https://img.shields.io/badge/AppVersion-1.2.3-informational?style=flat-square)

**Homepage:** <https://github.com/batonogov/xray-health-exporter>

## TL;DR

```bash
helm repo add batonogov https://batonogov.github.io/helm-charts
helm install xray batonogov/xray-health-exporter -n monitoring --create-namespace \
  --set-file config.tunnels=tunnels.yaml
```

## Prerequisites

- Kubernetes 1.32+
- Helm 3.14+
- For `ServiceMonitor`/`PrometheusRule`: the
  [Prometheus Operator](https://github.com/prometheus-operator/prometheus-operator)
  CRDs installed in the cluster
- For `replicaCount > 1`: leader election (default) requires a Role granting
  access to `coordination.k8s.io/leases` — created automatically by the chart

## High availability

The chart force-enables Kubernetes leader election whenever `replicaCount > 1`,
regardless of `leaderElection.enabled`. Only the leader publishes
`xray_tunnel_*` series; followers continue to serve `/health` and a single
`xray_exporter_leader=0` metric so a Service can still load-balance and the
Prometheus Operator can keep scraping every pod without duplicated tunnel
metrics.

Failover timing matches the upstream defaults: ~5s on graceful leader exit,
~30s on hard pod loss.

## Configuration

The exporter is driven by a YAML file. Set `.Values.config` to render a
ConfigMap, or point `existingConfigSecret` at a Secret you manage out of
band (recommended when subscription URLs contain tokens).

```yaml
config:
  defaults:
    check_url: https://www.google.com
    check_interval: 30s
    check_timeout: 30s
  subscriptions:
    - url: https://provider.example.com/subscribe?token=xxx
      update_interval: 1h
  tunnels:
    - name: edge-1
      url: "vless://uuid@host1:443?type=tcp&security=reality&pbk=...&sni=google.com"
```

See [upstream docs](https://github.com/batonogov/xray-health-exporter#конфигурация)
for the full schema.

## Prometheus integration

Set `metrics.serviceMonitor.enabled=true` to register the exporter with the
Prometheus Operator. Set `metrics.prometheusRule.enabled=true` to ship the
default tunnel alerts (`XrayTunnelDown`, `XrayHighLatency`,
`XrayNoRecentCheck`); override `metrics.prometheusRule.rules` to provide your
own list.

## Requirements

Kubernetes: `>=1.32.0-0`

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| affinity | object | `{}` | Affinity rules for the pod. |
| config.defaults | object | `{"check_interval":"30s","check_timeout":"30s","check_url":"https://www.google.com"}` | Global tunnel-check defaults applied when an entry omits the field. |
| config.subscriptions | list | `[]` | Subscription URLs that auto-discover tunnels. See upstream README for schema. WARNING: subscription URLs typically embed access tokens — they are rendered into a plain ConfigMap. Use `existingConfigSecret` to source `config.yaml` from a Secret instead. |
| config.tunnels | list | `[]` | Static tunnels. Each entry needs either `url` (VLESS) or `xray_config_file`. At least one tunnel or one subscription is required (or set `existingConfigSecret`); otherwise the exporter refuses to start. |
| env.DEBUG | string | `"false"` | Verbose exporter logging. |
| env.XRAY_LOG_LEVEL | string | `"warning"` | Xray-core log level (`debug`/`info`/`warning`/`error`). |
| existingConfigSecret | string | `""` | Mount an existing Secret containing `config.yaml` instead of rendering one from `.Values.config`. |
| extraEnv | list | `[]` | Extra environment variables (list of `{name, value}` or `{name, valueFrom}`). |
| fullnameOverride | string | `""` | Fully override the generated release name. |
| image.pullPolicy | string | `"IfNotPresent"` | Image pull policy. |
| image.pullSecrets | list | `[]` | Image pull secrets (list of `{name: <secret>}`). |
| image.repository | string | `"ghcr.io/batonogov/xray-health-exporter"` | Image repository. |
| image.tag | string | `""` | Image tag. Defaults to `v<chart appVersion>` when empty (upstream publishes v-prefixed tags to ghcr.io). |
| leaderElection.enabled | bool | `true` | Enable Kubernetes leader election so only one replica publishes `xray_tunnel_*`. Forced on whenever `replicaCount > 1`, regardless of this flag. |
| leaderElection.leaseName | string | `""` | Lease object name. Defaults to the release fullname. |
| leaderElection.rbac.create | bool | `true` | Create the Role + RoleBinding granting access to `coordination.k8s.io/leases`. |
| metrics.prometheusRule.annotations | object | `{}` | Extra annotations. |
| metrics.prometheusRule.enabled | bool | `false` | Create a Prometheus Operator `PrometheusRule` with default tunnel alerts. |
| metrics.prometheusRule.labels | object | `{}` | Extra labels on the PrometheusRule (e.g. `release: kube-prometheus-stack`). |
| metrics.prometheusRule.rules | list | `[]` | Override the default rule list. When empty the chart ships sensible defaults (`XrayTunnelDown`, `XrayHighLatency`, `XrayNoRecentCheck`). |
| metrics.serviceMonitor.annotations | object | `{}` | Extra annotations on the ServiceMonitor. |
| metrics.serviceMonitor.enabled | bool | `false` | Create a Prometheus Operator `ServiceMonitor` for the exporter. |
| metrics.serviceMonitor.interval | string | `"30s"` | Scrape interval. |
| metrics.serviceMonitor.labels | object | `{}` | Extra labels (e.g. `release: kube-prometheus-stack`). |
| metrics.serviceMonitor.metricRelabelings | list | `[]` | Optional metric relabelings. |
| metrics.serviceMonitor.relabelings | list | `[]` | Optional relabelings. |
| metrics.serviceMonitor.scrapeTimeout | string | `"10s"` | Scrape timeout. |
| nameOverride | string | `""` | Override the chart name (used in resource naming). |
| networkPolicy.egress | list | `[]` | Extra egress rules. When unset, allows all egress. |
| networkPolicy.enabled | bool | `false` | Create a NetworkPolicy. By default allows all egress and Prometheus-style ingress to the metrics port. |
| networkPolicy.ingress | list | `[]` | Extra ingress rules. When unset, the chart allows ingress from any pod with label `app.kubernetes.io/name: prometheus`. |
| nodeSelector | object | `{}` | nodeSelector for the pod. |
| podAnnotations | object | `{}` | Annotations applied to every Deployment pod. |
| podDisruptionBudget.enabled | bool | `false` | Create a PodDisruptionBudget. |
| podDisruptionBudget.maxUnavailable | string | `nil` | Maximum number of pods that can be unavailable during disruptions. Takes precedence over `minAvailable` when set. |
| podDisruptionBudget.minAvailable | int | `1` | Minimum number of pods that must be available during disruptions. |
| podLabels | object | `{}` | Extra labels applied to every Deployment pod. |
| podSecurityContext | object | `{"fsGroup":10001,"runAsGroup":10001,"runAsNonRoot":true,"runAsUser":10001}` | Pod-level security context (non-root, matches upstream UID 10001). |
| replicaCount | int | `2` | Number of replicas. Values >1 force-enable `leaderElection.enabled` so only one pod publishes tunnel metrics. |
| resources | object | `{}` | Container resource requests/limits. |
| securityContext | object | `{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"readOnlyRootFilesystem":true}` | Container-level security context (read-only rootfs, no privilege escalation). |
| service.annotations | object | `{}` | Annotations applied to the Service. |
| service.port | int | `9273` | Service port. |
| service.type | string | `"ClusterIP"` | Service type. |
| serviceAccount.annotations | object | `{}` | Annotations applied to the ServiceAccount. |
| serviceAccount.create | bool | `true` | Create a dedicated ServiceAccount for the Deployment. |
| serviceAccount.name | string | `""` | ServiceAccount name. Defaults to release fullname when empty. |
| tolerations | list | `[]` | Tolerations for the pod. |
| topologySpreadConstraints | list | `[]` | topologySpreadConstraints for the pod. |

## Maintainers

| Name | Email | Url |
| ---- | ------ | --- |
| batonogov |  | <https://github.com/batonogov> |

## Source Code

* <https://github.com/batonogov/helm-charts>
* <https://github.com/batonogov/xray-health-exporter>
