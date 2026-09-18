#!/usr/bin/env node
import { execFileSync } from "node:child_process";
import { parseArgs } from "node:util";
import { main as data, loadJson, unwrapDashboard, collectPanels, collectVariables } from "./dashboard_visible_data.js";
import { main as editorDiagnostics } from "./dashboard_editor_diagnostics.js";
import { main as queryCheck } from "./query_check.js";
import { release, resolveGrafanaSource, runHarness } from "./upstream.js";

async function main(): Promise<number> {
  const [command, ...args] = process.argv.slice(2);
  if (command === "version" || command === "--version") {
    console.log(`Grafana ${release.version} (${release.commit})`);
    return 0;
  }
  if (command === "data") return data(args);
  if (command === "query-check") return queryCheck(args);
  if (command === "editor-diagnostics") return editorDiagnostics(args);
  if (!command || command === "--help" || command === "help") {
    console.log("Usage: grafana-inspect <structure|data|query-check|editor-schema|editor-diagnostics|version> [options]\nUse a command with --help for details.");
    return 0;
  }
  const { values, positionals } = parseArgs({ args, allowPositionals: true, options: {
    help: { type: "boolean" }, format: { type: "string", default: "text" },
    "grafana-source": { type: "string" }, "input-format": { type: "string", default: "resource" },
  } });
  if (values.help) {
    console.log(`Usage: grafana-inspect ${command} DASHBOARD [--format text|json]${command === "editor-schema" ? " [--input-format resource|spec] [--grafana-source PATH]" : ""}`);
    return 0;
  }
  if (positionals.length !== 1) throw new Error("provide one dashboard JSON file");
  if (!["text", "json"].includes(values.format!)) throw new Error("--format must be text or json");
  const payload = loadJson(positionals[0]);
  if (command === "structure") {
    const [shape, dashboard] = unwrapDashboard(payload);
    const panels = collectPanels(shape, dashboard, { includeCollapsed: true, includeHiddenTargets: true });
    const output = { title: dashboard.title, description: dashboard.description, tags: dashboard.tags,
      time: dashboard.timeSettings || dashboard.time, variables: dashboard.variables || dashboard.templating,
      values: collectVariables(shape, dashboard),
      annotations: dashboard.annotations, layout: dashboard.layout,
      panels: panels.map(p => ({ id: p.id, title: p.title, type: p.type, description: p.raw.description,
        layout: p.raw.gridPos, queries: p.targets, transformations: p.transformations })),
    };
    if (values.format === "json") console.log(JSON.stringify(output, null, 2));
    else {
      console.log(`# ${output.title}\n${output.description || ""}\n${panels.length} panels`);
      for (const [name, value] of Object.entries(output)) {
        if (!["title", "description", "panels"].includes(name) && value) console.log(`${name}: ${JSON.stringify(value)}`);
      }
      for (const panel of output.panels) {
        console.log(`\n[${panel.id}] ${panel.title} (${panel.type})`);
        if (panel.description) console.log(panel.description);
        if (panel.layout) console.log(`layout: ${JSON.stringify(panel.layout)}`);
        for (const query of panel.queries) console.log(`  ${query.refId}: ${JSON.stringify(query)}`);
      }
    }
    return 0;
  }
  if (command === "editor-schema") {
    if (!["resource", "spec"].includes(values["input-format"]!)) throw new Error("--input-format must be resource or spec");
    const backendVersion = execFileSync("grafana-dashboard", ["version"], { encoding: "utf8" });
    if (!backendVersion.includes(release.commit.slice(0, 12))) throw new Error("grafana-dashboard and grafana-inspect must target the same release; reinstall the tools");
    execFileSync("grafana-dashboard", ["validate", "--input", positionals[0], "--input-format", values["input-format"]!]);
    const resource = values["input-format"] === "spec"
      ? { apiVersion: "dashboard.grafana.app/v2", kind: "Dashboard", metadata: { name: "inspection" }, spec: payload }
      : payload;
    const openapi = JSON.parse(execFileSync("grafana-dashboard", ["schema"], { encoding: "utf8", maxBuffer: 32 * 1024 * 1024 }));
    const source = resolveGrafanaSource(values["grafana-source"] || "");
    const result = runHarness(source.path, { resource, openapi }, "schema");
    if (values.format === "json") console.log(JSON.stringify({ grafana: release.version, ...result }, null, 2));
    else {
      for (const diagnostic of result.diagnostics) console.log(`${diagnostic.range.start.line + 1}:${diagnostic.range.start.character + 1}: ${diagnostic.message}`);
      if (!result.diagnostics.length) console.log("Accepted by Grafana's editor schema and Monaco JSON worker");
    }
    return result.diagnostics.length ? 1 : 0;
  }
  throw new Error(`unknown command: ${command}`);
}

main().then(code => { process.exitCode = code; }, error => {
  console.error(`grafana-inspect: ${error.message}`);
  process.exitCode = 2;
});
