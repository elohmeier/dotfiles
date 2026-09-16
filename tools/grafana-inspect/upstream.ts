import { spawnSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { DashboardDataError } from "./errors.js";
import { createRequire } from "node:module";
const corepack = path.join(path.dirname(createRequire(import.meta.url).resolve("corepack/package.json")), "dist/corepack.js");
const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
export const release = JSON.parse(fs.readFileSync(path.join(scriptDirectory, "../grafana-version.json"), "utf8"));
export function resolveGrafanaSource(configuredSource: string): {
  path: string;
  version: string;
  commit: string;
  dirty: boolean;
} {
  if (configuredSource) {
    const inspected = inspectGrafanaSource(configuredSource);
    if (inspected.commit !== release.commit || inspected.dirty) throw new DashboardDataError("Grafana source must match the clean pinned release commit");
    return inspected;
  }

  const pinnedVersion = pinnedGrafanaVersion();
  const cacheBase = process.env.XDG_CACHE_HOME
    ? path.resolve(process.env.XDG_CACHE_HOME)
    : path.join(os.homedir(), ".cache");
  const source = path.join(cacheBase, "grafana-tools", `grafana-${release.commit}`);
  if (!fs.existsSync(path.join(source, "package.json"))) {
    bootstrapGrafanaSource(source, pinnedVersion);
  }
  ensureGrafanaFrontendDependencies(source);
  const inspected = inspectGrafanaSource(source);
  if (normalizedVersion(inspected.version) !== normalizedVersion(pinnedVersion) || inspected.commit !== release.commit || inspected.dirty) {
    throw new DashboardDataError(
      `cached Grafana source ${source} is ${inspected.version}, expected pinned release ${pinnedVersion}`,
    );
  }
  return inspected;
}

function pinnedGrafanaVersion(): string { return release.version; }

function bootstrapGrafanaSource(destination: string, version: string): void {
  const parent = path.dirname(destination);
  const temporary = `${destination}.partial-${process.pid}`;
  fs.mkdirSync(parent, { recursive: true });
  if (fs.existsSync(temporary)) {
    fs.rmSync(temporary, { recursive: true, force: true });
  }
  console.error(`Bootstrapping Grafana ${version} editor runtime in ${destination}`);
  try {
    runChecked(
      "git",
      [
        "clone",
        "--depth",
        "1",
        "--filter=blob:none",
        "--single-branch",
        "--branch",
        `v${version}`,
        "https://github.com/grafana/grafana.git",
        temporary,
      ],
      process.cwd(),
      "could not download the pinned Grafana source",
    );
    if (gitOutput(temporary, ["rev-parse", "HEAD"]) !== release.commit) throw new DashboardDataError("downloaded Grafana tag does not match the pinned commit");
    fs.renameSync(temporary, destination);
  } finally {
    if (fs.existsSync(temporary)) {
      fs.rmSync(temporary, { recursive: true, force: true });
    }
  }
}

function ensureGrafanaFrontendDependencies(source: string): void {
  if (fs.existsSync(path.join(source, "node_modules", "jest"))) {
    return;
  }
  console.error(`Installing Grafana frontend dependencies in ${source}`);
  runChecked(process.execPath, [corepack, "yarn", "install", "--immutable"], source, "could not install the pinned Grafana frontend dependencies");
}

function runChecked(command: string, args: string[], cwd: string, message: string): void {
  const result = spawnSync(command, args, { cwd, stdio: "inherit" });
  if (result.error) {
    throw new DashboardDataError(`${message}: ${result.error.message}`);
  }
  if (result.status !== 0) {
    throw new DashboardDataError(`${message} (exit ${result.status ?? "unknown"})`);
  }
}

function inspectGrafanaSource(value: string): {
  path: string;
  version: string;
  commit: string;
  dirty: boolean;
} {
  const source = path.resolve(value);
  const packagePath = path.join(source, "package.json");
  const jestConfigPath = path.join(source, "jest.config.js");
  if (!fs.existsSync(packagePath) || !fs.existsSync(jestConfigPath)) {
    throw new DashboardDataError(`${source} is not a Grafana source checkout`);
  }
  if (!fs.existsSync(path.join(source, "node_modules", "jest"))) {
    throw new DashboardDataError(
      `Grafana frontend dependencies are missing; run 'corepack yarn install --immutable' in ${source}`,
    );
  }
  const packageJson = JSON.parse(fs.readFileSync(packagePath, "utf8")) as { version?: string };
  const version = packageJson.version || "";
  if (!version) {
    throw new DashboardDataError(`Grafana source package.json has no version: ${packagePath}`);
  }
  const commit = gitOutput(source, ["rev-parse", "HEAD"]);
  const dirty = gitOutput(source, ["status", "--porcelain", "--untracked-files=no"]).length > 0;
  return { path: source, version, commit, dirty };
}

function gitOutput(cwd: string, args: string[]): string {
  const result = spawnSync("git", args, { cwd, encoding: "utf8" });
  if (result.status !== 0) {
    throw new DashboardDataError(result.stderr.trim() || `git ${args.join(" ")} failed in ${cwd}`);
  }
  return result.stdout.trim();
}

function normalizedVersion(value: string): string {
  return value.trim().replace(/\+.*$/, "");
}

export function runHarness(source: string, input: unknown, mode = "diagnostics"): any {
  const temporaryDirectory = fs.mkdtempSync(path.join(os.tmpdir(), "grafana-editor-diagnostics-"));
  const inputPath = path.join(temporaryDirectory, "input.json");
  const outputPath = path.join(temporaryDirectory, "output.json");
  fs.writeFileSync(inputPath, `${JSON.stringify(input, null, 2)}\n`, "utf8");

  try {
    const result = spawnSync(process.execPath, [corepack, "yarn", "jest", "--runInBand", "--silent", "--watchAll=false", "--config", path.join(scriptDirectory, "grafana_editor_diagnostics_jest.config.cjs")], {
      cwd: source,
      encoding: "utf8",
      env: {
        ...process.env,
        GRAFANA_SOURCE: source,
        GRAFANA_HARNESS_MODE: mode,
        GRAFANA_EDITOR_DIAGNOSTICS_INPUT: inputPath,
        GRAFANA_EDITOR_DIAGNOSTICS_OUTPUT: outputPath,
      },
      maxBuffer: 10 * 1024 * 1024,
    });
    if (result.error) {
      throw new DashboardDataError(`could not start Grafana editor harness: ${result.error.message}`);
    }
    if (result.status !== 0) {
      const details = [result.stdout, result.stderr].filter(Boolean).join("\n").trim();
      throw new DashboardDataError(`Grafana editor harness failed${details ? `:\n${details}` : ""}`);
    }
    if (!fs.existsSync(outputPath)) {
      throw new DashboardDataError("Grafana editor harness produced no output");
    }
    const output = JSON.parse(fs.readFileSync(outputPath, "utf8"));
    if (output.schemaVersion !== 1) {
      throw new DashboardDataError("Grafana editor harness produced unsupported output");
    }
    return output;
  } finally {
    fs.rmSync(temporaryDirectory, { recursive: true, force: true });
  }
}
