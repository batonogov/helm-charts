#!/usr/bin/env python3
"""Collect bounded status/log artifacts; exclude manifests, kubeconfig and Secret data."""

import base64
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import subprocess


work = Path(os.environ["DOQA_KIND_WORK"])
out = work / "diagnostics"
out.mkdir(parents=True, exist_ok=True)
context = "kind-" + os.environ["DOQA_KIND_NAME"]
command = ["kubectl", "--context", context, "--request-timeout=15s"]


def capture(args):
    try:
        result = subprocess.run(command + args, capture_output=True, text=True, timeout=25)
        return result.returncode, result.stdout + result.stderr
    except (OSError, subprocess.TimeoutExpired) as error:
        return 1, str(error)


for name in ("baseline.json", "result.json"):
    if (work / name).exists():
        shutil.copyfile(work / name, out / name)

for namespace in ("doqa-smoke", "cnpg-system"):
    code, secret_json = capture(["-n", namespace, "get", "secrets", "-o", "json"])
    sensitive = []
    try:
        if code:
            raise ValueError("Secrets could not be read for log redaction")
        for secret in json.loads(secret_json)["items"]:
            for value in secret.get("data", {}).values():
                decoded = base64.b64decode(value).decode("utf-8", errors="ignore")
                if len(decoded) >= 6:
                    sensitive.extend((decoded, value))
    except (ValueError, KeyError):
        # Fail closed for logs when redaction cannot be prepared.
        sensitive = None

    def save(name, args):
        _, text = capture(["-n", namespace, *args])
        if sensitive is not None:
            for value in sorted(set(sensitive), key=len, reverse=True):
                text = text.replace(value, "[REDACTED]")
        (out / (namespace + "-" + name + ".log")).write_text(text)

    # These table formats do not include Secret data or pod environment.
    save("status", ["get", "pods,deployments,services,pvc,jobs,clusters.postgresql.cnpg.io", "-o", "wide"])
    save("events", ["get", "events", "--sort-by=.metadata.creationTimestamp"])
    if sensitive is None:
        continue
    code, pods_json = capture(["-n", namespace, "get", "pods", "-o", "json"])
    if code:
        continue
    tasks = []
    pods = json.loads(pods_json)["items"]
    images = []
    for pod in pods:
        for status in pod.get("status", {}).get("initContainerStatuses", []) + pod.get("status", {}).get("containerStatuses", []):
            terminated = status.get("state", {}).get("terminated") or status.get("lastState", {}).get("terminated", {})
            images.append({"pod": pod["metadata"]["name"], "container": status["name"],
                           "image": status["image"], "image_id": status.get("imageID", ""),
                           "restart_count": status["restartCount"], "ready": status["ready"],
                           "last_exit_reason": terminated.get("reason"),
                           "last_exit_code": terminated.get("exitCode")})
        for container in pod["spec"].get("initContainers", []) + pod["spec"]["containers"]:
            name = pod["metadata"]["name"] + "-" + container["name"]
            args = ["logs", pod["metadata"]["name"], "-c", container["name"], "--tail=200"]
            tasks.append((name, args))
            tasks.append((name + "-previous", args + ["--previous"]))
    (out / (namespace + "-images.json")).write_text(json.dumps(images, indent=2) + "\n")
    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda task: save(*task), tasks))
print(f"Diagnostics saved to {out}")
