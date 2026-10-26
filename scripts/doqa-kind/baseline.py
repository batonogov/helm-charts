#!/usr/bin/env python3
"""Resolve and verify the latest published stable DoQA chart, independently of other charts."""

import hashlib
import json
import os
from pathlib import Path
import re
import sys
import urllib.request


API = "https://api.github.com/repos/batonogov/helm-charts/releases"


def resolve(releases, candidate, required=None):
    stable = []
    for release in releases:
        match = re.fullmatch(r"doqa-(\d+)\.(\d+)\.(\d+)", release["tag_name"])
        if match and not release["draft"] and not release["prerelease"]:
            stable.append((tuple(map(int, match.groups())), release))
    if required:
        stable = [entry for entry in stable if entry[0] == tuple(map(int, required.split(".")))]
    if not stable:
        raise RuntimeError("No published stable DoQA baseline exists")
    version, release = max(stable, key=lambda entry: entry[0])
    if version > tuple(map(int, candidate.split("."))):
        raise RuntimeError("Candidate is older than the published baseline; update this branch")
    name = "doqa-" + ".".join(map(str, version)) + ".tgz"
    asset = next(a for a in release["assets"] if a["name"] == name)
    digest = asset.get("digest", "") or ""
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise RuntimeError("Published baseline has no valid GitHub SHA256 digest")
    expected_url = f"https://github.com/batonogov/helm-charts/releases/download/{release['tag_name']}/{name}"
    if asset["browser_download_url"] != expected_url:
        raise RuntimeError("Unexpected baseline asset URL")
    return {"version": ".".join(map(str, version)), "sha256": digest[7:],
            "url": expected_url, "release": release["html_url"]}


def download(candidate, directory, required=None):
    headers = {"User-Agent": "helm-charts-kind-ci", "Accept": "application/vnd.github+json"}
    if os.environ.get("GH_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GH_TOKEN"]
    releases = []
    page = 1
    while True:
        request = urllib.request.Request(f"{API}?per_page=100&page={page}", headers=headers)
        with urllib.request.urlopen(request, timeout=60) as response:
            batch = json.load(response)
        releases.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    baseline = resolve(releases, candidate, required)
    with urllib.request.urlopen(baseline["url"], timeout=180) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != baseline["sha256"]:
        raise RuntimeError("Published baseline archive checksum mismatch")
    (directory / "baseline.tgz").write_bytes(data)
    (directory / "baseline.json").write_text(json.dumps(baseline, indent=2) + "\n")
    print(f"Upgrade baseline: DoQA {baseline['version']} sha256:{baseline['sha256']}", flush=True)
    return directory / "baseline.tgz"


if __name__ == "__main__":
    download(sys.argv[1], Path(sys.argv[2]))
