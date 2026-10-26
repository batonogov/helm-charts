#!/usr/bin/env python3
"""Exercise release preflight against real temporary git histories."""

import importlib
from pathlib import Path
import subprocess
import tempfile
import unittest

preflight = importlib.import_module("check-release-versions")


class ReleasePreflightTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.addCleanup(self.tempdir.cleanup)
        self.git("init")

    def git(self, *args):
        return subprocess.check_output(
            ["git", "-c", "user.name=CI", "-c", "user.email=ci@example.invalid", *args],
            cwd=self.root, text=True, stderr=subprocess.DEVNULL,
        ).strip()

    def commit(self, message):
        self.git("add", "-A")
        self.git("commit", "-m", message)
        return self.git("rev-parse", "HEAD")

    def write_chart(self, version="1.0.0"):
        chart = self.root / "charts/demo"
        chart.mkdir(parents=True, exist_ok=True)
        (chart / "Chart.yaml").write_text(f'apiVersion: v2\nname: demo\nversion: "{version}"\n')

    def test_docs_only_push_ignores_existing_chart_tags(self):
        self.write_chart()
        before = self.commit("initial chart")
        self.git("tag", "demo-1.0.0")
        (self.root / "README.md").write_text("docs\n")
        after = self.commit("docs")
        self.assertEqual(preflight.already_released(self.root, before, after), [])

    def test_changed_chart_with_existing_version_tag_fails(self):
        self.write_chart()
        before = self.commit("initial chart")
        self.git("tag", "demo-1.0.0")
        (self.root / "charts/demo/README.md").write_text("changed\n")
        after = self.commit("chart change without version bump")
        self.assertEqual(preflight.already_released(self.root, before, after),
                         [("charts/demo", "demo-1.0.0")])

    def test_changed_chart_with_new_version_and_no_tags_passes(self):
        self.write_chart()
        before = self.commit("initial chart")
        self.write_chart("1.1.0")
        after = self.commit("new chart version")
        self.assertEqual(preflight.already_released(self.root, before, after), [])

    def test_range_covers_every_commit_in_push(self):
        self.write_chart()
        before = self.commit("initial chart")
        self.git("tag", "demo-1.0.0")
        (self.root / "README.md").write_text("docs\n")
        self.commit("first commit in push")
        (self.root / "charts/demo/values.yaml").write_text("replicaCount: 1\n")
        after = self.commit("second commit in push")
        self.assertEqual(preflight.already_released(self.root, before, after),
                         [("charts/demo", "demo-1.0.0")])

    def test_first_root_push_without_tags_passes(self):
        self.write_chart()
        after = self.commit("first release")
        self.assertEqual(preflight.already_released(self.root, "0" * 40, after), [])

    def test_renamed_out_of_chart_still_requires_new_version(self):
        self.write_chart()
        source = self.root / "charts/demo/values.yaml"
        source.write_text("replicaCount: 1\n")
        before = self.commit("initial chart")
        self.git("tag", "demo-1.0.0")
        target = self.root / "docs/values.yaml"
        target.parent.mkdir()
        source.rename(target)
        after = self.commit("rename out of chart")
        self.assertEqual(preflight.already_released(self.root, before, after),
                         [("charts/demo", "demo-1.0.0")])

    def test_renamed_chart_directory_uses_chart_name_for_tag(self):
        chart = self.root / "charts/old-name"
        chart.mkdir(parents=True)
        (chart / "Chart.yaml").write_text("apiVersion: v2\nname: demo\nversion: 1.0.0\n")
        (chart / "values.yaml").write_text("replicaCount: 1\n")
        before = self.commit("initial chart")
        self.git("tag", "demo-1.0.0")
        renamed = self.root / "charts/new-name"
        chart.rename(renamed)
        (renamed / "values.yaml").write_text("replicaCount: 2\n")
        after = self.commit("rename chart directory and change values")
        self.assertEqual(preflight.already_released(self.root, before, after),
                         [("charts/new-name", "demo-1.0.0")])

    def test_yaml_escaped_name_and_version_are_decoded(self):
        chart = self.root / "charts/demo"
        chart.mkdir(parents=True)
        (chart / "Chart.yaml").write_text(
            'apiVersion: v2\nname: "\\u0064emo"\nversion: "\\u0030.9.0"\n')
        before = self.commit("initial chart")
        self.git("tag", "demo-0.9.0")
        (chart / "values.yaml").write_text("replicaCount: 1\n")
        after = self.commit("chart change")
        self.assertEqual(preflight.already_released(self.root, before, after),
                         [("charts/demo", "demo-0.9.0")])

    def test_duplicate_name_and_version_use_last_values(self):
        chart = self.root / "charts/demo"
        chart.mkdir(parents=True)
        (chart / "Chart.yaml").write_text(
            "apiVersion: v2\nname: wrong\nname: demo\nversion: 0.0.1\nversion: 1.0.0\n")
        before = self.commit("initial chart")
        self.git("tag", "demo-1.0.0")
        (chart / "values.yaml").write_text("replicaCount: 1\n")
        after = self.commit("chart change")
        self.assertEqual(preflight.already_released(self.root, before, after),
                         [("charts/demo", "demo-1.0.0")])

    def test_zero_before_checks_chart_from_earlier_commit(self):
        self.write_chart()
        self.commit("initial chart")
        self.git("tag", "demo-1.0.0")
        (self.root / "charts/demo/values.yaml").write_text("replicaCount: 1\n")
        self.commit("chart change")
        (self.root / "README.md").write_text("last commit is docs only\n")
        after = self.commit("docs")
        self.assertEqual(preflight.already_released(self.root, "0" * 40, after),
                         [("charts/demo", "demo-1.0.0")])

    def test_zero_before_checks_chart_at_merge_commit(self):
        self.write_chart()
        self.commit("initial chart")
        self.git("tag", "demo-1.0.0")
        main = self.git("branch", "--show-current")
        self.git("checkout", "-b", "chart-change")
        (self.root / "charts/demo/values.yaml").write_text("replicaCount: 1\n")
        self.commit("chart change")
        self.git("checkout", main)
        (self.root / "README.md").write_text("main branch docs\n")
        self.commit("docs")
        self.git("merge", "--no-ff", "chart-change", "-m", "merge chart change")
        after = self.git("rev-parse", "HEAD")
        self.assertEqual(preflight.already_released(self.root, "0" * 40, after),
                         [("charts/demo", "demo-1.0.0")])


if __name__ == "__main__":
    unittest.main()
