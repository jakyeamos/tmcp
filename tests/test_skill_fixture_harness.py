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
APPLY = ROOT / "scripts" / "apply_skill_fixture_proposals.py"
GENERATE = ROOT / "scripts" / "generate_skill_fixture_proposals.py"


class SkillFixtureHarnessTests(unittest.TestCase):
    def test_scaffold_accepts_source_bound_admission_cases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "skills" / "alpha" / "SKILL.md"
            source.parent.mkdir(parents=True)
            source.write_text("# Alpha\nReturn a checked result.\n", encoding="utf-8")
            seed = root / "admission.json"
            seed.write_text(
                json.dumps({
                    "schema": "tmcp-individual-skill-admission-cases-v0.1",
                    "cases": [{
                        "source_path": "skills/alpha/SKILL.md",
                        "case_id": "alpha-admission",
                        "mode": "judgment",
                        "prompt": "Review this input.",
                        "bar": "The result cites concrete evidence.",
                        "smells": ["unsupported claim"],
                        "provenance": [{"line": 1, "excerpt": "# Alpha"}],
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
                    str(root / "skills"),
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
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["skills"][0]["readiness"], "ready")
            self.assertEqual(manifest["skills"][0]["cases"][0]["provenance"][0]["line"], 1)

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

    def test_apply_only_approved_hash_chained_proposals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_root = root / "skills"
            source = source_root / "alpha" / "SKILL.md"
            source.parent.mkdir(parents=True)
            original = "# Alpha\nReturn a checked result.\n"
            replacement = original + "\n## Verification\nRun the targeted check and report pass/fail.\n"
            source.write_text(original, encoding="utf-8")
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
            skill_id = manifest["skills"][0]["skill_id"]
            proposals = root / "proposals"
            proposals.mkdir()
            source_hash = __import__("hashlib").sha256(original.encode()).hexdigest()
            replacement_hash = __import__("hashlib").sha256(replacement.encode()).hexdigest()
            (proposals / f"{skill_id}.json").write_text(
                json.dumps({
                    "schema": "tmcp-skill-fixture-proposals-v0.1",
                    "skill_id": skill_id,
                    "source_sha256": source_hash,
                    "proposals": [
                        {
                            "proposal_id": "add-verification-gate",
                            "status": "approved",
                            "target": "SKILL.md",
                            "reason": "Replace vague quality language with an observable check.",
                            "before_sha256": source_hash,
                            "after_sha256": replacement_hash,
                            "replacement": replacement,
                        },
                        {
                            "proposal_id": "unreviewed-follow-up",
                            "status": "proposed",
                            "target": "SKILL.md",
                            "reason": "Not yet reviewed.",
                            "before_sha256": replacement_hash,
                            "after_sha256": source_hash,
                            "replacement": original,
                        },
                    ],
                }),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(APPLY),
                    str(manifest_path),
                    "--proposals-dir",
                    str(proposals),
                    "--skill-id",
                    skill_id,
                ],
                check=True,
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            report = json.loads(result.stdout)
            self.assertEqual(report["results"][0]["applied_proposal_ids"], ["add-verification-gate"])
            self.assertEqual(report["results"][0]["skipped_proposal_ids"], ["unreviewed-follow-up"])
            candidate = output / manifest["skills"][0]["versions"]["candidate"]["path"]
            self.assertEqual(candidate.read_text(encoding="utf-8"), replacement)
            subprocess.run([sys.executable, str(VALIDATE), str(manifest_path)], check=True, cwd=ROOT)
            prepared = subprocess.run(
                [
                    sys.executable,
                    str(PREPARE),
                    str(manifest_path),
                    "--skill-id",
                    skill_id,
                    "--output-dir",
                    str(root / "plans"),
                ],
                check=True,
                cwd=ROOT,
                env={**__import__("os").environ, "PYTHONPATH": str(ROOT)},
                capture_output=True,
                text=True,
            )
            prepared_report = json.loads(prepared.stdout)
            self.assertEqual(prepared_report["candidate_proposals"]["applied_proposal_ids"], ["add-verification-gate"])

    def test_generated_proposals_are_review_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "skills" / "alpha" / "SKILL.md"
            source.parent.mkdir(parents=True)
            source.write_text(
                "---\nname: Alpha\ndescription: Use for any task.\n---\n\n# Alpha\n\nMake sure everything works.\n",
                encoding="utf-8",
            )
            output = root / "fixtures"
            subprocess.run(
                [
                    sys.executable,
                    str(SCAFFOLD),
                    "--root",
                    str(root / "skills"),
                    "--output-dir",
                    str(output),
                ],
                check=True,
                cwd=ROOT,
            )
            manifest_path = output / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            proposals_dir = root / "proposals"
            generated = subprocess.run(
                [
                    sys.executable,
                    str(GENERATE),
                    str(manifest_path),
                    "--output-dir",
                    str(proposals_dir),
                ],
                check=True,
                cwd=ROOT,
                env={**__import__("os").environ, "PYTHONPATH": str(ROOT)},
                capture_output=True,
                text=True,
            )
            report = json.loads(generated.stdout)
            self.assertEqual(report["skills_with_proposals"], 1)
            bundle = json.loads((proposals_dir / f"{manifest['skills'][0]['skill_id']}.json").read_text(encoding="utf-8"))
            self.assertEqual(bundle["proposals"][0]["status"], "proposed")
            candidate = output / manifest["skills"][0]["versions"]["candidate"]["path"]
            self.assertEqual(candidate.read_text(encoding="utf-8"), source.read_text(encoding="utf-8"))
            experimental = subprocess.run(
                [
                    sys.executable,
                    str(APPLY),
                    str(manifest_path),
                    "--proposals-dir",
                    str(proposals_dir),
                    "--all",
                    "--include-proposed",
                ],
                check=True,
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            experiment_report = json.loads(experimental.stdout)
            self.assertEqual(experiment_report["results"][0]["application_mode"], "experimental")
            self.assertNotEqual(candidate.read_text(encoding="utf-8"), source.read_text(encoding="utf-8"))
            subprocess.run([sys.executable, str(VALIDATE), str(manifest_path)], check=True, cwd=ROOT)


if __name__ == "__main__":
    unittest.main()
