#!/usr/bin/env node
// Upgrade together; installation always uses the resulting committed pins.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const read = name => JSON.parse(fs.readFileSync(path.join(root, name), "utf8"));
const write = (name, data) => fs.writeFileSync(path.join(root, name), JSON.stringify(data, null, 2) + "\n");
const run = (command, args, directory) => execFileSync(command, args, { cwd: path.join(root, directory), stdio: "inherit" });
const releaseFile = "tools/grafana-version.json";
const packageFile = "tools/grafana-inspect/package.json";
const commonFile = path.join(root, "scripts/grafana/common.py");
const check = process.argv.includes("--check");
const offline = process.argv.includes("--offline");
let release = read(releaseFile);
if (!offline) {
  const api = async route => {
    const response = await fetch(`https://api.github.com/repos/grafana/grafana/${route}`);
    if (!response.ok) throw new Error(`GitHub: ${response.status}`);
    return response.json();
  };
  const latest = await api("releases/latest");
  assert(!latest.prerelease && !latest.draft && /^v\d+\.\d+\.\d+$/.test(latest.tag_name));
  let { object } = await api(`git/ref/tags/${latest.tag_name}`);
  while (object.type === "tag") ({ object } = await api(`git/tags/${object.sha}`));
  const current = { version: latest.tag_name.slice(1), commit: object.sha };
  if (check) assert.deepEqual(release, current, "Run node tools/update-grafana.mjs to update the stable release");
  else {
    release = current;
    run("go", ["get", ...["apps/dashboard", "pkg/apimachinery"].map(p => `github.com/grafana/grafana/${p}@${release.commit}`)], "tools/grafana-dashboard");
    run("go", ["mod", "tidy"], "tools/grafana-dashboard");
    const pkg = read(packageFile);
    pkg.dependencies["@grafana/data"] = release.version;
    // Match the frontend peers declared by the selected Grafana source.
    const upstream = await fetch(`https://raw.githubusercontent.com/grafana/grafana/${release.commit}/package.json`).then(r => r.json());
    for (const name of ["react", "react-dom"]) pkg.dependencies[name] = upstream.dependencies[name];
    write(packageFile, pkg);
    run("npm", ["install", "--package-lock-only"], "tools/grafana-inspect");
    fs.writeFileSync(commonFile, fs.readFileSync(commonFile, "utf8").replace(/GRAFANA_VERSION = "[^"]+"/, `GRAFANA_VERSION = "${release.version}"`));
    write(releaseFile, release);
  }
}
assert.equal(read(packageFile).dependencies["@grafana/data"], release.version);
const lock = read("tools/grafana-inspect/package-lock.json");
assert.equal(lock.packages["node_modules/@grafana/data"].version, release.version);
const mod = fs.readFileSync(path.join(root, "tools/grafana-dashboard/go.mod"), "utf8");
for (const module of ["apps/dashboard", "pkg/apimachinery"]) {
  assert(mod.split("\n").some(line => line.includes(`github.com/grafana/grafana/${module} `) && line.trim().endsWith(release.commit.slice(0, 12))));
}
assert(fs.readFileSync(commonFile, "utf8").includes(`GRAFANA_VERSION = "${release.version}"`));
console.log(`Grafana ${release.version} (${release.commit}): pins agree`);
if (!check && !offline) {
  run("go", ["test", "./..."], "tools/grafana-dashboard");
  run("npm", ["ci"], "tools/grafana-inspect");
  run("npm", ["test"], "tools/grafana-inspect");
  run("npm", ["run", "build"], "tools/grafana-inspect");
  for (const args of [["ruff", "format"], ["ruff", "check"], ["ty", "check"]]) run("uv", ["run", ...args, "scripts/grafana/common.py"], ".");
  console.log("Review conversion/editor parity and live integration before accepting the update.");
}
