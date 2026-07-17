#!/usr/bin/env node

import { createHash, randomUUID } from "node:crypto";
import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn, spawnSync } from "node:child_process";

const VERSION_PATTERN = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/;
const STATE_SCHEMA = "tmcp-central-runtime-state-v0.1";
const PACKAGE_SCHEMA = "tmcp-runtime-package-v0.1";
const MARKETPLACE_PIN_MIN_RELEASE = "0.5.4";
const CODEX_MARKETPLACE_MARKER = ".codex-marketplace-install.json";
const CODEX_MARKETPLACE_SOURCE = "https://github.com/jakyeamos/tmcp.git";
const SKIP_NAMES = new Set([
  ".aios",
  ".codex",
  CODEX_MARKETPLACE_MARKER,
  ".git",
  ".planning",
  ".pre-cr",
  ".pytest_cache",
  ".quality-runner",
  ".ruff_cache",
  ".tmcp",
  "__pycache__",
  "node_modules",
]);

const HELP = `TMCP central runtime manager

Usage:
  node scripts/tmcp_runtime.mjs install --source <directory|archive> --runtime-home <path> [--sha256 <digest>] [--activate]
  node scripts/tmcp_runtime.mjs activate --version <release> --runtime-home <path>
  node scripts/tmcp_runtime.mjs rollback --runtime-home <path>
  node scripts/tmcp_runtime.mjs sync --runtime-home <path> [surface options]
  node scripts/tmcp_runtime.mjs status --runtime-home <path>
  node scripts/tmcp_runtime.mjs doctor --runtime-home <path> [--expected-version <release>] [surface options]
  node scripts/tmcp_runtime.mjs run --runtime-home <path> -- <tmcp launcher args>

Surface options:
  --legacy-alias <path>       Atomically point a compatibility alias at the active version.
  --codex-cache-root <path>   Add the active package at <root>/<codex plugin version>.
  --claude-cache-root <path>  Add the active package at <root>/<release version>.
  --codex-marketplace <path>  Replace a generated Codex marketplace snapshot.
  --claude-marketplace <path> Replace a generated Claude marketplace snapshot.
  --codex-config <path>       Check the native Codex marketplace ref.
  --claude-installed-record <path>
                              Check native Claude version, path, and source commit.
  --skill-path <path>         Check or install the canonical skills/tmcp/SKILL.md copy.

The runtime home defaults to TMCP_RUNTIME_HOME or ~/.tmcp/runtime. Installs are
immutable by release version. Activation changes an explicit state file and an
active symlink; the prior active version remains available for rollback.
`;

function parseArgs(argv) {
  const options = {};
  const passthrough = [];
  let passthroughMode = false;
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (passthroughMode) {
      passthrough.push(token);
      continue;
    }
    if (token === "--") {
      passthroughMode = true;
      continue;
    }
    if (!token.startsWith("--")) {
      if (!options._) options._ = [];
      options._.push(token);
      continue;
    }
    const key = token.slice(2).replaceAll("-", "_");
    const next = argv[index + 1];
    const value = next && !next.startsWith("--") ? next : true;
    if (value !== true) index += 1;
    if (options[key] === undefined) options[key] = value;
    else if (Array.isArray(options[key])) options[key].push(value);
    else options[key] = [options[key], value];
  }
  return { options, passthrough };
}

function optionString(options, key, fallback = undefined) {
  const value = options[key];
  if (value === undefined || value === true) return fallback;
  if (Array.isArray(value)) return String(value.at(-1));
  return String(value);
}

function optionBoolean(options, key) {
  const value = options[key];
  return value === true || value === "true";
}

function directoryLinkType() {
  return process.platform === "win32" ? "junction" : "dir";
}

function runtimeHome(options) {
  return path.resolve(
    optionString(options, "runtime_home", process.env.TMCP_RUNTIME_HOME ?? path.join(os.homedir(), ".tmcp", "runtime")),
  );
}

function jsonOutput(payload) {
  process.stdout.write(`${JSON.stringify(payload, null, 2)}\n`);
}

function fail(message) {
  throw new Error(message);
}

async function readJson(filePath) {
  try {
    return JSON.parse(await fs.readFile(filePath, "utf8"));
  } catch (error) {
    fail(`could not read JSON ${filePath}: ${error.message}`);
  }
}

async function readOptionalJson(filePath) {
  try {
    return JSON.parse(await fs.readFile(filePath, "utf8"));
  } catch (error) {
    if (error.code === "ENOENT") return null;
    fail(`could not read JSON ${filePath}: ${error.message}`);
  }
}

function releaseTuple(version) {
  return version.split(".").map((part) => Number(part));
}

function releaseAtLeast(version, minimum) {
  const actual = releaseTuple(version);
  const required = releaseTuple(minimum);
  for (let index = 0; index < required.length; index += 1) {
    if (actual[index] !== required[index]) return actual[index] > required[index];
  }
  return true;
}

