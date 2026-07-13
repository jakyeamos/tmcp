from __future__ import annotations

import ast
import inspect
import unittest
from pathlib import Path

import tmcp_runtime.services.artifact_persistence as persistence_service
from tmcp_runtime.services.artifact_persistence import (
    ArtifactPersistenceContext,
    ArtifactPersistenceService,
)
from tmcp_runtime.services.artifact_plans import ArtifactPlan


class _Store:
    def __init__(self) -> None:
        self.json_writes: list[tuple[str, object]] = []
        self.text_writes: list[tuple[str, str]] = []

    def write_json(self, name: str, payload: object) -> Path:
        self.json_writes.append((name, payload))
        return Path("/output") / name

    def write_text(self, name: str, content: str) -> Path:
        self.text_writes.append((name, content))
        return Path("/output") / name


class ArtifactPersistenceServiceTests(unittest.TestCase):
    def test_fresh_bundle_uses_redacted_content_and_bundle_callback(self) -> None:
        bundle_calls: list[tuple[Path, dict[str, object], dict[str, str]]] = []

        def redact_json(payload: dict[str, object]) -> dict[str, object]:
            artifact = payload["result.json"]
            assert isinstance(artifact, dict)
            return {"result.json": {"safe": artifact["secret"]}}

        def write_bundle(
            output_dir: Path,
            json_artifacts: dict[str, object],
            text_artifacts: dict[str, str],
        ) -> dict[str, Path]:
            bundle_calls.append((output_dir, json_artifacts, text_artifacts))
            return {
                name: output_dir / name
                for name in (*json_artifacts, *text_artifacts)
            }

        service = ArtifactPersistenceService(
            ArtifactPersistenceContext(
                redact_json=redact_json,
                redact_text=lambda content: f"safe:{content}",
                present_path=lambda path: f"shown:{Path(path).as_posix()}",
                write_bundle=write_bundle,
                open_store=lambda _output_dir: _Store(),
            )
        )

        result = service.persist(
            Path("/bundle"),
            json_artifacts={"result.json": {"secret": "value"}},
            text_artifacts={"notes.md": "note"},
            fresh_bundle=True,
        )

        self.assertEqual(
            bundle_calls,
            [
                (
                    Path("/bundle"),
                    {"result.json": {"safe": "value"}},
                    {"notes.md": "safe:note"},
                )
            ],
        )
        self.assertEqual(
            result,
            {
                "result.json": "shown:/bundle/result.json",
                "notes.md": "shown:/bundle/notes.md",
            },
        )

    def test_existing_output_uses_explicit_store_callback(self) -> None:
        store = _Store()
        service = ArtifactPersistenceService(
            ArtifactPersistenceContext(
                redact_json=lambda payload: payload,
                redact_text=lambda content: content.upper(),
                present_path=lambda path: Path(path).as_posix(),
                write_bundle=lambda *_args: self.fail("bundle callback was used"),
                open_store=lambda output_dir: store,
            )
        )

        result = service.persist(
            Path("/output"),
            json_artifacts={"result.json": {"ok": True}},
            text_artifacts={"notes.md": "note"},
            fresh_bundle=False,
        )

        self.assertEqual(store.json_writes, [("result.json", {"ok": True})])
        self.assertEqual(store.text_writes, [("notes.md", "NOTE")])
        self.assertEqual(
            result,
            {
                "result.json": "/output/result.json",
                "notes.md": "/output/notes.md",
            },
        )

    def test_plan_returns_declared_aliases_only(self) -> None:
        service = ArtifactPersistenceService(
            ArtifactPersistenceContext(
                redact_json=lambda payload: payload,
                redact_text=lambda content: content,
                present_path=lambda path: Path(path).as_posix(),
                write_bundle=lambda output_dir, json_artifacts, text_artifacts: {
                    name: output_dir / name
                    for name in (*json_artifacts, *text_artifacts)
                },
                open_store=lambda _output_dir: _Store(),
            )
        )
        plan = ArtifactPlan(
            json_artifacts={"report.json": {"ok": True}},
            text_artifacts={"report.md": "ok"},
            path_aliases={"report_json": "report.json"},
        )

        self.assertEqual(
            service.persist_plan(Path("/bundle"), plan, fresh_bundle=True),
            {"report_json": "/bundle/report.json"},
        )

    def test_duplicate_names_are_rejected_before_callbacks(self) -> None:
        service = ArtifactPersistenceService(
            ArtifactPersistenceContext(
                redact_json=lambda payload: payload,
                redact_text=lambda content: content,
                present_path=lambda path: Path(path).as_posix(),
                write_bundle=lambda *_args: self.fail("bundle callback was used"),
                open_store=lambda _output_dir: self.fail("store callback was used"),
            )
        )

        with self.assertRaisesRegex(ValueError, "unique"):
            service.persist(
                Path("/bundle"),
                json_artifacts={"same": {}},
                text_artifacts={"same": ""},
                fresh_bundle=True,
            )

    def test_service_has_no_storage_or_adapter_imports(self) -> None:
        source_path = Path(inspect.getfile(persistence_service))
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        imported_modules = {
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        imported_modules.update(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        forbidden_prefixes = (
            "os",
            "shutil",
            "subprocess",
            "scripts",
            "tmcp_runtime.safety",
            "tmcp_runtime.storage",
        )
        self.assertTrue(
            all(
                not module.startswith(prefix)
                for module in imported_modules
                for prefix in forbidden_prefixes
            )
        )


if __name__ == "__main__":
    unittest.main()
