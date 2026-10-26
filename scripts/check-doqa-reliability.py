#!/usr/bin/env python3
"""DoQA regression checks: require Helm and PyYAML (also used by chart-testing)."""

import base64
import os
import re
import shutil
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parent.parent
CHART = ROOT / "charts/doqa"


def render(values=None, kind="Deployment", fullname="review"):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml") as extra:
        yaml.safe_dump(values or {}, extra)
        extra.flush()
        result = subprocess.run(
            ["helm", "template", "review", str(CHART), "-f",
             str(CHART / "ci/test-values.yaml"), "-f", extra.name,
             "--kube-version", "1.32.0", "--set", f"fullnameOverride={fullname}"],
            capture_output=True, text=True, check=True,
        )
    documents = [doc for doc in yaml.safe_load_all(result.stdout)
                 if doc and (kind is None or doc["kind"] == kind)]
    if kind is None:
        return documents
    return {doc["metadata"]["name"]: doc for doc in documents}


def resource_name(fullname, suffix):
    return fullname[:63 - len(suffix) - 1].rstrip("-") + "-" + suffix


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

    def test_fresh_app_key_decodes_to_32_bytes(self):
        app_key = render(kind="Secret")["review-app-secrets"]["stringData"]["app-key"]
        self.assertTrue(app_key.startswith("base64:"))
        decoded = base64.b64decode(app_key.removeprefix("base64:"), validate=True)
        self.assertEqual(len(decoded), 32)

    def test_explicit_and_generated_secrets_can_be_mixed(self):
        explicit = {
            "app": "existing-app", "apiKeys": "existing-api", "pusher": "existing-pusher",
            "rabbitmq": "existing-rabbitmq", "minio": "existing-minio",
        }
        generated = render({"secrets": explicit}, kind="Secret")
        self.assertEqual(generated, {})

        generated = render({"secrets": {"app": "existing-app", "rabbitmq": "existing-rabbitmq"}},
                           kind="Secret")
        self.assertEqual(set(generated), {"review-api-keys", "review-pusher-secret", "review-minio-secrets"})
        backend_env = pod(render({"secrets": explicit})["review-backend"])["containers"][0]["env"]
        app_key = next(env for env in backend_env if env["name"] == "APP_KEY")
        self.assertEqual(app_key["valueFrom"]["secretKeyRef"]["name"], "existing-app")

    def test_notification_redis_password_inheritance(self):
        common = {
            "create": False, "host": "shared-redis",
            "passwordSecret": {"name": "shared-redis-auth", "key": "shared-key"},
        }
        inherited = pod(render({"redis": common})["review-notification"])["containers"][0]["env"]
        password = next(env for env in inherited if env["name"] == "REDIS_PASSWORD")
        self.assertEqual(password["valueFrom"]["secretKeyRef"],
                         {"name": "shared-redis-auth", "key": "shared-key"})

        separate = {"redis": {**common, "notification": {"host": "separate-redis"}}}
        env = pod(render(separate)["review-notification"])["containers"][0]["env"]
        password = next(item for item in env if item["name"] == "REDIS_PASSWORD")
        self.assertEqual(password, {"name": "REDIS_PASSWORD", "value": ""})

    def test_network_policy_minio_init_and_custom_pusher_port(self):
        policies = render({"networkPolicy": {"enabled": True}, "pusher": {"port": 7601}},
                          kind="NetworkPolicy")
        minio_policy = policies["review-allow-backend-to-minio"]["spec"]["ingress"][0]
        components = [rule["podSelector"]["matchLabels"]["app.kubernetes.io/component"]
                      for rule in minio_policy["from"]]
        self.assertIn("minio-init", components)
        self.assertEqual(minio_policy["ports"], [{"port": 9000, "protocol": "TCP"}])
        for name in ("review-allow-nginx-to-websocket", "review-allow-app-to-websocket"):
            with self.subTest(policy=name):
                self.assertEqual(policies[name]["spec"]["ingress"][0]["ports"],
                                 [{"port": 7601, "protocol": "TCP"}])

    def test_minio_tls_verification_setting(self):
        for value, expected in ((None, "on"), (True, "on"), (False, "off")):
            with self.subTest(value=value):
                values = {} if value is None else {"minio": {"tlsVerify": value}}
                config = render(values, kind="ConfigMap")["review-nginx"]["data"]["default.conf"]
                self.assertIn("proxy_ssl_server_name               on;", config)
                self.assertIn(f"proxy_ssl_verify                    {expected};", config)
                trusted_ca = "proxy_ssl_trusted_certificate       /etc/ssl/certs/ca-certificates.crt;"
                if value is False:
                    self.assertNotIn(trusted_ca, config)
                else:
                    self.assertIn(trusted_ca, config)

    def test_long_names_and_cross_references(self):
        fullname = "a" * 63
        values = {
            "networkPolicy": {"enabled": True}, "autoscaling": {"enabled": True},
            "podDisruptionBudget": {"enabled": True}, "serviceMonitor": {"enabled": True},
            "serviceAccount": {"create": True},
            "telegramBot": {"enabled": True, "tokenSecret": "telegram"},
        }
        documents = render(values, kind=None, fullname=fullname)
        by_kind = {}
        for doc in documents:
            name = doc["metadata"]["name"]
            self.assertLessEqual(len(name), 63, (doc["kind"], name))
            self.assertRegex(name, re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$"))
            by_kind.setdefault(doc["kind"], {})[name] = doc

        components = ("backend", "queue", "autotests-worker", "llm-bulk-queue", "cron",
                      "frontend", "autotest-parser", "statistic", "llm", "notification",
                      "notification-worker", "telegram-bot", "websocket", "nginx", "redis",
                      "rabbitmq", "minio")
        expected_deployments = {resource_name(fullname, component) for component in components}
        self.assertEqual(set(by_kind["Deployment"]), expected_deployments)
        service_components = ("backend", "frontend", "autotest-parser", "statistic", "llm",
                              "notification", "websocket", "nginx", "redis", "rabbitmq", "minio")
        self.assertEqual(set(by_kind["Service"]),
                         {resource_name(fullname, component) for component in service_components})
        self.assertEqual(set(by_kind["ConfigMap"]),
                         {resource_name(fullname, "env"), resource_name(fullname, "nginx")})

        cluster = resource_name(fullname, "cnpg-app").removesuffix("-app")
        self.assertEqual(set(by_kind["Cluster"]), {cluster})
        self.assertLessEqual(len(cluster + "-app"), 63)
        config = by_kind["ConfigMap"][resource_name(fullname, "env")]["data"]
        self.assertEqual(config["DB_HOST"], cluster + "-rw")
        self.assertEqual(config["REDIS_HOST"], resource_name(fullname, "redis"))
        self.assertEqual(config["RABBITMQ_HOST"], resource_name(fullname, "rabbitmq"))
        self.assertEqual(config["MINIO_ENDPOINT"],
                         f"http://{resource_name(fullname, 'minio')}:9000")
        self.assertEqual(config["PUSHER_APP_HOST"], resource_name(fullname, "websocket"))
        for key, component, port in (("STATISTIC_ENDPOINT", "statistic", 3000),
                                     ("NOTIFICATION_ENDPOINT", "notification", 3000),
                                     ("LLM_ENDPOINT", "llm", 3000),
                                     ("AUTOTEST_PARSER_SERVICE_URL", "autotest-parser", 8000)):
            self.assertEqual(config[key], f"http://{resource_name(fullname, component)}:{port}" +
                             ("/" if key != "AUTOTEST_PARSER_SERVICE_URL" else ""))

        ingress = by_kind["Ingress"][fullname]
        self.assertEqual(ingress["spec"]["rules"][0]["http"]["paths"][0]["backend"]["service"]["name"],
                         resource_name(fullname, "nginx"))
        self.assertEqual(ingress["spec"]["tls"][0]["secretName"], resource_name(fullname, "tls"))
        nginx = by_kind["ConfigMap"][resource_name(fullname, "nginx")]["data"]["default.conf"]
        for component, port in (("frontend", 8080), ("backend", 8080), ("autotest-parser", 8000)):
            self.assertIn(f"proxy_pass                          http://{resource_name(fullname, component)}:{port};",
                          nginx)
        self.assertIn(f"http://{resource_name(fullname, 'websocket')}:6001/app/web-socket", nginx)

        job_name = resource_name(fullname, "minio-bucket-init")
        self.assertEqual(set(by_kind["Job"]), {job_name})
        self.assertIn(f"http://{resource_name(fullname, 'minio')}:9000",
                      pod(by_kind["Job"][job_name])["containers"][0]["command"][-1])
        postgresql_policy = next(policy for policy in by_kind["NetworkPolicy"].values()
                                 if "cnpg.io/cluster" in policy["spec"]["podSelector"]["matchLabels"])
        self.assertEqual(postgresql_policy["spec"]["podSelector"]["matchLabels"]["cnpg.io/cluster"],
                         cluster)

        allowed_secrets = set(by_kind["Secret"]) | {cluster + "-app", "telegram"}
        for kind in ("Deployment", "Job"):
            for doc in by_kind[kind].values():
                spec = pod(doc)
                self.assertEqual(spec["serviceAccountName"], fullname)
                for container in spec["containers"] + spec.get("initContainers", []):
                    for env in container.get("env", []):
                        ref = env.get("valueFrom", {}).get("secretKeyRef")
                        if ref:
                            self.assertIn(ref["name"], allowed_secrets)
                    for env_from in container.get("envFrom", []):
                        if "configMapRef" in env_from:
                            self.assertIn(env_from["configMapRef"]["name"], by_kind["ConfigMap"])
                for volume in spec.get("volumes", []):
                    if "configMap" in volume:
                        self.assertIn(volume["configMap"]["name"], by_kind["ConfigMap"])
                    if "persistentVolumeClaim" in volume:
                        self.assertIn(volume["persistentVolumeClaim"]["claimName"],
                                      by_kind["PersistentVolumeClaim"])

        for hpa in by_kind["HorizontalPodAutoscaler"].values():
            self.assertIn(hpa["spec"]["scaleTargetRef"]["name"], expected_deployments)
        self.assertEqual(set(by_kind["PodDisruptionBudget"]),
                         {resource_name(fullname, component + "-pdb")
                          for component in ("backend", "frontend", "queue")})
        self.assertIn(resource_name(fullname, "backend"), by_kind["ServiceMonitor"])

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
