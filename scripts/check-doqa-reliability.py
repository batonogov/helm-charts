#!/usr/bin/env python3
"""DoQA regression checks: require Helm and PyYAML (also used by chart-testing)."""

import os
import shutil
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
             str(CHART / "ci/test-values.yaml"), "-f", extra.name,
             "--kube-version", "1.32.0", "--set", "fullnameOverride=review"],
            capture_output=True, text=True, check=True,
        )
    return {doc["metadata"]["name"]: doc
            for doc in yaml.safe_load_all(result.stdout)
            if doc and doc["kind"] == kind}


def pod(doc):
    return doc["spec"]["template"]["spec"]


class ReliabilityTests(unittest.TestCase):
    def test_product_environment_reaches_each_consumer(self):
        for custom in (False, True):
            with self.subTest(custom=custom):
                values = {"telegramBot": {"enabled": True, "tokenSecret": "telegram"}}
                if custom:
                    values["product"] = {
                        "id": "acme", "appName": "Acme App", "appBrand": "Acme Brand",
                        "name": "Acme", "fromDisplay": "Acme Support",
                        "supportEmail": "support@acme.example", "docsUrl": "https://acme.example/docs",
                        "siteUrl": "https://acme.example", "telegramUrl": "",
                        "supportTelegramUrl": "", "vkUrl": "", "youtubeUrl": "",
                        "telegramNewsUrl": "",
                    }
                config = render(values, kind="ConfigMap")["review-env"]["data"]
                expected_name = "Acme" if custom else "DoQA"
                self.assertEqual(config["CACHE_PREFIX"], "laravel_cache:")
                self.assertEqual(config["REDIS_PREFIX"], "laravel_database_")
                self.assertEqual(config["SESSION_COOKIE"], "laravel_session")
                self.assertEqual(config["PRODUCT"], "acme" if custom else "doqa")
                self.assertEqual(config["APP_NAME"], "Acme App" if custom else "DoQA")
                self.assertEqual(config["APP_BRAND"], "Acme Brand" if custom else "DoQA")
                self.assertEqual(config["PRODUCT_NAME"], expected_name)
                self.assertEqual(config["PRODUCT_TELEGRAM_NEWS_URL"],
                                 "" if custom else "https://t.me/DoQA_news_bot")
                expected_brand = {
                    "PRODUCT_FROM_DISPLAY": "Acme Support" if custom else "DoQA",
                    "PRODUCT_SUPPORT_EMAIL": "support@acme.example" if custom else "support@doqa.app",
                    "PRODUCT_DOCS_URL": "https://acme.example/docs" if custom else "https://docs.doqa.app",
                    "PRODUCT_SITE_URL": "https://acme.example" if custom else "https://doqa.app",
                    "PRODUCT_TELEGRAM_URL": "" if custom else "https://t.me/DoQATMS",
                    "PRODUCT_SUPPORT_TELEGRAM_URL": "" if custom else "https://t.me/doqa_team",
                    "PRODUCT_VK_URL": "" if custom else "https://vk.com/doqa_tms",
                    "PRODUCT_YOUTUBE_URL": ("" if custom else
                                            "https://www.youtube.com/channel/UCTzbumj-8d9ijeU3gEWWTPQ"),
                }
                for key, expected in expected_brand.items():
                    self.assertEqual(config[key], expected, key)
                deployments = render(values)
                for component in ("backend", "queue", "cron", "autotests-worker", "llm-bulk-queue"):
                    spec = pod(deployments["review-" + component])
                    consumers = spec["containers"] + [c for c in spec.get("initContainers", [])
                                                       if c["name"] == "migrate"]
                    for container in consumers:
                        self.assertIn({"configMapRef": {"name": "review-env"}}, container["envFrom"])
                for component in ("notification", "notification-worker", "telegram-bot"):
                    env = {e["name"]: e.get("value") for e in
                           pod(deployments["review-" + component])["containers"][0]["env"]}
                    self.assertEqual(env["APP_TITLE"], expected_name + " - Notification")
                    for key in ("PRODUCT_NAME", "PRODUCT_FROM_DISPLAY", "PRODUCT_SUPPORT_EMAIL",
                                "PRODUCT_DOCS_URL", "PRODUCT_SITE_URL", "PRODUCT_TELEGRAM_URL",
                                "PRODUCT_SUPPORT_TELEGRAM_URL", "PRODUCT_VK_URL", "PRODUCT_YOUTUBE_URL"):
                        self.assertEqual(env[key], config[key], (component, key))
                for component, suffix in (("autotest-parser", " Autotests"),
                                          ("statistic", " - Statistic"), ("llm", " - LLM")):
                    env = {e["name"]: e.get("value") for e in
                           pod(deployments["review-" + component])["containers"][0]["env"]}
                    self.assertEqual(env["APP_TITLE"], expected_name + suffix)

    def test_custom_state_identity_is_independent_of_brand(self):
        config = render({"product": {"appName": "Acme"}, "backend": {
            "cachePrefix": "existing_cache:", "redisPrefix": "existing_redis_",
            "sessionCookie": "existing_session",
        }}, kind="ConfigMap")["review-env"]["data"]
        self.assertEqual(config["APP_NAME"], "Acme")
        self.assertEqual(config["CACHE_PREFIX"], "existing_cache:")
        self.assertEqual(config["REDIS_PREFIX"], "existing_redis_")
        self.assertEqual(config["SESSION_COOKIE"], "existing_session")

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
        # Run the rendered command, replacing only the transport response.
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

    def test_minio_initially_unreachable_server_recovers(self):
        command = pod(render(kind="Job")["review-minio-bucket-init"])["containers"][0]["command"]
        for binary in ("mc", "mcli"):
            with self.subTest(binary=binary), tempfile.TemporaryDirectory() as directory:
                calls = Path(directory) / "calls"
                executable = Path(directory) / binary
                executable.write_text('#!/bin/sh\nprintf \'%s\\n\' "$*" >> "$TEST_MC_CALLS"\ncase "$1" in\n  alias)\n    [ "$3" = --api ] && [ "$4" = S3v4 ] || exit 1\n    : > "$TEST_ALIAS"\n    ;;\n  ls)\n    [ -f "$TEST_ALIAS" ] || exit 1\n    if [ ! -f "$TEST_PROBED" ]; then\n      : > "$TEST_PROBED"\n      echo \'connection refused\' >&2\n      exit 1\n    fi\n    ;;\nesac\n')
                executable.chmod(0o755)
                (Path(directory) / "grep").symlink_to(shutil.which("grep"))
                sleep = Path(directory) / "sleep"
                sleep.write_text("#!/bin/sh\nexit 0\n")
                sleep.chmod(0o755)
                env = dict(os.environ, PATH=directory, KEY="test", SECRET="test",
                           TEST_MC_CALLS=str(calls), TEST_ALIAS=directory + "/alias",
                           TEST_PROBED=directory + "/probed")
                result = subprocess.run(["/bin/sh", *command[1:]], env=env, capture_output=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)
                recorded = calls.read_text().splitlines()
                self.assertTrue(recorded[0].startswith("alias set --api S3v4 doqa "))
                self.assertEqual(recorded.count("ls doqa"), 2)
                self.assertIn("anonymous set public doqa/doqa", recorded)

    def test_minio_alias_configuration_failure_is_fatal(self):
        command = pod(render(kind="Job")["review-minio-bucket-init"])["containers"][0]["command"]
        with tempfile.TemporaryDirectory() as directory:
            calls = Path(directory) / "calls"
            executable = Path(directory) / "mc"
            executable.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$TEST_MC_CALLS"\nexit 13\n')
            executable.chmod(0o755)
            env = dict(os.environ, PATH=directory, KEY="test", SECRET="test", TEST_MC_CALLS=str(calls))
            result = subprocess.run(["/bin/sh", *command[1:]], env=env, capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 13)
            self.assertEqual(len(calls.read_text().splitlines()), 1)

    def test_invalid_parameters_are_rejected(self):
        for values in [{"backend": {"cachePrefix": None}},
                       {"backend": {"redisPrefix": ""}},
                       {"backend": {"sessionCookie": None}},
                       {"product": None},
                       {"product": {"name": None}},
                       {"product": {"telegramUrl": None}},
                       {"product": {"id": "Invalid Slug"}},
                       {"product": {"name": ""}},
                       {"product": {"supportEmail": 123}},
                       {"backend": {"phpFpm": {"maxChildren": 0}}},
                       {"nginx": {"proxyReadTimeout": "60s; invalid"}},
                       {"nginx": {"websocketReadTimeout": ""}}]:
            with self.subTest(values=values):
                with self.assertRaises(subprocess.CalledProcessError) as failure:
                    render(values)
                self.assertIn("schema", failure.exception.stderr)


if __name__ == "__main__":
    unittest.main()
