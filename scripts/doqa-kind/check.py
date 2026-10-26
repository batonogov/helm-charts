#!/usr/bin/env python3
"""Install the release archive and exercise real DoQA services in a disposable kind cluster."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

from baseline import download


ROOT = Path(__file__).resolve().parents[2]
NAMESPACE = RELEASE = "doqa-smoke"
VALUES = ROOT / ".github/doqa-kind/values.yaml"
EXPLICIT_VALUES = ROOT / ".github/doqa-kind/upgrade-explicit-values.yaml"
WORK = Path(os.environ["DOQA_KIND_WORK"])
CONTEXT = "kind-" + os.environ["DOQA_KIND_NAME"]
KUBE = ["kubectl", "--context", CONTEXT, "--request-timeout=60s"]
HELM = ["helm", "--kube-context", CONTEXT, "--namespace", NAMESPACE]


def run(command, *, data=None, timeout=120):
    result = subprocess.run(command, input=data, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        # Never print successful secret JSON or literal secret data.
        raise RuntimeError(f"Command failed: {command[:5]}\n{result.stderr}")
    return result.stdout.strip()


def kube(*args, **kwargs):
    return run([*KUBE, "-n", NAMESPACE, *args], **kwargs)


def objects(kind):
    return json.loads(kube("get", kind, "-o", "json"))["items"]


def backend(code):
    bootstrap = ("require '/app/vendor/autoload.php'; $app = require '/app/bootstrap/app.php'; "
                 "$app->make(Illuminate\\Contracts\\Console\\Kernel::class)->bootstrap(); ")
    return kube("exec", "deployment/doqa-smoke-backend", "-c", "backend", "--", "php",
                "-d", "display_errors=stderr", "-r", bootstrap + code)


def wait_ready():
    kube("wait", "--for=condition=Ready", "cluster/doqa-smoke-cnpg", "--timeout=600s", timeout=620)
    for deployment in objects("deployments"):
        kube("rollout", "status", "deployment/" + deployment["metadata"]["name"], "--timeout=300s", timeout=320)


def http(path, *, follow=False):
    address = kube("get", "service", "doqa-smoke-nginx", "-o", "jsonpath={.spec.clusterIP}")
    redirects = ["--location", "--max-redirs", "5", "--proto-redir", "=http"] if follow else []
    output = kube("exec", "deployment/doqa-smoke-backend", "-c", "backend", "--", "curl", "--silent",
                  "--show-error", "--max-time", "20", "--proto", "=http", *redirects,
                  "--resolve", "doqa-ci.example.test:80:" + address,
                  "--write-out", "\n%{http_code}", "http://doqa-ci.example.test" + path)
    body, status = output.rsplit("\n", 1)
    if status != "200":
        raise RuntimeError(f"nginx {path}: expected HTTP 200, got {status}")
    return body


def health():
    wait_ready()
    deadline = time.monotonic() + 120
    while True:
        try:
            if "<html" not in http("/", follow=True).lower():
                raise RuntimeError("Frontend response is not HTML")
            config = json.loads(http("/api/auth/sso"))
            if not isinstance(config, dict) or not isinstance(config.get("enabled"), bool):
                raise RuntimeError("Public SSO configuration endpoint returned an unexpected payload")
            break
        except (RuntimeError, ValueError):
            if time.monotonic() >= deadline:
                raise
            time.sleep(5)
    # Check the optional 0.9.0 FPM configuration is actually loaded, not just rendered.
    kube("exec", "deployment/doqa-smoke-backend", "-c", "backend", "--", "php-fpm", "-t")
    kube("exec", "deployment/doqa-smoke-backend", "-c", "backend", "--", "sh", "-ec",
         "grep -q '^pm.max_children = 8$' /usr/local/etc/php-fpm.conf")
    def running_containers():
        containers = {}
        for pod in objects("pods"):
            if pod["metadata"].get("deletionTimestamp"):
                continue
            if pod["status"]["phase"] == "Succeeded":
                continue
            if pod["status"]["phase"] != "Running":
                raise RuntimeError("A workload pod is not Running: " + pod["metadata"]["name"])
            for status in pod["status"].get("containerStatuses", []):
                if not status["ready"]:
                    raise RuntimeError("A workload container is not Ready")
                containers[(pod["metadata"]["uid"], status["name"])] = status["restartCount"]
        return containers
    before = running_containers()
    time.sleep(20)
    if before != running_containers():
        raise RuntimeError("Containers restarted or were replaced during the stability check")
    print("Ready: all Deployments, CNPG, frontend, API through nginx, FPM override", flush=True)


def state_snapshot():
    suffixes = ("app-secrets", "api-keys", "pusher-secret", "rabbitmq-secret", "minio-secrets", "cnpg-app")
    secrets = {}
    for suffix in suffixes:
        secret = json.loads(kube("get", "secret", "doqa-smoke-" + suffix, "-o", "json"))
        secrets[suffix] = hashlib.sha256(json.dumps(secret["data"], sort_keys=True).encode()).hexdigest()
    volumes = {p["metadata"]["name"]: p["metadata"]["uid"] for p in objects("pvc")}
    if len(volumes) < 4:
        raise RuntimeError("Expected all four stateful components to have PVCs")
    identity = json.loads(backend("echo json_encode([config('cache.prefix'), config('database.redis.options.prefix'), config('session.cookie')]);"))
    return {"secrets": secrets, "pvc_uids": volumes, "identity": identity}


def sql(statement):
    return kube("exec", "doqa-smoke-cnpg-1", "-c", "postgres", "--", "psql", "-U", "postgres", "-d", "doqa",
                "-v", "ON_ERROR_STOP=1", "-Atqc", statement)


def minio(command, *, data=None):
    script = ('set -eu; MC_BIN="$(command -v mc || command -v mcli)"; '
              '"$MC_BIN" alias set ci http://doqa-smoke-minio:9000 "$KEY" "$SECRET" >/dev/null; ' + command)
    return kube("exec", "-i", "ci-minio-probe", "--", "sh", "-ec", script, data=data)


def create_probe():
    pod = {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": "ci-minio-probe"}, "spec": {
        "restartPolicy": "Never", "containers": [{"name": "probe",
        "image": "registry.control.doqa.app/service/mc:20240527.191746-r2-alpine",
        "command": ["sh", "-c", "sleep 3600"], "env": [
            {"name": "KEY", "valueFrom": {"secretKeyRef": {"name": "doqa-smoke-minio-secrets", "key": "access-key"}}},
            {"name": "SECRET", "valueFrom": {"secretKeyRef": {"name": "doqa-smoke-minio-secrets", "key": "secret-key"}}}],
        "resources": {"requests": {"cpu": "10m", "memory": "32Mi"}, "limits": {"memory": "128Mi"}}}]}}
    kube("apply", "-f", "-", data=json.dumps(pod))
    kube("wait", "--for=condition=Ready", "pod/ci-minio-probe", "--timeout=180s", timeout=200)


def seed(marker):
    # Use the application's public schema so a destructive schema reset loses the sentinel too.
    sql("CREATE TABLE public.ci_helm_smoke_marker(value text NOT NULL); "
        f"INSERT INTO public.ci_helm_smoke_marker VALUES ('{marker}');")
    backend(f"cache()->put('ci_helm_smoke', '{marker}', 3600);")
    minio('"$MC_BIN" pipe ci/doqa/ci-helm-smoke', data=marker)


def verify(marker):
    checks = [sql("SELECT value FROM public.ci_helm_smoke_marker;"),
              backend("echo cache()->get('ci_helm_smoke');"),
              minio('"$MC_BIN" cat ci/doqa/ci-helm-smoke'), http("/doqa/ci-helm-smoke")]
    if any(value != marker for value in checks):
        raise RuntimeError("PostgreSQL, Laravel cache or MinIO sentinel did not survive")
    print("Verified: PostgreSQL, Laravel cache, MinIO object and nginx object route", flush=True)


def value_files(scenario):
    return [VALUES] + ([EXPLICIT_VALUES] if scenario == "upgrade-explicit" else [])


def value_args(scenario):
    return [arg for path in value_files(scenario) for arg in ("-f", str(path))]


def install(archive, scenario):
    print("Installing packaged chart: " + archive.name, flush=True)
    run([*HELM, "install", RELEASE, str(archive), "--create-namespace", *value_args(scenario),
         "--wait", "--wait-for-jobs", "--timeout", "15m"], timeout=920)
    health()


def main(scenario):
    if not os.environ.get("KUBECONFIG"):
        raise RuntimeError("A dedicated KUBECONFIG is required")
    if json.loads(run([*KUBE, "config", "view", "-o", "json"]))["current-context"] != CONTEXT:
        raise RuntimeError("Refusing to test outside the dedicated kind context")
    package_dir = WORK / "package"
    package_dir.mkdir(parents=True, exist_ok=True)
    run(["helm", "package", str(ROOT / "charts/doqa"), "--destination", str(package_dir)])
    archives = list(package_dir.glob("doqa-*.tgz"))
    if len(archives) != 1:
        raise RuntimeError("Expected exactly one candidate chart archive")
    candidate = archives[0]
    version = candidate.name.removeprefix("doqa-").removesuffix(".tgz")
    marker = uuid.uuid4().hex
    if scenario in ("upgrade", "upgrade-explicit"):
        required = "0.10.0" if scenario == "upgrade-explicit" else None
        install(download(version, WORK, required), scenario)
        create_probe()
        seed(marker)
        verify(marker)
        before = state_snapshot()
        print("Upgrading to packaged candidate: " + candidate.name, flush=True)
        run([*HELM, "upgrade", RELEASE, str(candidate), *value_args(scenario), "--reset-values",
             "--wait", "--wait-for-jobs", "--timeout", "15m"], timeout=920)
        health()
        if before != state_snapshot():
            raise RuntimeError("Upgrade changed Secret data, PVC identities or application state prefixes")
        verify(marker)
        print("Upgrade preserved all Secret data, PVC UIDs and effective state prefixes", flush=True)
    else:
        install(candidate, scenario)
        create_probe()
        seed(marker)
        verify(marker)
        state_snapshot()
    result = {"scenario": scenario, "candidate_version": version, "result": "passed"}
    (WORK / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("fresh", "upgrade", "upgrade-explicit"):
        raise SystemExit("Usage: check.py fresh|upgrade|upgrade-explicit")
    main(sys.argv[1])