async function writeJsonAtomic(filePath, value) {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  const temporary = `${filePath}.tmp-${process.pid}-${randomUUID()}`;
  await fs.writeFile(temporary, `${JSON.stringify(value, null, 2)}\n`, { mode: 0o600 });
  await fs.rename(temporary, filePath);
}

function shouldSkip(relativePath) {
  return relativePath.split(path.sep).some((part) => SKIP_NAMES.has(part));
}

async function listFiles(root, relativePath = "") {
  const directory = path.join(root, relativePath);
  const entries = (await fs.readdir(directory, { withFileTypes: true })).sort((left, right) => left.name.localeCompare(right.name));
  const files = [];
  for (const entry of entries) {
    const childRelative = path.join(relativePath, entry.name);
    if (shouldSkip(childRelative) || entry.name === "runtime-manifest.json") continue;
    const child = path.join(root, childRelative);
    if (entry.isSymbolicLink()) fail(`symlinks are not allowed in runtime packages: ${childRelative}`);
    if (entry.isDirectory()) files.push(...(await listFiles(root, childRelative)));
    else if (entry.isFile()) files.push(childRelative);
    else fail(`unsupported runtime package entry: ${childRelative}`);
  }
  return files;
}

async function treeDigest(root) {
  const files = (await listFiles(root)).sort();
  const hash = createHash("sha256");
  for (const relative of files) {
    hash.update(relative.replaceAll(path.sep, "/"));
    hash.update("\0");
    hash.update(await fs.readFile(path.join(root, relative)));
    hash.update("\n");
  }
  return { sha256: hash.digest("hex"), file_count: files.length };
}

async function copyTree(source, destination, relativePath = "") {
  const sourceDirectory = path.join(source, relativePath);
  const destinationDirectory = path.join(destination, relativePath);
  await fs.mkdir(destinationDirectory, { recursive: true });
  const entries = (await fs.readdir(sourceDirectory, { withFileTypes: true })).sort((left, right) => left.name.localeCompare(right.name));
  for (const entry of entries) {
    const childRelative = path.join(relativePath, entry.name);
    if (shouldSkip(childRelative) || entry.name === "runtime-manifest.json") continue;
    const sourceChild = path.join(source, childRelative);
    const destinationChild = path.join(destination, childRelative);
    if (entry.isSymbolicLink()) fail(`symlinks are not allowed in runtime packages: ${childRelative}`);
    if (entry.isDirectory()) await copyTree(source, destination, childRelative);
    else if (entry.isFile()) {
      await fs.mkdir(path.dirname(destinationChild), { recursive: true });
      await fs.copyFile(sourceChild, destinationChild);
      const mode = (await fs.stat(sourceChild)).mode & 0o777;
      await fs.chmod(destinationChild, mode);
    } else fail(`unsupported runtime package entry: ${childRelative}`);
  }
}

async function readPackageMetadata(packageRoot) {
  const claude = await readJson(path.join(packageRoot, ".claude-plugin", "plugin.json"));
  const codex = await readJson(path.join(packageRoot, ".codex-plugin", "plugin.json"));
  const release = String(claude.version ?? "");
  const codexPlugin = String(codex.version ?? "");
  if (!VERSION_PATTERN.test(release)) fail(`package release is not strict semver: ${release}`);
  if (!codexPlugin.startsWith(`${release}+`)) fail(`Codex plugin version ${codexPlugin} does not match release ${release}`);
  const marketplace = await readOptionalJson(path.join(packageRoot, ".claude-plugin", "marketplace.json"));
  let marketplaceRef = null;
  let marketplaceVersion = null;
  let marketplacePluginVersion = null;
  let marketplaceSource = null;
  if (marketplace && typeof marketplace === "object" && !Array.isArray(marketplace)) {
    marketplaceVersion = typeof marketplace.version === "string" ? marketplace.version : null;
    const plugins = Array.isArray(marketplace.plugins) ? marketplace.plugins : [];
    const plugin = plugins.find((candidate) => candidate && typeof candidate === "object" && candidate.name === codex.name);
    marketplacePluginVersion = plugin && typeof plugin.version === "string" ? plugin.version : null;
    const source = plugin && typeof plugin.source === "object" && !Array.isArray(plugin.source) ? plugin.source : null;
    marketplaceSource = source;
    marketplaceRef = source && typeof source.ref === "string" ? source.ref : null;
  }
  if (releaseAtLeast(release, MARKETPLACE_PIN_MIN_RELEASE)) {
    if (marketplaceVersion !== release || marketplacePluginVersion !== release) {
      fail(`Claude marketplace metadata must identify release ${release}`);
    }
    if (marketplaceSource?.source !== "github" || marketplaceSource.repo !== "jakyeamos/tmcp") {
      fail("Claude marketplace plugin source must be the canonical GitHub repository");
    }
    if (marketplaceRef !== `v${release}`) {
      fail(`Claude marketplace plugin source ref ${marketplaceRef ?? "<missing>"} must be pinned to v${release}`);
    }
  }
  const registrySource = await fs.readFile(path.join(packageRoot, "tmcp_runtime", "api", "registry.py"), "utf8");
  const registryMatch = registrySource.match(/release\s*=\s*["']([^"']+)["']/);
  if (!registryMatch || registryMatch[1] !== release) fail(`Python registry release does not match ${release}`);
  return { release, codex_plugin: codexPlugin, server_name: String(codex.name ?? ""), marketplace_ref: marketplaceRef };
}

