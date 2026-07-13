"""Artifact-bundle persistence over explicit redaction and storage callbacks."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from tmcp_runtime.services.artifact_plans import ArtifactPlan


ArtifactPath = str | Path
JsonRedactor = Callable[[dict[str, Any]], dict[str, Any]]
TextRedactor = Callable[[str], str]
PathPresenter = Callable[[ArtifactPath], str]
BundleWriter = Callable[
    [Path, Mapping[str, Any], Mapping[str, str]], Mapping[str, ArtifactPath]
]


class ExplicitArtifactWriter(Protocol):
    """The small write surface needed for non-bundle artifact persistence."""

    def write_json(self, name: str, payload: Any) -> ArtifactPath:
        """Write one JSON artifact and return its path."""

    def write_text(self, name: str, content: str) -> ArtifactPath:
        """Write one text artifact and return its path."""


StoreOpener = Callable[[Path], ExplicitArtifactWriter]


@dataclass(frozen=True)
class ArtifactPersistenceContext:
    """Adapter-owned capabilities for safe artifact persistence."""

    redact_json: JsonRedactor
    redact_text: TextRedactor
    present_path: PathPresenter
    write_bundle: BundleWriter
    open_store: StoreOpener


class ArtifactPersistenceService:
    """Persist safe artifact bundles without owning filesystem or redaction policy."""

    def __init__(self, context: ArtifactPersistenceContext) -> None:
        self._context = context

    def persist(
        self,
        output_dir: Path,
        *,
        json_artifacts: Mapping[str, Any],
        text_artifacts: Mapping[str, str],
        fresh_bundle: bool,
    ) -> dict[str, str]:
        """Redact and persist artifacts through the adapter-provided capabilities."""

        if set(json_artifacts).intersection(text_artifacts):
            raise ValueError("Artifact names must be unique.")
        safe_json = self._context.redact_json(dict(json_artifacts))
        safe_text = {
            name: self._context.redact_text(str(content))
            for name, content in text_artifacts.items()
        }
        if fresh_bundle:
            paths = self._context.write_bundle(
                output_dir,
                safe_json,
                safe_text,
            )
        else:
            store = self._context.open_store(output_dir)
            paths: dict[str, ArtifactPath] = {
                name: store.write_json(name, payload)
                for name, payload in safe_json.items()
            }
            paths.update(
                {
                    name: store.write_text(name, content)
                    for name, content in safe_text.items()
                }
            )
        return {
            name: self._context.present_path(path) for name, path in paths.items()
        }

    def persist_plan(
        self,
        output_dir: Path,
        plan: ArtifactPlan,
        *,
        fresh_bundle: bool,
    ) -> dict[str, str]:
        """Persist a manifest and return only its declared response aliases."""

        paths = self.persist(
            output_dir,
            json_artifacts=plan.json_artifacts,
            text_artifacts=plan.text_artifacts,
            fresh_bundle=fresh_bundle,
        )
        return {alias: paths[name] for alias, name in plan.path_aliases.items()}
