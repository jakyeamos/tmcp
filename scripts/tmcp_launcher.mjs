#!/usr/bin/env node
import { spawn, spawnSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const pluginRoot = resolve(scriptDir, "..");
const defaultServerPath = resolve(scriptDir, "tmcp_mcp_server.py");

export function pythonCandidates(env = process.env, platform = process.platform) {
  const configured = env.TMCP_PYTHON?.trim();
  const candidates = [];
  if (configured) {
    candidates.push({ command: configured, args: [], source: "TMCP_PYTHON" });
  }

  if (platform === "win32") {
    candidates.push(
      { command: "py", args: ["-3"], source: "windows-python-launcher" },
      { command: "python", args: [], source: "python" },
      { command: "python3", args: [], source: "python3" },
    );
  } else {
    candidates.push(
      { command: "python3", args: [], source: "python3" },
      { command: "python", args: [], source: "python" },
    );
  }

  return candidates;
}

export function selectPythonCandidate(env = process.env, platform = process.platform) {
  for (const candidate of pythonCandidates(env, platform)) {
    const probe = spawnSync(candidate.command, [...candidate.args, "--version"], {
      env,
      stdio: "ignore",
    });
    if (!probe.error && probe.status === 0) {
      return candidate;
    }
  }
  return null;
}

export function buildServerCommand(
  serverPath = defaultServerPath,
  env = process.env,
  platform = process.platform,
) {
  const python = selectPythonCandidate(env, platform);
  if (!python) {
    throw new Error(
      "No Python runtime found. Install Python 3, or set TMCP_PYTHON to an explicit Python executable.",
    );
  }
  return {
    command: python.command,
    args: [...python.args, serverPath],
    source: python.source,
  };
}

function main() {
  let server;
  try {
    server = buildServerCommand();
  } catch (error) {
    console.error(`TMCP launcher error: ${error.message}`);
    process.exit(1);
  }

  const child = spawn(server.command, [...server.args, ...process.argv.slice(2)], {
    cwd: pluginRoot,
    env: process.env,
    stdio: "inherit",
  });

  child.on("error", (error) => {
    console.error(`TMCP launcher failed to start Python: ${error.message}`);
    process.exit(1);
  });

  child.on("exit", (code, signal) => {
    if (signal) {
      process.kill(process.pid, signal);
      return;
    }
    process.exit(code ?? 0);
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main();
}