function gitCommit(sourceRoot) {
  const result = spawnSync("git", ["-C", sourceRoot, "rev-parse", "HEAD"], { encoding: "utf8" });
  if (result.status === 0) return result.stdout.trim();
  return "uncommitted-directory";
}

async function fileDigest(filePath) {
  const hash = createHash("sha256");
  hash.update(await fs.readFile(filePath));
  return hash.digest("hex");
}

async function validateArchive(archivePath) {
  const result = spawnSync("tar", ["-tzf", archivePath], { encoding: "utf8" });
  if (result.status !== 0) fail(`could not inspect release archive: ${result.stderr || result.stdout}`);
  const entries = result.stdout.split("\n").map((entry) => entry.trim()).filter(Boolean);
  if (!entries.some((entry) => entry === "tmcp" || entry === "tmcp/" || entry.startsWith("tmcp/"))) fail("release archive must have a tmcp/ root");
  for (const entry of entries) {
    if (entry === "tmcp" || entry === "tmcp/") continue;
    if (!entry.startsWith("tmcp/") || entry.split("/").some((part) => part === ".." || part === "" && entry.at(-1) !== "/")) {
      fail(`unsafe release archive entry: ${entry}`);
    }
  }
}

async function materializeSource(source, staging, options) {
  const sourcePath = path.resolve(source);
  const stats = await fs.stat(sourcePath);
  if (stats.isDirectory()) {
    const digest = await treeDigest(sourcePath);
    return { root: sourcePath, source_kind: "directory", source_sha256: digest.sha256, source_commit: gitCommit(sourcePath) };
  }
  if (!stats.isFile() || !sourcePath.endsWith(".tar.gz")) fail(`source must be a directory or .tar.gz archive: ${sourcePath}`);
  const expected = optionString(options, "sha256");
  if (!expected) fail("archive installs require --sha256 so the package is pinned before extraction");
  const actual = await fileDigest(sourcePath);
  if (actual !== expected) fail(`archive SHA-256 mismatch: expected ${expected}, got ${actual}`);
  await validateArchive(sourcePath);
  const extractRoot = path.join(staging, "extract");
  await fs.mkdir(extractRoot, { recursive: true });
  const result = spawnSync("tar", ["-xzf", sourcePath, "-C", extractRoot], { encoding: "utf8" });
  if (result.status !== 0) fail(`could not extract release archive: ${result.stderr || result.stdout}`);
  const root = path.join(extractRoot, "tmcp");
  await fs.access(root);
  return { root, source_kind: "archive", source_sha256: actual, source_commit: optionString(options, "source_commit", "release-archive") };
}

async function loadState(home) {
  const statePath = path.join(home, "state.json");
  try {
    await fs.access(statePath);
  } catch (error) {
    if (error.code === "ENOENT") {
      return { schema: STATE_SCHEMA, active_version: null, previous_version: null, versions: {}, surfaces: {}, updated_at: null };
    }
    throw error;
  }
  const state = await readJson(statePath);
  if (state.schema !== STATE_SCHEMA) fail(`unsupported runtime state schema: ${state.schema}`);
  return state;
}

async function withLock(home, callback) {
  await fs.mkdir(home, { recursive: true });
  const lockPath = path.join(home, ".lock");
  let handle;
  try {
    handle = await fs.open(lockPath, "wx", 0o600);
  } catch (error) {
    if (error.code === "EEXIST") fail(`runtime is locked: ${lockPath}`);
    throw error;
  }
  try {
    return await callback();
  } finally {
    await handle.close();
    await fs.rm(lockPath, { force: true });
  }
}

async function validateInstalled(home, version) {
  const packageRoot = path.join(home, "versions", version);
  const metadata = await readPackageMetadata(packageRoot);
  const manifest = await readJson(path.join(packageRoot, "runtime-manifest.json"));
  if (manifest.schema !== PACKAGE_SCHEMA || manifest.release !== metadata.release || manifest.codex_plugin !== metadata.codex_plugin || (manifest.marketplace_ref !== undefined && manifest.marketplace_ref !== metadata.marketplace_ref)) {
    fail(`runtime manifest mismatch for ${version}`);
  }
  const digest = await treeDigest(packageRoot);
  if (digest.sha256 !== manifest.content_sha256) fail(`runtime content digest mismatch for ${version}`);
  const skillRoot = path.join(packageRoot, "skills");
  const skillDigest = await treeDigest(skillRoot);
  if (skillDigest.sha256 !== manifest.skills_sha256) fail(`runtime skill digest mismatch for ${version}`);
  const compatibilityLauncher = path.join(packageRoot, "scripts", "tmcp_launcher.mjs");
  await fs.access(compatibilityLauncher);
  const canonicalLauncher = path.join(packageRoot, "tmcp");
  let launcher = compatibilityLauncher;
  try {
    await fs.access(canonicalLauncher);
    launcher = canonicalLauncher;
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
  }
  return { packageRoot, metadata, manifest, digest, skillDigest, launcher };
}

