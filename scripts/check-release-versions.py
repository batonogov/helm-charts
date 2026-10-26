#!/usr/bin/env python3
"""Reject chart changes whose current version already has a release tag."""

import os
from pathlib import Path
import re
import subprocess
import sys


VERSION_RE = re.compile(r"^version:\s*(['\"]?)([^'\"\s#]+)\1(?:\s*(?:#.*)?)$")


def changed_paths(before, after, cwd=None):
    if before and set(before) == {"0"}:
        before = ""
    if before:
        command = ["git", "diff", "--no-renames", "--name-only", "-z", before, after]
    else:
        command = ["git", "diff-tree", "--root", "--no-commit-id", "--no-renames",
                   "--name-only", "-r", "-z", after]
    output = subprocess.check_output(command, cwd=cwd, text=True)
    return [path for path in output.split("\0") if path]


def changed_chart_dirs(paths):
    charts = set()
    for path in paths:
        parts = path.split("/")
        if len(parts) >= 3 and parts[0] == "charts" and parts[1]:
            charts.add("/".join(parts[:2]))
    return sorted(charts)


def chart_version(path):
    for line in path.read_text().splitlines():
        match = VERSION_RE.match(line)
        if match:
            return match.group(2)
    raise RuntimeError(f"cannot read chart version from {path}")


def already_released(root, before, after):
    released = []
    for chart_dir in changed_chart_dirs(changed_paths(before, after, cwd=root)):
        chart_yaml = root / chart_dir / "Chart.yaml"
        if not chart_yaml.is_file():
            continue
        chart = Path(chart_dir).name
        tag = f"{chart}-{chart_version(chart_yaml)}"
        result = subprocess.run(
            ["git", "tag", "--list", tag],
            cwd=root, capture_output=True, text=True, check=True,
        )
        if result.stdout.strip():
            released.append((chart_dir, tag))
    return released


def main():
    root = Path(__file__).resolve().parent.parent
    before = os.environ.get("BEFORE_SHA", "")
    after = os.environ.get("AFTER_SHA", "HEAD")
    released = already_released(root, before, after)
    if released:
        for chart_dir, tag in released:
            print(f"error: {chart_dir} changed, but release tag {tag} already exists", file=sys.stderr)
        print("Bump each changed chart version before merging; refusing a no-op release.", file=sys.stderr)
        return 1
    print("Release preflight passed: no changed chart has an existing version tag.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
