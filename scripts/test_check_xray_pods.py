#!/usr/bin/env python3
"""Regression checks for pod churn during the xray integration rollout."""

import importlib.util
from pathlib import Path
import unittest


spec = importlib.util.spec_from_file_location(
    "check_xray_pods", Path(__file__).with_name("check-xray-pods.py"))
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


def pod(name, ready="True", terminating=False):
    metadata = {"name": name}
    if terminating:
        metadata["deletionTimestamp"] = "2026-11-02T20:24:54Z"
    return {"metadata": metadata, "status": {"conditions": [
        {"type": "Ready", "status": ready},
    ]}}


class ReadyTests(unittest.TestCase):
    def test_rollout_rechecks_after_old_pod_disappears(self):
        current = [pod("new-1"), pod("new-2")]
        self.assertFalse(check.ready([pod("old", "False", True), *current]))
        self.assertTrue(check.ready(current))

    def test_requires_exactly_two_replicas(self):
        for pods in ([], [pod("one")], [pod(str(i)) for i in range(3)]):
            with self.subTest(pods=pods):
                self.assertFalse(check.ready(pods))

    def test_requires_every_pod_ready(self):
        for status in ("False", "Unknown"):
            self.assertFalse(check.ready([pod("one"), pod("two", status)]))
        self.assertFalse(check.ready([pod("one"), {"metadata": {"name": "two"}}]))

    def test_ready_terminating_pod_does_not_count(self):
        self.assertFalse(check.ready([pod("old", terminating=True), pod("new")]))


if __name__ == "__main__":
    unittest.main()