async function removeExistingLink(target) {
  try {
    const stats = await fs.lstat(target);
    if (!stats.isSymbolicLink()) fail(`refusing to replace a non-link surface: ${target}`);
  } catch (error) {
    if (error.code === "ENOENT") return;
    throw error;
  }
  await fs.rm(target, { force: true, recursive: true });
}

async function replaceActiveLink(home, version) {
  const activePath = path.join(home, "active");
  if (process.platform === "win32") {
    await removeExistingLink(activePath);
    await fs.symlink(path.join("versions", version), activePath, directoryLinkType());
    return;
  }
  const temporary = `${activePath}.tmp-${process.pid}-${randomUUID()}`;
  await fs.rm(temporary, { force: true, recursive: true });
  await fs.symlink(path.join("versions", version), temporary, directoryLinkType());
  await fs.rename(temporary, activePath);
}

async function switchActive(home, state, version, reason) {
  const validated = await validateInstalled(home, version);
  const current = state.active_version;
  if (current !== version) {
    await replaceActiveLink(home, version);
    state.previous_version = current;
    state.active_version = version;
    state.updated_at = new Date().toISOString();
    state.last_switch = { from: current, to: version, reason, at: state.updated_at };
    await writeJsonAtomic(path.join(home, "state.json"), state);
  } else {
    await replaceActiveLink(home, version);
  }
  return validated;
}

async function install(options) {
  const home = runtimeHome(options);
  const source = optionString(options, "source");
  if (!source) fail("install requires --source");
  return withLock(home, async () => {
    const staging = await fs.mkdtemp(path.join(home, ".staging-"));
    try {
      const sourceInfo = await materializeSource(source, staging, options);
      const packageRoot = path.join(staging, "package");
      await copyTree(sourceInfo.root, packageRoot);
      const metadata = await readPackageMetadata(packageRoot);
      const digest = await treeDigest(packageRoot);
      const skillsDigest = await treeDigest(path.join(packageRoot, "skills"));
      const manifest = {
        schema: PACKAGE_SCHEMA,
        release: metadata.release,
        codex_plugin: metadata.codex_plugin,
        source_kind: sourceInfo.source_kind,
        source_sha256: sourceInfo.source_sha256,
        source_commit: optionString(options, "source_commit", sourceInfo.source_commit),
        marketplace_ref: metadata.marketplace_ref,
        content_sha256: digest.sha256,
        file_count: digest.file_count,
        skills_sha256: skillsDigest.sha256,
        installed_at: new Date().toISOString(),
        launcher: "tmcp",
      };
      const versionRoot = path.join(home, "versions", metadata.release);
      await fs.mkdir(path.dirname(versionRoot), { recursive: true });
      let installedManifest = manifest;
      try {
        const existing = await validateInstalled(home, metadata.release);
        if (existing.manifest.source_sha256 !== manifest.source_sha256 || existing.manifest.content_sha256 !== manifest.content_sha256) {
          fail(`immutable runtime version already exists with different content: ${metadata.release}`);
        }
        installedManifest = existing.manifest;
      } catch (error) {
        if (!error.message.startsWith("could not read JSON") && !error.message.includes("ENOENT")) throw error;
        await writeJsonAtomic(path.join(packageRoot, "runtime-manifest.json"), manifest);
        await fs.rename(packageRoot, versionRoot);
      }
      const state = await loadState(home);
      state.versions[metadata.release] = installedManifest;
      if (optionBoolean(options, "activate")) await switchActive(home, state, metadata.release, "install");
      else await writeJsonAtomic(path.join(home, "state.json"), { ...state, updated_at: new Date().toISOString() });
      return { schema: "tmcp-runtime-install-v0.1", ok: true, command: "install", runtime_home: home, version: metadata.release, manifest: installedManifest };
    } finally {
      await fs.rm(staging, { force: true, recursive: true });
    }
  });
}

async function activate(options, reason = "activate") {
  const home = runtimeHome(options);
  const version = optionString(options, "version");
  if (!version) fail("activate requires --version");
  return withLock(home, async () => activateLocked(home, version, reason));
}

async function rollback(options) {
  const home = runtimeHome(options);
  return withLock(home, async () => {
    const state = await loadState(home);
    if (!state.previous_version) fail("no previous runtime version is available for rollback");
    return activateLocked(home, state.previous_version, "rollback");
  });
}

async function activateLocked(home, version, reason) {
  const state = await loadState(home);
  const validated = await switchActive(home, state, version, reason);
  return { schema: "tmcp-runtime-activate-v0.1", ok: true, command: reason === "rollback" ? "rollback" : "activate", runtime_home: home, active_version: version, previous_version: state.previous_version, content_sha256: validated.manifest.content_sha256 };
}

