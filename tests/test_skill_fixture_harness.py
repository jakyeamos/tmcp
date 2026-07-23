from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCAFFOLD = ROOT / "scripts" / "scaffold_skill_fixtures.py"
VALIDATE = ROOT / "scripts" / "validate_skill_fixtures.py"
PREPARE = ROOT / "scripts" / "prepare_skill_fixture_eval.py"


class SkillFixtureHarnessTests(unittest.TestCase):
    def test_scaffold_validate_and_prepare_versions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_root = root / "skills"
            skill_a = source_root / "alpha" / "SKILL.md"
            skill_b = source_root / "beta" / "SKILL.md"
            skill_a.parent.mkdir(parents=True)
            skill_b.parent.mkdir(parents=True)
            skill_a.write_text("# Alpha\nReturn a checked result.\n", encoding="utf-8")
            skill_b.write_text("# Beta\nDo the work.\n", encoding="utf-8")
            seed = root / "seed.json"
            seed.write_text(
                json.dumps({
                    "schema": "tmcp-skill-fixture-seed-cases-v0.1",
                    "cases": [{
                        "source_path": "skills/alpha/SKILL.md",
                        "case_id": "alpha-case",
                        "mode": "judgment",
                        "prompt": "Review this input.",
                        "bar": "The result is defensible and cites concrete evidence.",
                        "smells": ["unsupported claim"],
                        "observables": ["evidence is cited"],
                    }],
                }),
                encoding="utf-8",
            )
            output = root / "fixtures"
            subprocess.run(
                [
                    sys.executable,
                    str(SCAFFOLD),
                    "--root",
                    str(source_root),
                    "--seed-cases",
                    str(seed),
                    "--project-root",
                    str(root),
                    "--output-dir",
                    str(output),
                ],
                check=True,
                cwd=ROOT,
            )
            manifest_path = output / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(len(manifest["skills"]), 2)
            self.assertEqual(sum(item["readiness"] == "ready" for item in manifest["skills"]), 1)
            subprocess.run([sys.executable, str(VALIDATE), str(manifest_path)], check=True, cwd=ROOT)
            alpha = next(item for item in manifest["skills"] if item["skill_id"].endswith("alpha"))
            candidate = output / alpha["versions"]["candidate"]["path"]
            candidate.write_text(candidate.read_text(encoding="utf-8") + "\n# Candidate revision\n", encoding="utf-8")
            record = ROOT / "scripts" / "record_skill_fixture_candidate.py"
            subprocess.run(
                [sys.executable, str(record), str(manifest_path), "--skill-id", alpha["skill_id"]],
                check=True,
                cwd=ROOT,
            )
            subprocess.run([sys.executable, str(VALIDATE), str(manifest_path)], check=True, cwd=ROOT)
            plans = root / "plans"
            subprocess.run(
                [
                    sys.executable,
                    str(PREPARE),
                    str(manifest_path),
                    "--skill-id",
                    alpha["skill_id"],
                    "--output-dir",
                    str(plans),
                ],
                check=True,
                cwd=ROOT,
                env={**__import__("os").environ, "PYTHONPATH": str(ROOT)},
            )
            self.assertTrue((plans / f"{alpha['skill_id']}--original.json").is_file())
            self.assertTrue((plans / f"{alpha['skill_id']}--candidate.json").is_file())


if __name__ == "__main__":
    unittest.main()
