#!/usr/bin/env tsx
import { resolveGrafanaSource, runHarness } from "./upstream.js";

import {
  collectDashboardEditorDiagnosticsInput,
  DashboardDataError,
  type DashboardVisibleDataOptions,
  writeOutput,
} from "./dashboard_visible_data.js";

interface Args {
  dashboard: string;
  grafanaSource: string;
  reportOnly: boolean;
  output?: string;
  format: "text" | "json";
  options: DashboardVisibleDataOptions;
}

interface EditorAlert {
  transformationIndex: number;
  transformationId: string;
  transformationName: string;
  message: string;
}

interface HarnessPanelOutput {
  id: string;
  title: string;
  alerts: EditorAlert[];
  unknownTransformations: Array<{ index: number; id: string }>;
}

interface HarnessOutput {
  schemaVersion: 1;
  grafanaVersion: string;
  dashboard: string;
  panels: HarnessPanelOutput[];
}

interface DiagnosticsOutput {
  schemaVersion: 1;
  dashboard: string;
  sourceGrafanaVersion: string;
  sourceGrafanaCommit: string;
  sourceGrafanaDirty: boolean;
  panels: HarnessPanelOutput[];
  summary: {
    editorAlerts: number;
    unknownTransformations: number;
  };
}



export async function main(argv: string[]): Promise<number> {
  const args = parseArgs(argv);
  const source = resolveGrafanaSource(args.grafanaSource);
  const input = collectDashboardEditorDiagnosticsInput(args.dashboard, args.options);
  const harness = runHarness(source.path, input) as HarnessOutput;

  const panels = harness.panels;
  const output: DiagnosticsOutput = {
    schemaVersion: 1,
    dashboard: harness.dashboard,
    sourceGrafanaVersion: harness.grafanaVersion,
    sourceGrafanaCommit: source.commit,
    sourceGrafanaDirty: source.dirty,
    panels,
    summary: {
      editorAlerts: panels.reduce((total, panel) => total + panel.alerts.length, 0),
      unknownTransformations: panels.reduce((total, panel) => total + panel.unknownTransformations.length, 0),
    },
  };

  const rendered = args.format === "json" ? JSON.stringify(output, null, 2) : renderText(output);
  writeOutput(rendered, args.output);

  if (output.summary.unknownTransformations > 0) {
    return 1;
  }
  return !args.reportOnly && output.summary.editorAlerts > 0 ? 1 : 0;
}

function renderText(output: DiagnosticsOutput): string {
  const lines = [
    `Dashboard: ${output.dashboard}`,
    `Grafana: source ${output.sourceGrafanaVersion} (${output.sourceGrafanaCommit.slice(0, 12)}${output.sourceGrafanaDirty ? ", dirty" : ""}); input synthetic (one frame per query)`,
  ];

  for (const panel of output.panels) {
    if (!panel.alerts.length && !panel.unknownTransformations.length) {
      continue;
    }
    lines.push("", `Panel ${panel.id}: ${panel.title}`);
    for (const transformation of panel.unknownTransformations) {
      lines.push(`  unknown transformation ${transformation.index + 1}: ${transformation.id}`);
    }
    for (const alert of panel.alerts) {
      lines.push(
        `  editor alert ${alert.transformationIndex + 1}: ${alert.transformationName} (${alert.transformationId}): ${alert.message}`,
      );
    }
  }

  lines.push(
    "",
    `Summary: ${output.summary.editorAlerts} editor alert(s), ${output.summary.unknownTransformations} unknown transformation(s)`,
  );
  return lines.join("\n");
}

function parseArgs(argv: string[]): Args {
  const options: DashboardVisibleDataOptions = {};
  const args: Args = {
    dashboard: "",
    grafanaSource: process.env.GRAFANA_SOURCE || "",
    reportOnly: false,
    format: "text",
    options,
  };

  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    const next = (): string => {
      const value = argv[++index];
      if (value == null) {
        throw new DashboardDataError(`${arg} expects a value`);
      }
      return value;
    };

    if (arg === "--help" || arg === "-h") {
      printHelp();
      process.exit(0);
    } else if (arg === "--grafana-source") {
      args.grafanaSource = next();
    } else if (arg === "--report-only") {
      args.reportOnly = true;
    } else if (arg === "--panel-id") {
      options.panelId = next();
    } else if (arg === "--panel-ids") {
      options.panelIds = splitList(next());
    } else if (arg === "--panel-type") {
      options.panelTypes = [...(options.panelTypes ?? []), ...splitList(next())];
    } else if (arg === "--var") {
      options.vars = [...(options.vars ?? []), next()];
    } else if (arg === "--include-hidden-targets") {
      options.includeHiddenTargets = true;
    } else if (arg === "--include-collapsed") {
      options.includeCollapsed = true;
    } else if (arg === "--format") {
      const format = next();
      if (format !== "text" && format !== "json") {
        throw new DashboardDataError("--format expects text or json");
      }
      args.format = format;
    } else if (arg === "--output") {
      args.output = next();
    } else if (arg.startsWith("--")) {
      throw new DashboardDataError(`unknown option ${arg}`);
    } else if (!args.dashboard) {
      args.dashboard = arg;
    } else {
      throw new DashboardDataError(`unexpected argument ${arg}`);
    }
  }

  if (!args.dashboard) {
    throw new DashboardDataError("missing dashboard JSON file");
  }
  return args;
}

function splitList(value: string): string[] {
  const values = value.split(",").map((item) => item.trim()).filter(Boolean);
  if (!values.length) {
    throw new DashboardDataError("expected a non-empty comma-separated value");
  }
  return values;
}

function printHelp(): void {
  console.log(`Usage: grafana-inspect editor-diagnostics <dashboard.json> [options]

Mount Grafana's real transformation editors headlessly with one synthetic frame per query and
report semantic editor alerts. No Grafana server is needed. Editor alerts fail validation unless
--report-only is used. The pinned Grafana source/runtime is cached automatically on first use.

Options:
  --grafana-source PATH       Override the automatically cached pinned Grafana source
  --report-only               Report editor alerts without failing for them
  --panel-id ID               Validate one panel
  --panel-ids ID[,ID...]      Validate selected panels
  --panel-type TYPE           Filter by panel type; repeatable/comma-separated
  --var NAME=VALUE            Override a dashboard variable; repeatable
  --include-hidden-targets    Also run hidden query targets
  --include-collapsed         Include classic panels inside collapsed rows
  --format text|json          Output format (default: text)
  --output FILE               Write output to FILE instead of stdout`);
}
