import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

test("Grafana/Monaco accept tabs and reject null thresholds accepted by CUE", () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "grafana-editor-parity-"));
  try {
    const resource = JSON.parse(fs.readFileSync(new URL("./testdata/tabbed-dashboard-v2.json", import.meta.url), "utf8"));
    const file = path.join(directory, "dashboard.json");
    const validate = () => {
      fs.writeFileSync(file, JSON.stringify(resource));
      return spawnSync(process.execPath, ["dist/cli.js", "editor-schema", file, "--format", "json"], { encoding: "utf8" });
    };
    const accepted = validate();
    assert.equal(accepted.status, 0, accepted.stderr || accepted.stdout);
    const panel = Object.values(resource.spec.elements)[0] as any;
    panel.spec.vizConfig.spec.fieldConfig.defaults.thresholds = { mode: "absolute", steps: [{ color: "green", value: null }] };
    const rejected = validate();
    assert.equal(rejected.status, 1, rejected.stderr || rejected.stdout);
    assert.match(rejected.stdout, /number/);
  } finally { fs.rmSync(directory, { recursive: true, force: true }); }
});
