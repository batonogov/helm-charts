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

    def test_changed_anchor_with_aliases_fetches_old_and_new_configs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = Path(__file__).with_name("audit-doqa-images.sh")
            old_values = root / "old.yaml"
            new_values = root / "new.yaml"
            for path, backend_tag in ((old_values, "1.0.0-box"), (new_values, "2.0.0-box")):
                text = (
                    f"component0: &backend_image\n  image:\n    repository: {REPOSITORIES[0]}\n"
                    f"    tag: {backend_tag}\n"
                    "backend_alias: *backend_image\n"
                    "nested:\n  child: *backend_image\n"
                )
                text += "".join(
                    f"component{index}:\n  image:\n    repository: {repo}\n    tag: 1.0.0-box\n"
                    for index, repo in enumerate(REPOSITORIES[1:], start=1)
                )
                path.write_text(text)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            crane_calls = root / "crane-calls"
            crane = bin_dir / "crane"
            crane.write_text(
                "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$CRANE_CALLS\"\n"
                "printf '%s\\n' '{\"config\":{\"Env\":[],\"Entrypoint\":null,"
                "\"Cmd\":null,\"User\":\"\",\"WorkingDir\":\"\"}}'\n")
            crane.chmod(0o755)
            env = dict(os.environ, PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                       CRANE_CALLS=str(crane_calls))
            result = subprocess.run(
                [str(script), str(old_values), str(new_values)],
                capture_output=True, text=True, env=env, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("diff  doqa/doqa-backend: 1.0.0-box -> 2.0.0-box", result.stdout)
            self.assertEqual(crane_calls.read_text().splitlines(), [
                "config registry.control.doqa.app/doqa/doqa-backend:1.0.0-box",
                "config registry.control.doqa.app/doqa/doqa-backend:2.0.0-box",
            ])

    def test_non_string_tag_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = Path(__file__).with_name("audit-doqa-images.sh")
            values = root / "values.yaml"
            values.write_text("".join(
                f"component{index}:\n  image:\n    repository: {repo}\n    tag: {1.0 if index == 0 else '1.0.0-box'}\n"
                for index, repo in enumerate(REPOSITORIES)
            ))
            bin_dir = root / "bin"
            bin_dir.mkdir()
            for executable in ("crane", "jq"):
                path = bin_dir / executable
                path.write_text("#!/bin/sh\nexit 99\n")
                path.chmod(0o755)
            env = dict(os.environ, PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
            result = subprocess.run(
                [str(script), str(values), str(values)],
                capture_output=True, text=True, env=env, check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("tag not found or invalid", result.stderr)


if __name__ == "__main__":
    unittest.main()
