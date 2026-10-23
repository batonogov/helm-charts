#!/usr/bin/env python3
"""Fail closed when detecting changes that require live integration checks."""

import os
import subprocess


def affected(paths):
    return any(path.startswith(("charts/doqa/", "scripts/doqa-kind/", ".github/doqa-kind/"))
               or path == ".github/workflows/doqa-kind.yaml" for path in paths)


def changed_paths(base, cwd=None):
    # Include both paths of renames, including files moved out of tested directories.
    return subprocess.check_output(["git", "diff", "--no-renames", "--name-only", "-z", base, "HEAD"],
                                   text=True, cwd=cwd).split("\0")


if __name__ == "__main__":
    base = os.environ.get("BASE_SHA")
    required = not base or affected(changed_paths(base))
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        output.write("run=" + str(required).lower() + "\n")
    print("DoQA integration required:", required)
