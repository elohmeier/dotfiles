import { spawnSync } from "node:child_process";
import { parseArgs } from "node:util";
import { collectPanels, collectVariables, loadJson, prepareTargets, unwrapDashboard } from "./dashboard_visible_data.js";

// Syntax probes only: the backend calculates real macros from the request range.
// Never alter the expression reported or sent by `data`.
export function syntaxProbe(expr: string): string {
  const macros: Record<string, string> = {
    __rate_interval: "5m", __interval: "1m", __range: "30m",
    __rate_interval_ms: "300000", __interval_ms: "60000",
    __range_s: "1800", __range_ms: "1800000", __from: "1700000000000", __to: "1700001800000",
  };
  const probe = expr.replace(/\$\{(\w+)\}|\$(\w+)/g, (original, braced, bare) => macros[braced || bare] ?? original);
  if (/\$(?:\{\w+[^}]*\}|\w+)/.test(probe) || /\[\[\w+[^\]]*\]\]/.test(probe)) {
    throw new Error("Unresolved query variable; provide a saved dashboard value or a supported macro");
  }
  return probe;
}

export async function main(args: string[]): Promise<number> {
  const { values, positionals } = parseArgs({ args, allowPositionals: true, options: {
    help: { type: "boolean" }, format: { type: "string", default: "text" },
  } });
  if (values.help) {
    console.log("Usage: grafana-inspect query-check DASHBOARD [--format text|json]\nOffline PromQL syntax validation, including hidden queries and inactive tabs. Uses saved variable values and placeholder built-in durations. Does not validate metric existence, datasource access, non-PromQL languages or runtime results; use data for live checks.");
    return 0;
  }
  if (positionals.length !== 1) throw new Error("provide one dashboard JSON file");
  if (!["text", "json"].includes(values.format!)) throw new Error("--format must be text or json");
  const [shape, dashboard] = unwrapDashboard(loadJson(positionals[0]));
  const variables = collectVariables(shape, dashboard);
  const panels = collectPanels(shape, dashboard, { includeCollapsed: true, includeHiddenTargets: true });
  const queries: { panelId: string; title: string; refId: string; expr: string }[] = [];
  const errors: { panelId: string; title: string; refId: string; error: string }[] = [];
  const skipped: { panelId: string; title: string; refId: string; reason: string }[] = [];
  for (const panel of panels) {
    for (const target of prepareTargets(panel, variables)) {
      const identity = { panelId: panel.id, title: panel.title, refId: String(target.refId ?? "") };
      const datasource = target.datasource as { type?: string } | undefined;
      if (datasource?.type !== "prometheus") {
        skipped.push({ ...identity, reason: `No syntax parser for ${datasource?.type || "unknown datasource"}` });
        continue;
      }
      try {
        queries.push({ ...identity, expr: syntaxProbe(String(target.expr ?? "")) });
      } catch (error) {
        errors.push({ ...identity, error: String(error) });
      }
    }
  }
  const result = spawnSync("grafana-dashboard", ["validate-promql"], {
    input: JSON.stringify(queries), encoding: "utf8", maxBuffer: 32 * 1024 * 1024,
  });
  if (result.error) throw result.error;
  if (!result.stdout.trim()) throw new Error(result.stderr || "PromQL validator returned no report");
  const parsed = JSON.parse(result.stdout) as (typeof queries[number] & { error?: string })[];
  const diagnostics = [...errors, ...parsed.filter(q => q.error)];
  const report = { checked: queries.length, skipped, diagnostics, scope: "offline syntax only; saved variable defaults; all panels and targets" };
  if (values.format === "json") console.log(JSON.stringify(report, null, 2));
  else {
    console.log(`PromQL: ${queries.length} parsed, ${diagnostics.length} errors; ${skipped.length} non-PromQL queries not checked`);
    for (const d of diagnostics) console.log(`[${d.panelId}] ${d.title} / ${d.refId}: ${d.error}`);
  }
  return diagnostics.length || result.status !== 0 ? 1 : 0;
}
