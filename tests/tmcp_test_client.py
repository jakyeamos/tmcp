"""Hermetic black-box clients shared by TMCP transport contract tests."""

from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from scripts.tmcp_mcp_framing import encode_message, read_message


PLUGIN_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class ProcessResult:
    """A completed launcher invocation with decoded JSON when available."""

    returncode: int
    stdout: str
    stderr: str

    def json(self) -> dict[str, object]:
        payload = json.loads(self.stdout)
        if not isinstance(payload, dict):
            raise RuntimeError("TMCP CLI output must be a JSON object")
        return payload


class TestWorkspace:
    """An isolated project, TMCP home, and subprocess environment for one test."""

    def __init__(self, plugin_root: Path = PLUGIN_ROOT) -> None:
        self.plugin_root = plugin_root
        self._temporary: tempfile.TemporaryDirectory[str] | None = None
        self.root: Path | None = None
        self.project: Path | None = None
        self.source: Path | None = None
        self.output: Path | None = None
        self.tmcp_home: Path | None = None

    def __enter__(self) -> TestWorkspace:
        self._temporary = tempfile.TemporaryDirectory(prefix="tmcp-test-")
        self.root = Path(self._temporary.name)
        self.project = self.root / "project"
        self.source = self.root / "source"
        self.output = self.root / "output"
        self.tmcp_home = self.root / "tmcp-home"
        for path in (self.project, self.source, self.output, self.tmcp_home):
            path.mkdir()
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        if self._temporary is not None:
            self._temporary.cleanup()
        self._temporary = None

    def environment(self) -> dict[str, str]:
        if self.root is None or self.tmcp_home is None:
            raise RuntimeError("TestWorkspace must be entered before use")
        environment = os.environ.copy()
        home = self.root / "home"
        home.mkdir(exist_ok=True)
        environment["HOME"] = str(home)
        environment["TMCP_HOME"] = str(self.tmcp_home)
        environment["AIOS_ROOT"] = str(self.root / "missing-aios")
        environment.pop("TMCP_ENABLE_DEPRECATED_AIOS_ADAPTER", None)
        assert "TMCP_ENABLE_DEPRECATED_AIOS_ADAPTER" not in environment
        environment.pop("XDG_CONFIG_HOME", None)
        environment.pop("XDG_CACHE_HOME", None)
        return environment

    def run_cli(self, arguments: Sequence[str]) -> ProcessResult:
        completed = subprocess.run(
            ["node", "scripts/tmcp_launcher.mjs", *arguments],
            cwd=self.plugin_root,
            env=self.environment(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=30,
        )
        return ProcessResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    def run_mcp(self, requests: Sequence[dict[str, object]]) -> list[dict[str, object]]:
        raw = b"".join(encode_message(request) for request in requests)
        completed = subprocess.run(
            ["node", "scripts/tmcp_launcher.mjs"],
            cwd=self.plugin_root,
            env=self.environment(),
            input=raw,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=30,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.decode("utf-8", errors="replace")
            raise RuntimeError(f"TMCP MCP launcher failed: {stderr}")
        stream = io.BytesIO(completed.stdout)
        responses: list[dict[str, object]] = []
        while stream.tell() < len(completed.stdout):
            response = read_message(stream)
            if response is None:
                break
            if not isinstance(response, dict):
                raise RuntimeError("TMCP MCP response must be a JSON object")
            responses.append(cast(dict[str, object], response))
        return responses


def run_mcp_requests(
    requests: Sequence[dict[str, object]], plugin_root: Path = PLUGIN_ROOT
) -> list[dict[str, object]]:
    """Run requests against a fresh, hermetic launcher process."""

    with TestWorkspace(plugin_root) as workspace:
        return workspace.run_mcp(requests)