async function realpathIfExists(target) {
  try {
    return await fs.realpath(target);
  } catch (error) {
    if (error.code === "ENOENT") return null;
    throw error;
  }
}

async function surfaceCheck(label, target, activeRoot, activeManifest) {
  if (!target) return { label, status: "skipped" };
  const resolved = await realpathIfExists(target);
  if (!resolved) return { label, status: "fail", detail: `missing surface: ${target}`, path: target };
  const activeResolved = await fs.realpath(activeRoot);
  if (resolved === activeResolved) return { label, status: "pass", mode: "active-symlink", path: target };
  const stats = await fs.stat(target);
  if (!stats.isDirectory()) return { label, status: "fail", detail: "surface is not a directory", path: target };
  if (label === "codex_marketplace") {
    const nativeCheck = await nativeCodexMarketplaceCheck(target, activeManifest);
    if (nativeCheck) return nativeCheck;
  }
  const digest = await treeDigest(target);
  if (digest.sha256 !== activeManifest.content_sha256) return { label, status: "fail", detail: `content digest ${digest.sha256} does not match active ${activeManifest.content_sha256}`, path: target };
  return { label, status: "pass", mode: "generated-copy", path: target };
}

async function nativeCodexMarketplaceCheck(target, activeManifest) {
  const gitStatus = gitSurfaceStatus(target);
  const targetRealpath = await realpathIfExists(target);
  const gitRoot = gitSurfaceRoot(target);
  if (gitStatus === null || !targetRealpath || !gitRoot || !pathsEquivalent(gitRoot, targetRealpath)) return null;
  let metadata;
  try {
    metadata = await readOptionalJson(path.join(target, CODEX_MARKETPLACE_MARKER));
  } catch (error) {
    return { label: "codex_marketplace", status: "fail", detail: error.message, path: target };
  }
  const expectedRef = activeManifest.marketplace_ref;
  const expectedRevision = activeManifest.source_commit;
  const issues = [];
  if (metadata) {
    if (metadata.source_type !== "git") issues.push(`source_type ${metadata.source_type ?? "<missing>"}`);
    if (metadata.source !== CODEX_MARKETPLACE_SOURCE) issues.push(`source ${metadata.source ?? "<missing>"}`);
    if (metadata.ref_name !== expectedRef) issues.push(`ref ${metadata.ref_name ?? "<missing>"}`);
    if (metadata.revision !== expectedRevision) issues.push(`revision ${metadata.revision ?? "<missing>"}`);
  }
  const remote = spawnSync("git", ["-C", target, "remote", "get-url", "origin"], { encoding: "utf8" });
  const remoteSource = remote.status === 0 ? remote.stdout.trim() : "<unavailable>";
  if (remoteSource !== CODEX_MARKETPLACE_SOURCE) issues.push(`remote ${remoteSource}`);
  const taggedRef = spawnSync("git", ["-C", target, "describe", "--tags", "--exact-match", "HEAD"], { encoding: "utf8" });
  const checkoutRef = taggedRef.status === 0 ? taggedRef.stdout.trim() : "<unavailable>";
  if (checkoutRef !== expectedRef) issues.push(`checkout ref ${checkoutRef}`);
  const dirty = nonMarkerGitSurfaceStatus(target);
  if (dirty) issues.push(`dirty Git checkout: ${dirty}`);
  const revision = spawnSync("git", ["-C", target, "rev-parse", "HEAD"], { encoding: "utf8" });
  const checkoutRevision = revision.status === 0 ? revision.stdout.trim() : "<unavailable>";
  if (/^[0-9a-f]{40}$/i.test(expectedRevision) && checkoutRevision !== expectedRevision) issues.push(`checkout revision ${checkoutRevision}`);
  if (issues.length > 0) {
    return { label: "codex_marketplace", status: "fail", detail: `native Codex marketplace provenance mismatch: ${issues.join(", ")}`, path: target };
  }
  return { label: "codex_marketplace", status: "pass", mode: "native-git", provenance: metadata ? "marker" : "git", ref: expectedRef, revision: expectedRevision, path: target };
}

async function skillCheck(target, activeRoot) {
  if (!target) return { label: "skill", status: "skipped" };
  const skillPath = (await fs.stat(target).catch(() => null))?.isDirectory() ? path.join(target, "SKILL.md") : target;
  const activeSkillPath = path.join(activeRoot, "skills", "tmcp", "SKILL.md");
  try {
    const expected = await fileDigest(activeSkillPath);
    const actual = await fileDigest(skillPath);
    return actual === expected ? { label: "skill", status: "pass", path: skillPath } : { label: "skill", status: "fail", detail: "skill copy does not match active runtime", path: skillPath };
  } catch (error) {
    return { label: "skill", status: "fail", detail: `missing skill copy: ${skillPath}`, path: skillPath };
  }
}

