const path = require("node:path");

const grafanaSource = process.env.GRAFANA_SOURCE;
if (!grafanaSource) {
  throw new Error("GRAFANA_SOURCE is required");
}

const base = require(path.join(grafanaSource, "jest.config.js"));

module.exports = {
  ...base,
  rootDir: grafanaSource,
  roots: [...base.roots, __dirname],
  modulePaths: [
    path.join(grafanaSource, "node_modules"),
    path.join(grafanaSource, "public"),
  ],
  moduleNameMapper: {
    ...base.moduleNameMapper,
    "^@grafana/data$": path.join(
      grafanaSource,
      "packages/grafana-data/src/index.ts",
    ),
    "^@grafana/runtime$": path.join(
      grafanaSource,
      "packages/grafana-runtime/src/index.ts",
    ),
    "^@testing-library/react$": path.join(
      grafanaSource,
      "node_modules/@testing-library/react",
    ),
    "^react$": path.join(grafanaSource, "node_modules/react"),
    "^react/(.*)$": path.join(grafanaSource, "node_modules/react/$1"),
    "^react-dom$": path.join(grafanaSource, "node_modules/react-dom"),
    "^react-dom/(.*)$": path.join(grafanaSource, "node_modules/react-dom/$1"),
  },
  testRegex: process.env.GRAFANA_HARNESS_MODE === "schema" ? "grafana_editor_schema_harness\\.test\\.ts$" : "grafana_editor_diagnostics_harness\\.test\\.tsx$",
  watchPlugins: [],
};
