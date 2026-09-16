import fs from "node:fs";
import { getBackendSrv } from "@grafana/runtime";
import { fetchDashboardSchema } from "app/features/dashboard-scene/v2schema/dashboardSchemaFetcher";

jest.mock("app/features/dashboard/api/DashboardAPIVersionResolver", () => ({
  dashboardAPIVersionResolver: { resolve: jest.fn() },
}));
jest.mock("app/features/dashboard/api/v2", () => ({
  getK8sV2DashboardApiConfig: () => ({ group: "dashboard.grafana.app", version: "v2" }),
}));
jest.mock("@grafana/runtime", () => ({ getBackendSrv: jest.fn() }));
jest.mock("monaco-editor/esm/vs/editor/editor.worker.js", () => ({ initialize: jest.fn() }));

test("validate with Grafana's schema conversion and Monaco JSON worker", async () => {
  const input = JSON.parse(fs.readFileSync(process.env.GRAFANA_EDITOR_DIAGNOSTICS_INPUT!, "utf8"));
  jest.mocked(getBackendSrv).mockReturnValue({ get: async () => input.openapi } as never);
  const schema = await fetchDashboardSchema();
  // Let the actual bundled worker register its factory, replacing only worker transport.
  const transport = require("monaco-editor/esm/vs/editor/editor.worker.js");
  require("monaco-editor/esm/vs/language/json/json.worker.js");
  self.onmessage!({} as MessageEvent);
  const factory = transport.initialize.mock.calls[0][0];
  const uri = "file:///dashboard.json";
  const worker = factory({ getMirrorModels: () => [{
    uri: { toString: () => uri }, version: 1, getValue: () => JSON.stringify(input.resource),
  }] }, {
    languageId: "json", enableSchemaRequest: false,
    languageSettings: {
      validate: true, allowComments: false, schemaValidation: "error",
      schemas: [{ uri: "https://grafana.local/dashboard.json", fileMatch: ["*"], schema }],
    },
  });
  const diagnostics = await worker.doValidation(uri);
  fs.writeFileSync(process.env.GRAFANA_EDITOR_DIAGNOSTICS_OUTPUT!, JSON.stringify({ schemaVersion: 1, diagnostics }));
});
