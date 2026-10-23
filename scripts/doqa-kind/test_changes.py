#!/usr/bin/env python3
"""Exercise relevant/irrelevant changes and a real rename outside the tested tree."""

from pathlib import Path
import subprocess
import tempfile
import unittest

from changes import affected, changed_paths


class ChangesTests(unittest.TestCase):
    def test_relevant_and_irrelevant_paths(self):
        for path in ("charts/doqa/values.yaml", "scripts/doqa-kind/check.py",
                     ".github/doqa-kind/values.yaml", ".github/workflows/doqa-kind.yaml"):
            with self.subTest(path=path):
                self.assertTrue(affected([path]))
        self.assertFalse(affected(["README.md", "charts/xray-health-exporter/values.yaml", ""]))

    def test_renamed_out_script_still_triggers_integration(self):
        with tempfile.TemporaryDirectory() as directory:
            def git(*args):
                return subprocess.check_output(["git", "-c", "user.name=CI", "-c", "user.email=ci@example.invalid",
                                                *args], cwd=directory, text=True, stderr=subprocess.DEVNULL).strip()
            git("init")
            source = Path(directory) / "scripts/doqa-kind/check.py"
            source.parent.mkdir(parents=True)
            source.write_text("print('unchanged content')\n")
            git("add", ".")
            git("commit", "-m", "baseline")
            base = git("rev-parse", "HEAD")
            target = Path(directory) / "docs/check.py"
            target.parent.mkdir()
            source.rename(target)
            git("add", "-A")
            git("commit", "-m", "rename outside integration tree")
            self.assertTrue(affected(changed_paths(base, cwd=directory)))

    def test_bad_base_is_an_error_instead_of_a_skip(self):
        with self.assertRaises(subprocess.CalledProcessError):
            changed_paths("this-is-not-a-revision")


if __name__ == "__main__":
    unittest.main()
