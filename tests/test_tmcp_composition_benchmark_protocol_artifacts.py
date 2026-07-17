from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tmcp_runtime.storage.artifacts import (
    ArtifactStorageError,
    AtomicArtifactStore,
    artifact_persistence_available,
)


class CompositionBenchmarkProtocolArtifactTests(unittest.TestCase):
    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_tree_bundle_rejects_escape_and_nonempty_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "benchmark"
            with self.assertRaises(ArtifactStorageError):
                AtomicArtifactStore.write_tree_bundle(
                    output_dir,
                    {"fixtures/../outside.txt": "unsafe"},
                )
            AtomicArtifactStore.write_tree_bundle(
                output_dir,
                {"fixtures/one/skills/example/SKILL.md": "safe"},
            )
            self.assertEqual(
                (
                    output_dir / "fixtures" / "one" / "skills" / "example" / "SKILL.md"
                ).read_text(encoding="utf-8"),
                "safe",
            )
            with self.assertRaises(ArtifactStorageError):
                AtomicArtifactStore.write_tree_bundle(
                    output_dir,
                    {"fixtures/two/skills/example/SKILL.md": "new"},
                )
