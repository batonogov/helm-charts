#!/usr/bin/env python3
"""Exercise DoQA image inventory parsing without registry access."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


REPOSITORIES = (
    "doqa/doqa-backend",
    "doqa/doqa-frontend",
    "doqa/doqa-parsing-autotests",
    "doqa/doqa-statistic",
    "doqa/doqa-notify",
    "doqa/doqa-llm",
    "doqa/doqa-telegram-bot",
)


class AuditDoqaImagesTests(unittest.TestCase):
    def test_inline_comments_do_not_make_unchanged_images_look_changed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = Path(__file__).with_name("audit-doqa-images.sh")
            old_values = root / "old.yaml"
            new_values = root / "new.yaml"
            old_values.write_text("".join(
                f"component{index}:\n  image:\n    repository: {repo} # vendor\n"
                f"    tag: 1.0.0-box # pin\n"
                for index, repo in enumerate(REPOSITORIES)
            ))
            new_values.write_text("".join(
                f"component{index}:\n  image:\n    repository: {repo}\n    tag: 1.0.0-box\n"
                for index, repo in enumerate(REPOSITORIES)
            ))
            bin_dir = root / "bin"
            bin_dir.mkdir()
            crane_calls = root / "crane-calls"
            crane = bin_dir / "crane"
            crane.write_text("#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$CRANE_CALLS\"\nexit 99\n")
            crane.chmod(0o755)
            jq = bin_dir / "jq"
            jq.write_text("#!/bin/sh\nexit 99\n")
            jq.chmod(0o755)
            env = dict(os.environ, PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                       CRANE_CALLS=str(crane_calls))
            result = subprocess.run(
                [str(script), str(old_values), str(new_values)],
                capture_output=True, text=True, env=env, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse(crane_calls.exists(), crane_calls.read_text() if crane_calls.exists() else "")


if __name__ == "__main__":
    unittest.main()
