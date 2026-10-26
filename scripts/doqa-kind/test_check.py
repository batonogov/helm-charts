#!/usr/bin/env python3
"""Regression checks for live scenario configuration without starting a cluster."""

import os
import tempfile
import unittest

os.environ.setdefault("DOQA_KIND_WORK", tempfile.gettempdir())
os.environ.setdefault("DOQA_KIND_NAME", "doqa-unit")

import check


class CheckTests(unittest.TestCase):
    def test_explicit_upgrade_is_separate_and_uses_explicit_values(self):
        self.assertEqual(check.value_files("fresh"), [check.VALUES])
        self.assertEqual(check.value_files("upgrade"), [check.VALUES])
        self.assertEqual(check.value_files("upgrade-explicit"),
                         [check.VALUES, check.EXPLICIT_VALUES])
        self.assertTrue(check.EXPLICIT_VALUES.is_file())


if __name__ == "__main__":
    unittest.main()
