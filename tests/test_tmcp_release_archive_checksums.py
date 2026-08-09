from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_release_archive_module():
    path = ROOT / "scripts" / "tmcp_release_archive.py"
    spec = importlib.util.spec_from_file_location("tmcp_release_archive_checks", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load release archive module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReleaseArchiveChecksumTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.package = load_release_archive_module()

    def test_documented_checksum_formats_are_allowed(self) -> None:
        checksum = "0123456789abcdef" * 4
        allowed = (
            f"sha256 digest: {checksum}\n",
            f'{{"sha256": "{checksum}"}}\n',
            f'"skills/example/SKILL.md": "{checksum}"\n',
            f"- Exact base commit: `{checksum[:40]}`\n",
            f"Base: current HEAD `{checksum[:40]}`; sealed declared base `{checksum[:40]}`\n",
            f"The handoff hash is\n`{checksum}`\n",
            f"| `docs/example.md` | `{checksum}` |\n",
        )
        for content in allowed:
            with self.subTest(content=content):
                self.package.scan_release_content("README.md", content.encode())

    def test_undocumented_digest_remains_rejected(self) -> None:
        checksum = "0123456789abcdef" * 4
        with self.assertRaisesRegex(
            self.package.ReleasePackageError,
            "long_high_entropy",
        ):
            self.package.scan_release_content(
                "README.md", f"hash note {checksum}\n".encode()
            )


if __name__ == "__main__":
    unittest.main()
