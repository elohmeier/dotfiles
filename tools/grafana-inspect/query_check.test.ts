import assert from "node:assert/strict";
import test from "node:test";
import { syntaxProbe } from "./query_check.js";
import { applyVariableOverrides, collectPanels, collectVariables, prepareTargets, framesFromResponse, queryResponseFrames } from "./dashboard_visible_data.js";

test("v2 row and tab variables shadow ancestors without leaking between inactive tabs", () => {
  const variable = (value: string) => ({ kind: "TextVariable", spec: { name: "scope", current: { value } } });
  const reference = (name: string) => ({ kind: "GridLayout", spec: { items: [
    { kind: "GridLayoutItem", spec: { element: { kind: "ElementReference", name } } },
  ] } });
  const dashboard = {
    variables: [variable("dashboard")],
    elements: Object.fromEntries(["row", "first", "second"].map((name, index) => [name, {
      kind: "Panel", spec: { id: index + 1, title: name,
        data: { spec: { queries: [{ spec: { refId: "A", hidden: true,
          query: { group: "prometheus", datasource: { name: "p" }, spec: { expr: 'up{scope="${scope:raw}"}' } },
        } }] } },
      },
    }])),
    layout: { kind: "RowsLayout", spec: { rows: [{ kind: "RowsLayoutRow", spec: {
      variables: [variable("row")], layout: { kind: "TabsLayout", spec: { tabs: [
        { kind: "TabsLayoutTab", spec: { layout: reference("row") } },
        { kind: "TabsLayoutTab", spec: { variables: [variable("first")], layout: reference("first") } },
        { kind: "TabsLayoutTab", spec: { variables: [variable("second")], layout: reference("second") } },
      ] } },
    } }] } },
  };
  const globals = collectVariables("v2", dashboard);
  const panels = collectPanels("v2", dashboard, { includeCollapsed: true, includeHiddenTargets: true });
  assert.deepEqual(panels.map(panel => prepareTargets(panel, globals)[0].expr), [
    'up{scope="row"}', 'up{scope="first"}', 'up{scope="second"}',
  ]);
  assert.equal(globals.scope.display(), "dashboard");
  applyVariableOverrides(panels[1].variables, ["scope=override"]);
  assert.equal(prepareTargets(panels[1], globals)[0].expr, 'up{scope="override"}');
  assert.equal(prepareTargets(panels[2], globals)[0].expr, 'up{scope="second"}');
});

test("a tab-local variable needs no hidden dashboard-level default", () => {
  const dashboard = { elements: { p: { kind: "Panel", spec: { id: 1, data: { spec: { queries: [
    { spec: { refId: "A", query: { group: "prometheus", spec: { expr: 'up{scope="$scope"}' } } } },
  ] } } } } }, layout: { kind: "TabsLayout", spec: { tabs: [{ kind: "TabsLayoutTab", spec: {
    variables: [{ kind: "TextVariable", spec: { name: "scope", current: { value: "local" } } }],
    layout: { kind: "GridLayout", spec: { items: [{ spec: { element: { kind: "ElementReference", name: "p" } } }] } },
  } }] } } };
  const panel = collectPanels("v2", dashboard, { includeCollapsed: true, includeHiddenTargets: true })[0];
  assert.equal(syntaxProbe(String(prepareTargets(panel, {})[0].expr)), 'up{scope="local"}');
});

test("syntax probes replace known macros but reject unresolved variables", () => {
  assert.equal(syntaxProbe('rate(up[$__rate_interval]) offset ${__range}'), 'rate(up[5m]) offset 30m');
  assert.throws(() => syntaxProbe('up{host="$missing"}'), /Unresolved/);
  assert.throws(() => syntaxProbe('up{host="[[missing]]"}'), /Unresolved/);
  assert.equal(syntaxProbe('up{host=~".*$"}'), 'up{host=~".*$"}');
  assert.equal(syntaxProbe('label_replace(up, "host", "$1-${2}", "instance", "(.+):(.+)")'),
    'label_replace(up, "host", "$1-${2}", "instance", "(.+):(.+)")');
});

test("query inspection preserves malformed escaping instead of concealing it", () => {
  const dashboard = { templating: { list: [{ name: "host", current: { value: ".*" } }] }, panels: [
    { id: 1, title: "Escape regression", type: "timeseries", datasource: { type: "prometheus", uid: "p" },
      targets: [{ refId: "A", expr: 'up{host=~"${host:regex}"}' }] },
  ] };
  const panel = collectPanels("classic", dashboard, { includeCollapsed: true, includeHiddenTargets: true })[0];
  assert.equal(prepareTargets(panel, collectVariables("classic", dashboard))[0].expr, 'up{host=~"\\.\\*"}');
});

test("partial and malformed responses cannot be mistaken for no data", () => {
  assert.deepEqual(framesFromResponse({ results: { A: { frames: [] } } }, ["A"]), [[], []]);
  assert.match(framesFromResponse({ results: { A: { frames: [] } } }, ["A", "B"])[1][0], /B: query result missing/);
  assert.match(framesFromResponse({ results: { A: null } }, ["A"])[1][0], /malformed/);
  assert.match(framesFromResponse({ results: { A: { error: "bad_data: unknown escape sequence", status: 400 } } }, ["A"])[1][0], /bad_data/);
});

test("HTTP errors retain successful sibling frames without dumping payloads", () => {
  const [frames, errors] = queryResponseFrames({ statusCode: 400, text: "DO NOT ECHO RAW PAYLOAD", json: {
    results: {
      A: { status: 200, frames: [{ schema: { fields: [{ name: "Value", type: "number" }] }, data: { values: [[42]] } }] },
      B: { status: 500, error: "unexpected status code: 401", frames: [] },
    },
  } }, ["A", "B"]);
  assert.equal(frames.length, 1);
  assert.equal(frames[0].fields[0].values[0], 42);
  assert.ok(errors.includes("HTTP 400"));
  assert.ok(errors.some(e => e.includes("B: unexpected status code: 401")));
  assert.ok(!errors.some(e => e.includes("PAYLOAD")));
});