async function codexConfigCheck(target, active) {
  if (!target) return { id: "codex_config", status: "skipped" };
  try {
    const content = await fs.readFile(target, "utf8");
    const heading = "[marketplaces.tmcp]";
    const start = content.indexOf(heading);
    if (start < 0) return { id: "codex_config", status: "fail", detail: "native Codex config has no [marketplaces.tmcp] table", path: target };
    const remainder = content.slice(start + heading.length);
    const nextTable = remainder.search(/^\[/m);
    const block = remainder.slice(0, nextTable < 0 ? remainder.length : nextTable);
    const source = block.match(/^source\s*=\s*"([^"]+)"/m)?.[1];
    const ref = block.match(/^ref\s*=\s*"([^"]+)"/m)?.[1];
    const expectedRef = `v${active.metadata.release}`;
    if (source !== "https://github.com/jakyeamos/tmcp.git" || ref !== expectedRef) {
      return { id: "codex_config", status: "fail", detail: `expected canonical source and ref ${expectedRef}; got ${source ?? "<missing>"} ${ref ?? "<missing>"}`, path: target };
    }
    return { id: "codex_config", status: "pass", detail: expectedRef, path: target };
  } catch (error) {
    return { id: "codex_config", status: "fail", detail: `could not read native Codex config: ${error.message}`, path: target };
  }
}

async function claudeInstalledRecordCheck(target, active, expectedPluginPath) {
  if (!target) return { id: "claude_installed_record", status: "skipped" };
  try {
    const payload = await readJson(target);
    const entries = payload.plugins?.["tmcp@tmcp"];
    const installed = Array.isArray(entries) ? entries[0] : null;
    const expectedPath = expectedPluginPath ? path.resolve(expectedPluginPath) : null;
    const actualPath = installed && typeof installed.installPath === "string" ? path.resolve(installed.installPath) : null;
    const expectedCommit = active.manifest.source_commit;
    if (!installed || installed.version !== active.metadata.release || installed.gitCommitSha !== expectedCommit || (expectedPath && actualPath !== expectedPath)) {
      return { id: "claude_installed_record", status: "fail", detail: `expected version ${active.metadata.release}, commit ${expectedCommit}, path ${expectedPath ?? "<not checked>"}; got ${installed ? `${installed.version ?? "<missing>"}, ${installed.gitCommitSha ?? "<missing>"}, ${actualPath ?? "<missing>"}` : "<missing>"}`, path: target };
    }
    return { id: "claude_installed_record", status: "pass", detail: active.metadata.release, path: target };
  } catch (error) {
    return { id: "claude_installed_record", status: "fail", detail: `could not read native Claude installed record: ${error.message}`, path: target };
  }
}

async function doctor(options) {
  const home = runtimeHome(options);
  const state = await loadState(home);
  const checks = [];
  if (!state.active_version) checks.push({ id: "active_version", status: "fail", detail: "no active runtime version" });
  let active;
  if (state.active_version) {
    try {
      active = await validateInstalled(home, state.active_version);
      checks.push({ id: "active_runtime", status: "pass", detail: state.active_version });
      const activeLink = await realpathIfExists(path.join(home, "active"));
      const expectedLink = await fs.realpath(active.packageRoot);
      checks.push(activeLink === expectedLink ? { id: "active_pointer", status: "pass", detail: "active symlink matches state" } : { id: "active_pointer", status: "fail", detail: "active symlink does not match state" });
      const expectedVersion = optionString(options, "expected_version");
      if (expectedVersion) checks.push(expectedVersion === active.metadata.release ? { id: "expected_release", status: "pass", detail: expectedVersion } : { id: "expected_release", status: "fail", detail: `expected ${expectedVersion}, got ${active.metadata.release}` });
      const expectedCodex = optionString(options, "expected_codex_plugin");
      if (expectedCodex) checks.push(expectedCodex === active.metadata.codex_plugin ? { id: "expected_codex_plugin", status: "pass", detail: expectedCodex } : { id: "expected_codex_plugin", status: "fail", detail: `expected ${expectedCodex}, got ${active.metadata.codex_plugin}` });
    } catch (error) {
      checks.push({ id: "active_runtime", status: "fail", detail: error.message });
    }
  }
  if (active) {
    checks.push(await surfaceCheck("legacy_alias", optionString(options, "legacy_alias"), active.packageRoot, active.manifest));
    checks.push(await surfaceCheck("codex_marketplace", optionString(options, "codex_marketplace"), active.packageRoot, active.manifest));
    checks.push(await surfaceCheck("claude_marketplace", optionString(options, "claude_marketplace"), active.packageRoot, active.manifest));
    checks.push(await surfaceCheck("codex_plugin", optionString(options, "codex_plugin"), active.packageRoot, active.manifest));
    checks.push(await surfaceCheck("claude_plugin", optionString(options, "claude_plugin"), active.packageRoot, active.manifest));
    checks.push(await codexConfigCheck(optionString(options, "codex_config"), active));
    checks.push(await claudeInstalledRecordCheck(optionString(options, "claude_installed_record"), active, optionString(options, "claude_plugin")));
    checks.push(await skillCheck(optionString(options, "skill_path"), active.packageRoot));
  }
  const failed = checks.filter((check) => check.status === "fail");
  return { schema: "tmcp-runtime-doctor-v0.1", ok: failed.length === 0 && Boolean(state.active_version), command: "doctor", runtime_home: home, active_version: state.active_version, previous_version: state.previous_version, checks };
}

