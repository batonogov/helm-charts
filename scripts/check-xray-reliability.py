#!/usr/bin/env python3
"""xray-health-exporter regression checks: require Helm and PyYAML."""

from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parent.parent
CHART = ROOT / "charts/xray-health-exporter"
RELEASE_NAMESPACE = "exporter-system"


def render(values=None, kind="Deployment", release_namespace=RELEASE_NAMESPACE):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml") as extra:
        yaml.safe_dump(values or {}, extra)
        extra.flush()
        result = subprocess.run(
            ["helm", "template", "review", str(CHART), "-f",
             str(CHART / "ci/test-values.yaml"), "-f", extra.name,
             "--namespace", release_namespace, "--kube-version", "1.32.0",
             "--set", "fullnameOverride=review"],
            capture_output=True, text=True, check=True,
        )
    return {doc["metadata"]["name"]: doc
            for doc in yaml.safe_load_all(result.stdout)
            if doc and doc["kind"] == kind}


def monitoring_values(namespace="monitoring"):
    return {
        "metrics": {"serviceMonitor": {"enabled": True, "namespace": namespace}},
        "networkPolicy": {"enabled": True},
    }


class ReliabilityTests(unittest.TestCase):
    def test_cross_namespace_service_monitor_selects_release_namespace(self):
        monitor = render(monitoring_values(), kind="ServiceMonitor")["review"]
        self.assertEqual(monitor["metadata"]["namespace"], "monitoring")
        self.assertEqual(monitor["spec"]["namespaceSelector"], {"matchNames": [RELEASE_NAMESPACE]})

        same_namespace = render(monitoring_values(RELEASE_NAMESPACE), kind="ServiceMonitor")["review"]
        self.assertNotIn("namespaceSelector", same_namespace["spec"])

    def test_yaml_boolean_like_namespaces_remain_strings(self):
        monitor = render(monitoring_values("true"), kind="ServiceMonitor")["review"]
        self.assertEqual(monitor["metadata"]["namespace"], "true")
        self.assertIsInstance(monitor["metadata"]["namespace"], str)

        policy = render(monitoring_values("true"), kind="NetworkPolicy")["review"]
        namespace = policy["spec"]["ingress"][0]["from"][0]["namespaceSelector"]["matchLabels"][
            "kubernetes.io/metadata.name"]
        self.assertEqual(namespace, "true")
        self.assertIsInstance(namespace, str)

        monitor = render(monitoring_values(), kind="ServiceMonitor", release_namespace="true")["review"]
        release_namespace = monitor["spec"]["namespaceSelector"]["matchNames"][0]
        self.assertEqual(release_namespace, "true")
        self.assertIsInstance(release_namespace, str)

        same_namespace = render(monitoring_values("true"), kind="ServiceMonitor",
                                release_namespace="true")["review"]
        self.assertEqual(same_namespace["metadata"]["namespace"], "true")
        self.assertIsInstance(same_namespace["metadata"]["namespace"], str)
        self.assertNotIn("namespaceSelector", same_namespace["spec"])

    def test_default_network_policy_follows_service_monitor_namespace(self):
        policy = render(monitoring_values(), kind="NetworkPolicy")["review"]
        source = policy["spec"]["ingress"][0]["from"][0]
        self.assertEqual(source, {
            "namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "monitoring"}},
            "podSelector": {"matchLabels": {"app.kubernetes.io/name": "prometheus"}},
        })

        same_namespace = render(monitoring_values(RELEASE_NAMESPACE), kind="NetworkPolicy")["review"]
        source = same_namespace["spec"]["ingress"][0]["from"][0]
        self.assertEqual(source["namespaceSelector"]["matchLabels"],
                         {"kubernetes.io/metadata.name": RELEASE_NAMESPACE})

        without_monitor = render({"networkPolicy": {"enabled": True}}, kind="NetworkPolicy")["review"]
        source = without_monitor["spec"]["ingress"][0]["from"][0]
        self.assertNotIn("namespaceSelector", source)
        self.assertEqual(source["podSelector"]["matchLabels"], {"app.kubernetes.io/name": "prometheus"})

    def test_explicit_network_policy_ingress_replaces_default(self):
        values = monitoring_values()
        values["networkPolicy"]["ingress"] = [{"from": [{"ipBlock": {"cidr": "10.0.0.0/8"}}]}]
        policy = render(values, kind="NetworkPolicy")["review"]
        self.assertEqual(policy["spec"]["ingress"], values["networkPolicy"]["ingress"])

    def test_pdb_distinguishes_zero_from_unset(self):
        zero = render({"podDisruptionBudget": {"enabled": True, "maxUnavailable": 0}},
                      kind="PodDisruptionBudget")["review"]
        self.assertEqual(zero["spec"]["maxUnavailable"], 0)
        self.assertNotIn("minAvailable", zero["spec"])

        unset = render({"podDisruptionBudget": {"enabled": True}},
                       kind="PodDisruptionBudget")["review"]
        self.assertEqual(unset["spec"]["minAvailable"], 1)
        self.assertNotIn("maxUnavailable", unset["spec"])

    def test_service_types_match_template_support(self):
        for service_type in ("ClusterIP", "NodePort", "LoadBalancer"):
            with self.subTest(service_type=service_type):
                service = render({"service": {"type": service_type}}, kind="Service")["review"]
                self.assertEqual(service["spec"]["type"], service_type)

        with self.assertRaises(subprocess.CalledProcessError) as failure:
            render({"service": {"type": "ExternalName"}}, kind="Service")
        self.assertIn("/service/type", failure.exception.stderr)
        self.assertNotIn("ExternalName", failure.exception.stderr)


if __name__ == "__main__":
    unittest.main()
