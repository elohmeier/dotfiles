import assert from "node:assert/strict";
import test from "node:test";
import { syntaxProbe } from "./query_check.js";
import { collectPanels, collectVariables, prepareTargets, framesFromResponse, queryResponseFrames } from "./dashboard_visible_data.js";

test("syntax probes replace known macros but reject unresolved variables", () => {
  assert.equal(syntaxProbe('rate(up[$__rate_interval]) offset ${__range}'), 'rate(up[5m]) offset 30m');
  assert.throws(() => syntaxProbe('up{host="$missing"}'), /Unresolved/);
  assert.throws(() => syntaxProbe('up{host="[[missing]]"}'), /Unresolved/);
  assert.equal(syntaxProbe('up{host=~".*$"}'), 'up{host=~".*$"}');
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