async function status(options) {
  const home = runtimeHome(options);
  const state = await loadState(home);
  const versions = [];
  for (const version of Object.keys(state.versions).sort()) {
    const packageRoot = path.join(home, "versions", version);
    const present = await realpathIfExists(packageRoot);
    versions.push({ version, present: Boolean(present), active: version === state.active_version, source_commit: state.versions[version]?.source_commit, source_sha256: state.versions[version]?.source_sha256, content_sha256: state.versions[version]?.content_sha256 });
  }
  return { schema: "tmcp-runtime-status-v0.1", ok: true, command: "status", runtime_home: home, active_version: state.active_version, previous_version: state.previous_version, active_path: state.active_version ? path.join(home, "active") : null, versions, surfaces: state.surfaces ?? {}, updated_at: state.updated_at };
}

async function replaceDirectory(destination, source, home, preserveEntries = []) {
  const temporary = `${destination}.staging-${process.pid}-${randomUUID()}`;
  await fs.rm(temporary, { force: true, recursive: true });
  await fs.mkdir(path.dirname(destination), { recursive: true });
  await copyTree(source, temporary);
  for (const relative of preserveEntries) {
    const existingPath = path.join(destination, relative);
    const preservedPath = path.join(temporary, relative);
    try {
      await fs.mkdir(path.dirname(preservedPath), { recursive: true });
      await fs.rename(existingPath, preservedPath);
    } catch (error) {
      if (error.code !== "ENOENT") throw error;
    }
  }
  const existing = await realpathIfExists(destination);
  let backup = null;
  if (existing) {
    backup = path.join(home, "backups", `${path.basename(destination)}-${Date.now()}`);
    await fs.mkdir(path.dirname(backup), { recursive: true });
    await fs.rename(destination, backup);
  }
  await fs.rename(temporary, destination);
  return backup;
}

function gitSurfaceStatus(destination) {
  const result = spawnSync("git", ["-C", destination, "status", "--porcelain"], { encoding: "utf8" });
  if (result.status !== 0) return null;
  return result.stdout.trim();
}

function gitSurfaceRoot(destination) {
  const result = spawnSync("git", ["-C", destination, "rev-parse", "--show-toplevel"], { encoding: "utf8" });
  if (result.status !== 0) return null;
  return result.stdout.trim();
}

function pathsEquivalent(left, right) {
  const normalizedLeft = path.normalize(path.resolve(left));
  const normalizedRight = path.normalize(path.resolve(right));
  return process.platform === "win32" ? normalizedLeft.toLowerCase() === normalizedRight.toLowerCase() : normalizedLeft === normalizedRight;
}

function nonMarkerGitSurfaceStatus(destination) {
  const status = gitSurfaceStatus(destination);
  if (!status) return status;
  return status
    .split("\n")
    .filter((line) => line.trim() && !line.trim().endsWith(CODEX_MARKETPLACE_MARKER))
    .join("\n");
}

async function assertSafeMarketplaceReplacement(destination) {
  const status = nonMarkerGitSurfaceStatus(destination);
  if (status) fail(`refusing to replace dirty marketplace surface: ${destination}`);
}

async function updateCodexMarketplaceMetadata(destination, active) {
  const metadataPath = path.join(destination, CODEX_MARKETPLACE_MARKER);
  try {
    const metadata = await readJson(metadataPath);
    metadata.ref_name = `v${active.metadata.release}`;
    metadata.revision = active.manifest.source_commit;
    await writeJsonAtomic(metadataPath, metadata);
  } catch (error) {
    if (!error.message.startsWith("could not read JSON") && error.code !== "ENOENT") throw error;
  }
}

async function replaceSymlink(destination, target) {
  if (process.platform === "win32") {
    await removeExistingLink(destination);
    await fs.mkdir(path.dirname(destination), { recursive: true });
    await fs.symlink(target, destination, directoryLinkType());
    return;
  }
  const temporary = `${destination}.tmp-${process.pid}-${randomUUID()}`;
  await fs.rm(temporary, { force: true, recursive: true });
  await fs.mkdir(path.dirname(destination), { recursive: true });
  await fs.symlink(target, temporary, directoryLinkType());
  await fs.rename(temporary, destination);
}

async function ensureGeneratedDirectory(destination, source, manifest, home) {
  const existing = await realpathIfExists(destination);
  if (!existing) {
    await replaceDirectory(destination, source, home);
    return { mode: "generated-copy", replaced: false };
  }
  const activeResolved = await fs.realpath(source);
  if (existing === activeResolved) return { mode: "active-symlink", replaced: false };
  const stats = await fs.stat(destination);
  if (stats.isDirectory()) {
    const digest = await treeDigest(destination);
    if (digest.sha256 === manifest.content_sha256) return { mode: "generated-copy", replaced: false };
  }
  await replaceDirectory(destination, source, home);
  return { mode: "generated-copy", replaced: true };
}

