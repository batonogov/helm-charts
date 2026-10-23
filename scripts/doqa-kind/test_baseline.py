#!/usr/bin/env python3
"""Regression checks for chart-specific published upgrade baseline selection."""

import unittest

from baseline import resolve


def release(version, *, digest=True):
    name = f"doqa-{version}.tgz"
    return {"tag_name": f"doqa-{version}", "draft": False, "prerelease": False,
            "html_url": f"https://github.com/batonogov/helm-charts/releases/tag/doqa-{version}",
            "assets": [{"name": name, "digest": "sha256:" + "a" * 64 if digest else None,
                        "browser_download_url": f"https://github.com/batonogov/helm-charts/releases/download/doqa-{version}/{name}"}]}


class BaselineTests(unittest.TestCase):
    def test_selects_latest_stable_chart_by_semver(self):
        other = release("99.0.0")
        other["tag_name"] = "xray-health-exporter-99.0.0"
        draft = release("100.0.0")
        draft["draft"] = True
        prerelease = release("101.0.0")
        prerelease["prerelease"] = True
        self.assertEqual(resolve([other, draft, prerelease, release("0.9.0"), release("0.10.0")],
                                 "0.11.0")["version"], "0.10.0")

    def test_same_version_for_repository_only_changes(self):
        self.assertEqual(resolve([release("0.10.0")], "0.10.0")["version"], "0.10.0")

    def test_refuses_downgrades_and_missing_baseline(self):
        for releases in ([], [release("0.11.0")]):
            with self.subTest(releases=releases), self.assertRaises(RuntimeError):
                resolve(releases, "0.10.0")

    def test_requires_published_checksum_and_expected_asset_url(self):
        bad_url = release("0.9.0")
        bad_url["assets"][0]["browser_download_url"] = "https://example.com/chart.tgz"
        for item in (release("0.9.0", digest=False), bad_url):
            with self.subTest(item=item), self.assertRaises(RuntimeError):
                resolve([item], "0.10.0")


if __name__ == "__main__":
    unittest.main()
