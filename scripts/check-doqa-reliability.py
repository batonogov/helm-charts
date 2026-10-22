#!/usr/bin/env python3
"""Регрессии DoQA: нужны Helm и PyYAML (также используется chart-testing)."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parent.parent
CHART = ROOT / "charts/doqa"


def render(values=None, kind="Deployment"):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml") as extra:
        yaml.safe_dump(values or {}, extra)
        extra.flush()
        result = subprocess.run(
            ["helm", "template", "review", str(CHART), "-f",
             str(CHART / "ci/test-values.yaml"), "-f", extra.name, "--set", "fullnameOverride=review"],
            capture_output=True, text=True, check=True,
        )
    return {doc["metadata"]["name"]: doc
            for doc in yaml.safe_load_all(result.stdout)
            if doc and doc["kind"] == kind}


def pod(doc):
    return doc["spec"]["template"]["spec"]


class ReliabilityTests(unittest.TestCase):
    def test_init_and_mounts(self):
        for enabled in (False, True):
            for skip in (False, True):
                with self.subTest(enabled=enabled, skip=skip):
                    values = {
                        "backend": {"phpFpm": {"enabled": enabled}, "skipMigrate": skip},
                        "extraVolumes": [{"name": "custom", "emptyDir": {}}],
                        "extraVolumeMounts": [{"name": "custom", "mountPath": "/custom"}],
                    }
                    spec = pod(render(values)["review-backend"])
                    init = {c["name"]: c for c in spec.get("initContainers", [])}
                    self.assertEqual("prepare-fpm" in init, enabled)
                    self.assertEqual("migrate" in init, not skip)
                    mounts = {m["name"] for m in spec["containers"][0]["volumeMounts"]}
                    self.assertIn("custom", mounts)
                    self.assertEqual("fpm-config" in mounts, enabled)
                    if enabled:
                        self.assertEqual(init["prepare-fpm"]["image"], spec["containers"][0]["image"])
                        self.assertNotIn("command", spec["containers"][0])
                        if not skip:
                            self.assertNotIn("fpm-config", {m["name"] for m in init["migrate"]["volumeMounts"]})

    def test_security_exceptions_are_local(self):
        workloads = render()
        for name in ("backend", "frontend", "nginx", "queue", "cron", "redis", "rabbitmq"):
            ctx = pod(workloads["review-" + name])["containers"][0]["securityContext"]
            self.assertFalse(ctx["allowPrivilegeEscalation"])
            self.assertEqual(ctx["capabilities"]["drop"], ["ALL"])
            self.assertEqual(bool(ctx["capabilities"].get("add")), name in ("backend", "frontend", "nginx", "rabbitmq"))

    def test_scheduler_is_still_resident(self):
        cron = render()["review-cron"]
        self.assertEqual(cron["spec"]["replicas"], 1)
        self.assertEqual(cron["spec"]["strategy"]["type"], "Recreate")
        self.assertEqual(pod(cron)["containers"][0]["command"], ["php", "artisan", "schedule:work"])

    def test_disable_and_replace_probes(self):
        spec = pod(render({"backend": {"readinessProbe": None, "livenessProbe": None}})["review-backend"])
        self.assertNotIn("readinessProbe", spec["containers"][0])
        self.assertNotIn("livenessProbe", spec["containers"][0])
        spec = pod(render({"backend": {"readinessProbe": {"exec": None, "tcpSocket": {"port": "http"}}}})["review-backend"])
        probe = spec["containers"][0]["readinessProbe"]
        self.assertNotIn("exec", probe)
        self.assertEqual(probe["tcpSocket"]["port"], "http")

    def test_readiness_http_and_transport_failures(self):
        # Выполняем именно команду из рендера, подменяя только ответ транспорта.
        container = pod(render()["review-backend"])["containers"][0]
        command = container["readinessProbe"]["exec"]["command"]
        self.assertIn("tcpSocket", container["livenessProbe"])
        with tempfile.TemporaryDirectory() as directory:
            curl = Path(directory) / "curl"
            curl.write_text('#!/bin/sh\nprintf "%s" "$TEST_HTTP_CODE"\nexit "$TEST_CURL_EXIT"\n')
            curl.chmod(0o755)
            for code, exit_code, ready in [("200", 0, True), ("301", 0, True), ("404", 0, True),
                                            ("500", 0, False), ("502", 0, False), ("503", 0, False),
                                            ("000", 28, False), ("000", 7, False), ("404", 28, False)]:
                with self.subTest(code=code, exit_code=exit_code):
                    env = dict(os.environ, PATH=directory + os.pathsep + os.environ["PATH"],
                               TEST_HTTP_CODE=code, TEST_CURL_EXIT=str(exit_code))
                    result = subprocess.run(command, env=env, capture_output=True)
                    self.assertEqual(result.returncode == 0, ready)

    def test_minio_client_names_and_missing_binary(self):
        job = render(kind="Job")["review-minio-bucket-init"]
        command = pod(job)["containers"][0]["command"]
        for binary in ("mc", "mcli", None):
            with self.subTest(binary=binary), tempfile.TemporaryDirectory() as directory:
                calls = Path(directory) / "calls"
                if binary:
                    executable = Path(directory) / binary
                    executable.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$TEST_MC_CALLS"\n')
                    executable.chmod(0o755)
                env = dict(os.environ, PATH=directory, TEST_MC_CALLS=str(calls), KEY="test", SECRET="test")
                result = subprocess.run(["/bin/sh", *command[1:]], env=env, capture_output=True, timeout=5)
                self.assertEqual(result.returncode == 0, binary is not None)
                if binary:
                    self.assertEqual(len(calls.read_text().splitlines()), 4)
                    self.assertIn("mb --ignore-existing doqa/doqa", calls.read_text())
                else:
                    self.assertIn("mc/mcli", result.stderr.decode())

    def test_invalid_parameters_are_rejected(self):
        for values in [{"backend": {"phpFpm": {"maxChildren": 0}}},
                       {"nginx": {"proxyReadTimeout": "60s; invalid"}},
                       {"nginx": {"websocketReadTimeout": ""}}]:
            with self.subTest(values=values), self.assertRaises(subprocess.CalledProcessError):
                render(values)


if __name__ == "__main__":
    unittest.main()
