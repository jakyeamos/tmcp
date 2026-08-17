from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class SkillFixtureCodexRunnerTests(unittest.TestCase):
    def test_prompt_is_passed_on_stdin_without_shell_interpolation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            fake_codex = root / "fake-codex"
            marker = root / "SHOULD_NOT_EXIST"
            fake_codex.write_text(
                "#!/bin/sh\n"
                "while [ $# -gt 0 ]; do\n"
                '  if [ "$1" = "-o" ]; then shift; output="$1"; fi\n'
                "  shift\n"
                "done\n"
                'cat > "$output"\n'
                "echo 'session id: fake-session'\n",
                encoding="utf-8",
            )
            fake_codex.chmod(fake_codex.stat().st_mode | stat.S_IXUSR)
            prompt_file = root / "prompt.txt"
            prompt = "literal `teh` $(touch SHOULD_NOT_EXIST)\n"
            prompt_file.write_text(prompt, encoding="utf-8")
            output_file = root / "last-message.txt"
            command = [
                sys.executable,
                "scripts/run_skill_fixture_codex.py",
                "--prompt-file",
                str(prompt_file),
                "--output-last-message",
                str(output_file),
                "--cwd",
                str(root),
                "--codex",
                str(fake_codex),
            ]
            completed = subprocess.run(
                command,
                cwd=Path(__file__).parents[1],
                text=True,
                capture_output=True,
                check=False,
                env={**os.environ, "PATH": os.environ["PATH"]},
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            report = json.loads(completed.stdout)
            self.assertEqual(output_file.read_text(encoding="utf-8"), prompt)
            self.assertFalse(marker.exists())
            self.assertEqual(report["session_id"], "fake-session")
            self.assertFalse(report["shell_interpolation"])
            self.assertEqual(report["exit_code"], 0)


if __name__ == "__main__":
    unittest.main()