async function sync(options) {
  const home = runtimeHome(options);
  return withLock(home, async () => {
    const state = await loadState(home);
    if (!state.active_version) fail("sync requires an active runtime version");
    const active = await validateInstalled(home, state.active_version);
    const surfaces = {};
    const legacyAlias = optionString(options, "legacy_alias");
    if (legacyAlias) {
      await replaceSymlink(path.resolve(legacyAlias), path.join(home, "active"));
      surfaces.legacy_alias = { path: path.resolve(legacyAlias), mode: "active-symlink" };
    }
    const codexCacheRoot = optionString(options, "codex_cache_root");
    if (codexCacheRoot) {
      const destination = path.join(path.resolve(codexCacheRoot), active.metadata.codex_plugin);
      const result = await ensureGeneratedDirectory(destination, active.packageRoot, active.manifest, home);
      surfaces.codex_plugin = { path: destination, ...result, version: active.metadata.codex_plugin };
    }
    const claudeCacheRoot = optionString(options, "claude_cache_root");
    if (claudeCacheRoot) {
      const destination = path.join(path.resolve(claudeCacheRoot), active.metadata.release);
      const result = await ensureGeneratedDirectory(destination, active.packageRoot, active.manifest, home);
      surfaces.claude_plugin = { path: destination, ...result, version: active.metadata.release };
    }
    for (const [key, optionKey] of [["codex_marketplace", "codex_marketplace"], ["claude_marketplace", "claude_marketplace"]]) {
      const destination = optionString(options, optionKey);
      if (destination) {
        const resolvedDestination = path.resolve(destination);
        if (key === "codex_marketplace") {
          const native = await nativeCodexMarketplaceCheck(resolvedDestination, active.manifest);
          if (native?.status === "pass") {
            surfaces[key] = native;
            continue;
          }
          if (native?.status === "fail") fail(native.detail);
        }
        await assertSafeMarketplaceReplacement(resolvedDestination);
        const backup = await replaceDirectory(resolvedDestination, active.packageRoot, home, [".git", CODEX_MARKETPLACE_MARKER]);
        if (key === "codex_marketplace") await updateCodexMarketplaceMetadata(resolvedDestination, active);
        surfaces[key] = { path: resolvedDestination, mode: "generated-copy", backup };
      }
    }
    const skillPath = optionString(options, "skill_path");
    if (skillPath) {
      const destination = path.resolve(skillPath);
      const activeSkill = path.join(active.packageRoot, "skills", "tmcp", "SKILL.md");
      await fs.mkdir(path.dirname(destination), { recursive: true });
      await fs.copyFile(activeSkill, destination);
      surfaces.skill = { path: destination, mode: "generated-copy" };
    }
    state.surfaces = surfaces;
    state.updated_at = new Date().toISOString();
    await writeJsonAtomic(path.join(home, "state.json"), state);
    const diagnosis = await doctor({ ...options, runtime_home: home });
    return { schema: "tmcp-runtime-sync-v0.1", ok: diagnosis.ok, command: "sync", runtime_home: home, active_version: state.active_version, surfaces, doctor: diagnosis };
  });
}

async function runActive(options, passthrough) {
  const home = runtimeHome(options);
  const state = await loadState(home);
  if (!state.active_version) fail("run requires an active runtime version");
  const active = await validateInstalled(home, state.active_version);
  const child = spawn(process.execPath, [active.launcher, ...passthrough], {
    stdio: "inherit",
    env: { ...process.env, TMCP_RUNTIME_VERSION: active.metadata.release },
  });
  return new Promise((resolve, reject) => {
    child.on("error", reject);
    child.on("exit", (code, signal) => resolve(code ?? (signal ? 1 : 0)));
  });
}

async function main() {
  const { options, passthrough } = parseArgs(process.argv.slice(2));
  const command = options._?.[0] ?? "help";
  if (command === "help" || optionBoolean(options, "help")) {
    process.stdout.write(HELP);
    return 0;
  }
  if (command === "install") jsonOutput(await install(options));
  else if (command === "activate") jsonOutput(await activate(options));
  else if (command === "rollback") jsonOutput(await rollback(options));
  else if (command === "sync") jsonOutput(await sync(options));
  else if (command === "status") jsonOutput(await status(options));
  else if (command === "doctor") jsonOutput(await doctor(options));
  else if (command === "run") return runActive(options, passthrough);
  else fail(`unknown command: ${command}`);
  return 0;
}

main().then((code) => {
  if (typeof code === "number") process.exitCode = code;
}).catch((error) => {
  jsonOutput({ schema: "tmcp-runtime-error-v0.1", ok: false, error: error.message });
  process.exitCode = 1;
});
