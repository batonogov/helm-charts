#!/usr/bin/env python3
"""Check a fresh pod snapshot; terminating rollout pods must disappear first."""

import json
import sys


def ready(pods, replicas=2):
    return len(pods) == replicas and all(
        not pod["metadata"].get("deletionTimestamp")
        and any(condition["type"] == "Ready" and condition["status"] == "True"
                for condition in pod.get("status", {}).get("conditions", []))
        for pod in pods
    )


if __name__ == "__main__":
    sys.exit(0 if ready(json.load(sys.stdin)["items"]) else 1)
