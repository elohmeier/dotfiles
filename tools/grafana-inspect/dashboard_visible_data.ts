#!/usr/bin/env tsx
import type {
  DataFrame,
  DataFrameJSON,
  DataTransformerConfig,
  Field,
  FieldConfigPropertyItem,
  FieldConfigSource,
  TransformerRegistryItem,
} from "@grafana/data";
import { lastValueFrom } from "rxjs";

import * as fs from "node:fs";
import { createRequire } from "node:module";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

export type JsonObject = Record<string, unknown>;

ensureBrowserShimForGrafanaData();
process.env.I18NEXT_NO_SUPPORT_NOTICE ??= "1";

const require = createRequire(import.meta.url);
const {
  applyFieldOverrides,
  createTheme,
  dataFrameFromJSON,
  displayNameOverrideProcessor,
  FieldConfigOptionsRegistry,
  FieldType,
  formattedValueToString,
  getFieldDisplayName,
  identityOverrideProcessor,
  reduceField,
  standardTransformers,
  standardTransformersRegistry,
  transformDataFrame,
} = require("@grafana/data") as typeof import("@grafana/data");

const DEFAULT_QUERY_CONCURRENCY = 6;

const VAR_RE = /\$(?:{([A-Za-z_][A-Za-z0-9_]*)(?::([^}]+))?}|([A-Za-z_][A-Za-z0-9_]*))/g;

import { DashboardDataError } from "./errors.js";
export { DashboardDataError } from "./errors.js";
import { grafanaConfig, grafanaToken, grafanaJsonRequest, type GrafanaConfig } from "./http.js";

function ensureBrowserShimForGrafanaData(): void {
  const globalWithWindow = (globalThis as unknown) as {
    window?: Record<string, unknown>;
    document?: Record<string, unknown>;
    navigator?: Record<string, unknown>;
  };
  if (globalWithWindow.window) {
    return;
  }

  const localStorage = Object.create(null) as Record<string, unknown> & {
    getItem: (key: string) => string | null;
    setItem: (key: string, value: unknown) => void;
    removeItem: (key: string) => void;
    clear: () => void;
  };
  localStorage.getItem = (key) => (typeof localStorage[key] === "string" ? localStorage[key] : null);
  localStorage.setItem = (key, value) => {
    localStorage[key] = String(value);
  };
  localStorage.removeItem = (key) => {
    delete localStorage[key];
  };
  localStorage.clear = () => {
    for (const key of Object.keys(localStorage)) {
      if (!["getItem", "setItem", "removeItem", "clear"].includes(key)) {
        delete localStorage[key];
      }
    }
  };

  const documentShim = {
    head: {
      appendChild: () => undefined,
      removeChild: () => undefined,
    },
    createElement: () => ({
      setAttribute: () => undefined,
      appendChild: () => undefined,
      removeChild: () => undefined,
      style: {},
      sheet: { cssRules: [], insertRule: () => undefined },
    }),
    createTextNode: () => ({}),
    getElementsByTagName: () => [{}],
    querySelector: () => null,
  };

  globalWithWindow.document = documentShim;
  const navigatorShim = globalWithWindow.navigator || { language: "en-US" };
  globalWithWindow.window = {
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => true,
    document: documentShim,
    history: {
      pushState: () => undefined,
      replaceState: () => undefined,
    },
    location: {
      href: "http://localhost/",
      pathname: "/",
      search: "",
      hash: "",
    },
    localStorage,
    navigator: navigatorShim,
    __grafanaSceneContext: null,
  };
}

class TemplateValue {
  constructor(
    readonly values: string[],
    readonly text = "",
    readonly multi = false,
    readonly isAll = false,
    readonly allValue?: string,
  ) {}

  render(fmt?: string): string {
    if (this.isAll) {
      return this.allValue || ".*";
    }
    const values = this.values.filter((value) => value != null).map(String);
    if (!values.length) {
      return "";
    }
    if (fmt === "raw" || fmt === "csv") {
      return values.join(",");
    }
    if (fmt === "text") {
      return this.text || values.join(",");
    }
    if (fmt === "regex" || (this.multi && values.length > 1)) {
      return values.map(escapeRegex).join("|");
    }
    return values[0];
  }

  display(): string {
    return this.render("raw");
  }
}

interface Panel {
  id: string;
  title: string;
  type: string;
  raw: JsonObject;
  targets: JsonObject[];
  transformations: JsonObject[];
  fieldConfig: FieldConfigSource;
  options: JsonObject;
  order: number;
  source: "classic" | "v2";
}

interface PanelResult {
  panel: Panel;
  frames: DataFrame[];
  errors: string[];
  warnings: string[];
  queryTargets: JsonObject[];
}

export interface DashboardVisibleDataOptions {
  panelId?: string;
  panelIds?: string[];
  panelTypes?: string[];
  start?: string;
  end?: string;
  vars?: string[];
  step?: string;
  includeHiddenTargets?: boolean;
  includeCollapsed?: boolean;
  allowNoQueryable?: boolean;
  rawFrames?: boolean;
  timeout?: number;
  concurrency?: number;
}

export interface DashboardEditorDiagnosticsPanelInput {
  id: string;
  title: string;
  targets: JsonObject[];
  transformations: DataTransformerConfig[];
  frames: DataFrameJSON[];
}

export interface DashboardEditorDiagnosticsInput {
  schemaVersion: 1;
  dashboard: string;
  variables: JsonObject[];
  panels: DashboardEditorDiagnosticsPanelInput[];
}

export interface FrameJson {
  name: string;
  refId: string;
  fields: string[];
  rows: JsonObject[];
}

export interface SeriesJson {
  name: string;
  calcs: JsonObject;
  display: Record<string, string>;
}

export interface PanelJson {
  id: string;
  title: string;
  type: string;
  targetRefs: string[];
  errors: string[];
  warnings: string[];
  frames: FrameJson[];
  series?: SeriesJson[];
}

export interface DashboardVisibleData {
  dashboard: string;
  from: string;
  to: string;
  variables: Record<string, string>;
  panels: PanelJson[];
}

interface DashboardQueryResult {
  dashboard: JsonObject;
  start: string;
  end: string;
  variables: Record<string, TemplateValue>;
  results: PanelResult[];
}

interface Args {
  dashboard: string;
  listPanels: boolean;
  panelId?: string;
  panelIds: string[];
  panelTypes: string[];
  output?: string;
  start?: string;
  end?: string;
  vars: string[];
  step?: string;
  maxRows: number;
  maxSeries: number;
  maxCellWidth: number;
  includeHiddenTargets: boolean;
  includeCollapsed: boolean;
  rawFrames: boolean;
  timeout: number;
  concurrency: number;
  format: "text" | "json";
}

export async function main(argv: string[]): Promise<number> {
  const args = parseArgs(argv);
  const payload = loadJson(repoPath(args.dashboard));
  const [shape, dashboard] = unwrapDashboard(payload);
  let panels = collectPanels(shape, dashboard, {
    includeHiddenTargets: args.includeHiddenTargets,
    includeCollapsed: args.includeCollapsed,
  });
  panels = filterPanelsByType(panels, args.panelTypes);
  panels = selectPanel(panels, args.panelId);
  panels = selectPanels(panels, args.panelIds, false);

  if (args.listPanels) {
    writeOutput(renderPanelList(panels), args.output);
    return Promise.resolve(0);
  }

  const queried = await queryDashboardVisibleData(args.dashboard, {
    panelId: args.panelId,
    panelIds: args.panelIds.length ? args.panelIds : undefined,
    panelTypes: args.panelTypes,
    start: args.start,
    end: args.end,
    vars: args.vars,
    step: args.step,
    includeHiddenTargets: args.includeHiddenTargets,
    includeCollapsed: args.includeCollapsed,
    rawFrames: args.rawFrames,
    timeout: args.timeout,
    concurrency: args.concurrency,
  });
  const output = args.format === "json"
    ? JSON.stringify(dashboardQueryResultToJson(queried), null, 2)
    : renderTextResult(queried.dashboard, {
      results: queried.results,
      variables: queried.variables,
      start: queried.start,
      end: queried.end,
      maxRows: args.maxRows,
      maxSeries: args.maxSeries,
      maxWidth: args.maxCellWidth,
    });
  writeOutput(output, args.output);
  return queried.results.some((result) => result.errors.length > 0) ? 1 : 0;
}

export async function collectDashboardVisibleData(
  dashboardPath: string,
  options: DashboardVisibleDataOptions = {},
): Promise<DashboardVisibleData> {
  return dashboardQueryResultToJson(await queryDashboardVisibleData(dashboardPath, options));
}

export function collectDashboardEditorDiagnosticsInput(
  dashboardPath: string,
  options: DashboardVisibleDataOptions = {},
): DashboardEditorDiagnosticsInput {
  const payload = loadJson(repoPath(dashboardPath));
  const [shape, dashboard] = unwrapDashboard(payload);
  let panels = collectPanels(shape, dashboard, {
    includeHiddenTargets: Boolean(options.includeHiddenTargets),
    includeCollapsed: Boolean(options.includeCollapsed),
  });
  panels = filterPanelsByType(panels, options.panelTypes || []);
  panels = selectPanel(panels, options.panelId);
  if (options.panelIds !== undefined) {
    panels = selectPanels(panels, options.panelIds, true);
  }
  panels = panels.filter((panel) => panel.transformations.length > 0 && panel.targets.length > 0);
  if (!panels.length && !options.allowNoQueryable) {
    throw new DashboardDataError("no queryable panels with transformations matched");
  }

  const variables = collectVariables(shape, dashboard);
  Object.assign(variables, parseVarOverrides(options.vars || []));

  return {
    schemaVersion: 1,
    dashboard: asText(dashboard.title) || "(untitled dashboard)",
    variables: templateVariableModels(variables),
    panels: panels.map((panel) => {
      const targets = prepareTargets(panel, variables);
      return {
        id: panel.id,
        title: panel.title,
        targets,
        transformations: dataTransformerConfigs(panel.transformations),
        frames: syntheticFrames(targets),
      };
    }),
  };
}

function syntheticFrames(targets: JsonObject[]): DataFrameJSON[] {
  return targets.map((target, index) => {
    const refId = asText(target.refId) || String.fromCharCode("A".charCodeAt(0) + index);
    return {
      schema: {
        name: refId,
        refId,
        fields: [{ name: "Value", type: FieldType.number }],
      },
      data: { values: [[index + 1]] },
    };
  });
}

async function queryDashboardVisibleData(
  dashboardPath: string,
  options: DashboardVisibleDataOptions,
): Promise<DashboardQueryResult> {
  initGrafanaDataForCli();

  const payload = loadJson(repoPath(dashboardPath));
  const [shape, dashboard] = unwrapDashboard(payload);
  let panels = collectPanels(shape, dashboard, {
    includeHiddenTargets: Boolean(options.includeHiddenTargets),
    includeCollapsed: Boolean(options.includeCollapsed),
  });
  panels = filterPanelsByType(panels, options.panelTypes || []);
  panels = selectPanel(panels, options.panelId);
  if (options.panelIds !== undefined) {
    panels = selectPanels(panels, options.panelIds, true);
  }
  const queryable = panels.filter((panel) => panel.targets.length > 0);
  if (!queryable.length && !options.allowNoQueryable) {
    throw new DashboardDataError("no queryable panels matched");
  }

  const [defaultStart, defaultEnd] = dashboardTime(shape, dashboard);
  const start = options.start || defaultStart;
  const end = options.end || defaultEnd;
  const variables = collectVariables(shape, dashboard);
  Object.assign(variables, parseVarOverrides(options.vars || []));
  const queryVariables = { ...variables };
  const stepMs = options.step ? parseStepMs(options.step) : undefined;

  const config = grafanaConfig();
  const token = grafanaToken();
  const results = queryable.length
    ? await queryPanels(queryable, {
      config,
      token,
      variables: queryVariables,
      start,
      end,
      stepMs,
      timeout: options.timeout ?? 60,
      concurrency: options.concurrency ?? DEFAULT_QUERY_CONCURRENCY,
    })
    : [];
  for (const result of results) {
    if (!options.rawFrames) {
      try {
        await processPanelResult(result, queryVariables);
      } catch (error) {
        result.errors.push(`frame processing failed: ${(error as Error).message}`);
        result.frames = [];
      }
    }
  }
  return { dashboard, start, end, variables, results };
}

function dashboardQueryResultToJson(result: DashboardQueryResult): DashboardVisibleData {
  return {
    dashboard: asText(result.dashboard.title) || "(untitled dashboard)",
    from: result.start,
    to: result.end,
    variables: Object.fromEntries(
      Object.entries(result.variables)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([name, value]) => [name, value.display()]),
    ),
    panels: result.results.map(panelResultToJson),
  };
}

export function initGrafanaDataForCli(): void {
  ((globalThis as unknown) as { window?: Record<string, unknown> }).window ??= {};
  const globals = globalThis as unknown as { __dashboardVisibleDataInitialized?: boolean };
  if (globals.__dashboardVisibleDataInitialized) {
    return;
  }
  globals.__dashboardVisibleDataInitialized = true;

  const transformerItems = new Map<string, TransformerRegistryItem>();
  for (const transformer of Object.values(standardTransformers)) {
    const ids = [transformer.id, ...((transformer as { aliasIds?: string[] }).aliasIds ?? [])];
    for (const id of ids) {
      if (transformerItems.has(id)) {
        continue;
      }
      transformerItems.set(id, {
        id,
        name: transformer.name,
        description: transformer.description,
        transformation: () => Promise.resolve(transformer),
        editor: (() => null) as TransformerRegistryItem["editor"],
        imageDark: "",
        imageLight: "",
      });
    }
  }
  standardTransformersRegistry.setInit(() => [...transformerItems.values()]);
}

function standardFieldProperties(): FieldConfigPropertyItem[] {
  const editor = (() => null) as FieldConfigPropertyItem["editor"];
  const override = (() => null) as FieldConfigPropertyItem["override"];
  const standard = (id: string, pathName = id): FieldConfigPropertyItem => ({
    id,
    path: pathName,
    name: id,
    editor,
    override,
    process: identityOverrideProcessor,
    shouldApply: () => true,
  });

  return [
    {
      ...standard("displayName"),
      process: displayNameOverrideProcessor,
      settings: { placeholder: "none", expandTemplateVars: true },
    },
    standard("unit"),
    standard("min"),
    standard("max"),
    standard("fieldMinMax"),
    standard("decimals"),
    standard("thresholds"),
    standard("mappings"),
    standard("noValue"),
    standard("links"),
    standard("color"),
  ];
}

function fieldConfigRegistry(): InstanceType<typeof FieldConfigOptionsRegistry> {
  return new FieldConfigOptionsRegistry(() => standardFieldProperties());
}

function repoPath(inputPath: string): string {
  return path.isAbsolute(inputPath) ? inputPath : path.resolve(process.cwd(), inputPath);
}

export function loadJson(filename: string): JsonObject {
  let text: string;
  try {
    text = fs.readFileSync(filename, "utf8");
  } catch (error) {
    throw new DashboardDataError(`${filename}: could not read file: ${(error as Error).message}`);
  }
  try {
    const parsed: unknown = JSON.parse(text);
    if (!isObject(parsed)) {
      throw new DashboardDataError(`${filename}: JSON root must be an object`);
    }
    return parsed;
  } catch (error) {
    if (error instanceof DashboardDataError) {
      throw error;
    }
    throw new DashboardDataError(`${filename}: invalid JSON: ${(error as Error).message}`);
  }
}

export function unwrapDashboard(payload: JsonObject): ["classic" | "v2", JsonObject] {
  if (isObject(payload.dashboard)) {
    return ["classic", payload.dashboard];
  }
  if (isObject(payload.spec) && isObject(payload.spec.elements)) {
    return ["v2", payload.spec];
  }
  if (isObject(payload.elements)) {
    return ["v2", payload];
  }
  if (Array.isArray(payload.panels)) {
    return ["classic", payload];
  }
  throw new DashboardDataError("input does not look like a classic dashboard or v2 DashboardSpec");
}

function asText(value: unknown): string {
  if (value == null) {
    return "";
  }
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean" || typeof value === "bigint") {
    return String(value);
  }
  return JSON.stringify(value);
}

function asValues(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map(asText);
  }
  if (value == null) {
    return [];
  }
  return [asText(value)];
}

function templateValue(variable: JsonObject): TemplateValue {
  const spec = isObject(variable.spec) ? variable.spec : variable;
  const current = isObject(spec.current) ? spec.current : {};
  const values = asValues(current.value);
  const text = Array.isArray(current.text) ? current.text.map(asText).join(",") : asText(current.text);
  const isAll = values.includes("$__all");
  const allValue = asText(spec.allValue) || undefined;
  return new TemplateValue(values, text, Boolean(spec.multi), isAll, allValue);
}

export function collectVariables(shape: "classic" | "v2", dashboard: JsonObject): Record<string, TemplateValue> {
  let items: unknown[] = [];
  if (shape === "classic") {
    const templating = isObject(dashboard.templating) ? dashboard.templating : {};
    items = Array.isArray(templating.list) ? templating.list : [];
  } else {
    items = Array.isArray(dashboard.variables) ? dashboard.variables : [];
  }

  const variables: Record<string, TemplateValue> = {};
  for (const item of items) {
    if (!isObject(item)) {
      continue;
    }
    const spec = isObject(item.spec) ? item.spec : item;
    const name = asText(spec.name);
    if (name) {
      variables[name] = templateValue(item);
    }
  }
  return variables;
}

function parseVarOverrides(items: string[]): Record<string, TemplateValue> {
  const result: Record<string, TemplateValue> = {};
  for (const item of items) {
    const index = item.indexOf("=");
    if (index < 0) {
      throw new DashboardDataError(`--var expects name=value, got ${JSON.stringify(item)}`);
    }
    const name = item.slice(0, index);
    const value = item.slice(index + 1);
    if (!name) {
      throw new DashboardDataError(`--var expects a non-empty name, got ${JSON.stringify(item)}`);
    }
    result[name] = new TemplateValue([value], value);
  }
  return result;
}

function templateVariableModels(variables: Record<string, TemplateValue>): JsonObject[] {
  return Object.entries(variables).map(([name, variable]) => ({
    type: "custom",
    name,
    multi: variable.multi,
    includeAll: variable.isAll,
    ...(variable.allValue ? { allValue: variable.allValue } : {}),
    current: {
      text: variable.text || variable.values.join(","),
      value: variable.isAll
        ? "$__all"
        : variable.multi
        ? variable.values
        : variable.values[0] || "",
    },
  }));
}

function replaceVariables(value: string, variables: Record<string, TemplateValue>, scopedVars?: unknown): string {
  let result = value;
  const dataContext = scopedDataContext(scopedVars);
  if (dataContext?.field) {
    const displayName = getFieldDisplayName(dataContext.field, dataContext.frame, dataContext.data);
    result = result
      .replaceAll("${__field.displayName}", displayName)
      .replaceAll("$__field.displayName", displayName)
      .replaceAll("${__field.name}", dataContext.field.name)
      .replaceAll("$__field.name", dataContext.field.name);
  }

  return result.replace(
    VAR_RE,
    (match, braced: string | undefined, fmt: string | undefined, named: string | undefined) => {
      const name = braced || named;
      const variable = name ? variables[name] : undefined;
      return variable ? variable.render(fmt) : match;
    },
  );
}

function substituteVars(value: unknown, variables: Record<string, TemplateValue>): unknown {
  if (typeof value === "string") {
    return replaceVariables(value, variables);
  }
  if (Array.isArray(value)) {
    return value.map((item) => substituteVars(item, variables));
  }
  if (isObject(value)) {
    return Object.fromEntries(Object.entries(value).map(([key, child]) => [key, substituteVars(child, variables)]));
  }
  return value;
}

function iterClassicPanels(items: unknown[], includeCollapsed: boolean, parentCollapsed = false): JsonObject[] {
  const result: JsonObject[] = [];
  for (const item of items) {
    if (!isObject(item)) {
      continue;
    }
    const collapsed = parentCollapsed || Boolean(item.collapsed);
    if (includeCollapsed || !parentCollapsed) {
      result.push(item);
    }
    if (Array.isArray(item.panels) && (includeCollapsed || !collapsed)) {
      result.push(...iterClassicPanels(item.panels, includeCollapsed, collapsed));
    }
  }
  return result;
}

function classicPanelTargets(panel: JsonObject, includeHiddenTargets: boolean): JsonObject[] {
  const rawTargets = Array.isArray(panel.targets) ? panel.targets : [];
  const targets = rawTargets.flatMap((target, index): JsonObject[] => {
    if (!isObject(target)) {
      return [];
    }
    const item = deepClone(target);
    if (!("datasource" in item) && isObject(panel.datasource)) {
      item.datasource = deepClone(panel.datasource);
    }
    item.refId ??= String.fromCharCode("A".charCodeAt(0) + index);
    return [item];
  });
  return filterHiddenTargets(targets, includeHiddenTargets);
}

function classicPanels(
  dashboard: JsonObject,
  options: { includeHiddenTargets: boolean; includeCollapsed: boolean },
): Panel[] {
  const rawPanels = Array.isArray(dashboard.panels) ? dashboard.panels : [];
  return iterClassicPanels(rawPanels, options.includeCollapsed).map((raw, order) => ({
    id: asText(raw.id),
    title: asText(raw.title) || "(untitled)",
    type: asText(raw.type) || "unknown",
    raw,
    targets: classicPanelTargets(raw, options.includeHiddenTargets),
    transformations: Array.isArray(raw.transformations) ? raw.transformations.filter(isObject) : [],
    fieldConfig: fieldConfigSource(raw.fieldConfig),
    options: isObject(raw.options) ? raw.options : {},
    order,
    source: "classic",
  }));
}

function v2LayoutOrder(layout: unknown): Record<string, number> {
  const order: Record<string, number> = {};
  const walk = (node: unknown): void => {
    if (Array.isArray(node)) {
      node.forEach(walk);
      return;
    }
    if (!isObject(node)) {
      return;
    }
    if (node.kind === "ElementReference") {
      const name = asText(node.name);
      if (name && !(name in order)) {
        order[name] = Object.keys(order).length;
      }
    }
    for (const key of ["items", "children", "rows", "tabs"]) {
      const child = node[key];
      if (Array.isArray(child)) {
        child.forEach(walk);
      }
    }
    if (isObject(node.spec)) {
      walk(node.spec);
    }
    if (isObject(node.element)) {
      walk(node.element);
    }
    if (isObject(node.layout)) {
      walk(node.layout);
    }
  };
  walk(layout);
  return order;
}

function v2QueryToTarget(query: JsonObject, refId: string): JsonObject {
  const querySpec = isObject(query.spec) ? query.spec : {};
  const target = deepClone(querySpec);
  target.refId = refId;

  const datasource = isObject(query.datasource) ? query.datasource : {};
  const uid = asText(datasource.uid || datasource.name);
  const dsType = asText(datasource.type || query.group);
  if (uid) {
    target.datasource = { uid, type: dsType };
  } else if (dsType) {
    target.datasource = { type: dsType };
  }

  if (dsType === "prometheus" || dsType === "loki") {
    const instant = Boolean(target.instant);
    target.instant = instant;
    target.range ??= !instant;
  }
  return target;
}

function v2PanelTargets(panelSpec: JsonObject, includeHiddenTargets: boolean): [JsonObject[], JsonObject[]] {
  const data = isObject(panelSpec.data) ? panelSpec.data : {};
  const dataSpec = isObject(data.spec) ? data.spec : {};
  const rawQueries = Array.isArray(dataSpec.queries) ? dataSpec.queries : [];
  const targets: JsonObject[] = [];
  rawQueries.forEach((queryItem, index) => {
    if (!isObject(queryItem)) {
      return;
    }
    const querySpec = isObject(queryItem.spec) ? queryItem.spec : {};
    const query = isObject(querySpec.query) ? querySpec.query : {};
    const refId = asText(querySpec.refId) || String.fromCharCode("A".charCodeAt(0) + index);
    const target = v2QueryToTarget(query, refId);
    if (querySpec.hidden) {
      target.hide = true;
    }
    targets.push(target);
  });

  const transformations = Array.isArray(dataSpec.transformations)
    ? dataSpec.transformations.filter(isObject)
    : [];
  return [filterHiddenTargets(targets, includeHiddenTargets), transformations];
}

function filterHiddenTargets(targets: JsonObject[], includeHiddenTargets: boolean): JsonObject[] {
  if (includeHiddenTargets) {
    return targets;
  }
  const required = expressionDependencies(targets.filter((target) => !target.hide));
  return targets.filter((target) => !target.hide || required.has(asText(target.refId)));
}

function expressionDependencies(targets: JsonObject[]): Set<string> {
  const refs = new Set<string>();
  for (const target of targets) {
    const datasource = isObject(target.datasource) ? target.datasource : {};
    if (asText(datasource.type) !== "__expr__") {
      continue;
    }
    const expression = asText(target.expression);
    for (const match of expression.matchAll(/\$([A-Za-z][A-Za-z0-9_]*)/g)) {
      refs.add(match[1]);
    }
  }
  return refs;
}

function v2Panels(dashboard: JsonObject, includeHiddenTargets: boolean): Panel[] {
  const elements = isObject(dashboard.elements) ? dashboard.elements : {};
  const orderMap = v2LayoutOrder(dashboard.layout);
  const panels: Panel[] = [];

  for (const [name, element] of Object.entries(elements)) {
    if (!isObject(element) || element.kind !== "Panel") {
      continue;
    }
    const spec = isObject(element.spec) ? element.spec : {};
    const [targets, transformations] = v2PanelTargets(spec, includeHiddenTargets);
    const vizConfig = isObject(spec.vizConfig) ? spec.vizConfig : {};
    const vizSpec = isObject(vizConfig.spec) ? vizConfig.spec : {};
    panels.push({
      id: asText(spec.id) || name,
      title: asText(spec.title) || "(untitled)",
      type: asText(vizConfig.group) || "unknown",
      raw: spec,
      targets,
      transformations,
      fieldConfig: fieldConfigSource(vizSpec.fieldConfig),
      options: isObject(vizSpec.options) ? vizSpec.options : {},
      order: orderMap[name] ?? Object.keys(orderMap).length + panels.length,
      source: "v2",
    });
  }

  panels.sort((left, right) => left.order - right.order || left.id.localeCompare(right.id));
  return panels;
}

export function collectPanels(
  shape: "classic" | "v2",
  dashboard: JsonObject,
  options: { includeHiddenTargets: boolean; includeCollapsed: boolean },
): Panel[] {
  return shape === "classic" ? classicPanels(dashboard, options) : v2Panels(dashboard, options.includeHiddenTargets);
}

function dashboardTime(shape: "classic" | "v2", dashboard: JsonObject): [string, string] {
  const timeSettings = shape === "classic"
    ? isObject(dashboard.time)
      ? dashboard.time
      : {}
    : isObject(dashboard.timeSettings)
    ? dashboard.timeSettings
    : {};
  return [asText(timeSettings.from) || "now-6h", asText(timeSettings.to) || "now"];
}

function selectPanel(panels: Panel[], panelId?: string): Panel[] {
  if (!panelId) {
    return panels;
  }
  const matches = panels.filter((panel) => panel.id === panelId);
  if (!matches.length) {
    throw new DashboardDataError(`no panel with id ${JSON.stringify(panelId)}`);
  }
  if (matches.length > 1) {
    throw new DashboardDataError(`multiple panels have id ${JSON.stringify(panelId)}`);
  }
  return matches;
}

function selectPanels(panels: Panel[], panelIds: string[], explicit: boolean): Panel[] {
  if (!panelIds.length) {
    return explicit ? [] : panels;
  }
  const wanted = new Set(panelIds);
  const matches = panels.filter((panel) => wanted.has(panel.id));
  const missing = [...wanted].filter((panelId) => !matches.some((panel) => panel.id === panelId));
  if (missing.length) {
    throw new DashboardDataError(`no panel with id(s) ${missing.map((panelId) => JSON.stringify(panelId)).join(", ")}`);
  }
  return matches;
}

function filterPanelsByType(panels: Panel[], panelTypes: string[]): Panel[] {
  if (!panelTypes.length) {
    return panels;
  }
  const wanted = new Set(panelTypes.map((panelType) => panelType.toLowerCase()));
  return panels.filter((panel) => wanted.has(panel.type.toLowerCase()));
}

function parseStepMs(value: string): number {
  const match = value.match(/^\s*(\d+(?:\.\d+)?)\s*(ms|s|m|h)?\s*$/);
  if (!match) {
    throw new DashboardDataError(`--step: bad duration ${JSON.stringify(value)} (expected e.g. 30s, 1m, 500ms)`);
  }
  const amount = Number.parseFloat(match[1]);
  const unit = match[2] || "s";
  const factors: Record<string, number> = { ms: 1, s: 1000, m: 60_000, h: 3_600_000 };
  return Math.trunc(amount * factors[unit]);
}

function targetDatasource(target: JsonObject): string {
  const datasource = isObject(target.datasource) ? target.datasource : {};
  const dsType = asText(datasource.type);
  const uid = asText(datasource.uid || datasource.name);
  return dsType && uid ? `${dsType}:${uid}` : uid || dsType;
}

function prepareTargets(panel: Panel, variables: Record<string, TemplateValue>, stepMs?: number): JsonObject[] {
  const substituted = substituteVars(panel.targets, variables);
  if (!Array.isArray(substituted)) {
    return [];
  }
  const targets = substituted.filter(isObject);
  for (const target of targets) {
    const datasource = isObject(target.datasource) ? target.datasource : {};
    const dsType = datasource.type;
    if (stepMs != null && (dsType === "prometheus" || dsType === "loki")) {
      target.intervalMs ??= stepMs;
      target.maxDataPoints ??= 1_000_000;
    }
  }
  return targets;
}

async function queryPanels(
  panels: Panel[],
  options: {
    config: GrafanaConfig;
    token: string;
    variables: Record<string, TemplateValue>;
    start: string;
    end: string;
    stepMs?: number;
    timeout: number;
    concurrency: number;
  },
): Promise<PanelResult[]> {
  return mapParallelOrdered(panels, options.concurrency, (panel) => queryPanel(panel, options));
}

async function mapParallelOrdered<T, R>(
  items: T[],
  concurrency: number,
  mapper: (item: T, index: number) => Promise<R>,
): Promise<R[]> {
  const limit = Math.min(Math.max(1, Math.trunc(concurrency)), Math.max(1, items.length));
  const results = new Array<R>(items.length);
  let nextIndex = 0;

  const workers = Array.from({ length: limit }, async () => {
    while (true) {
      const index = nextIndex++;
      if (index >= items.length) {
        return;
      }
      results[index] = await mapper(items[index], index);
    }
  });

  await Promise.all(workers);
  return results;
}

async function queryPanel(
  panel: Panel,
  options: {
    config: GrafanaConfig;
    token: string;
    variables: Record<string, TemplateValue>;
    start: string;
    end: string;
    stepMs?: number;
    timeout: number;
  },
): Promise<PanelResult> {
  const result: PanelResult = { panel, frames: [], errors: [], warnings: [], queryTargets: [] };
  const targets = prepareTargets(panel, options.variables, options.stepMs);
  result.queryTargets = targets;
  if (!targets.length) {
    result.warnings.push("panel has no visible query targets");
    return result;
  }

  const requestId = cryptoRandomHex();
  const body = { queries: targets, from: options.start, to: options.end };
  const response = await grafanaJsonRequest(options.config, options.token, {
    method: "POST",
    pathname: "/api/ds/query",
    search: `?requestId=${requestId}`,
    timeout: options.timeout,
    body,
  });

  if (response.statusCode >= 400) {
    result.errors.push(`HTTP ${response.statusCode}: ${response.text.trim()}`);
    return result;
  }

  if (!isObject(response.json)) {
    result.errors.push("Grafana returned a non-object JSON response");
    return result;
  }
  const [frames, errors] = framesFromResponse(response.json);
  result.frames = frames;
  result.errors.push(...errors);
  return result;
}

function framesFromResponse(payload: JsonObject): [DataFrame[], string[]] {
  const frames: DataFrame[] = [];
  const errors: string[] = [];
  const results = isObject(payload.results) ? payload.results : undefined;
  if (!results) {
    return [frames, ["response has no results object"]];
  }

  for (const [refId, rawResult] of Object.entries(results)) {
    if (!isObject(rawResult)) {
      continue;
    }
    if (rawResult.error) {
      errors.push(`${refId}: ${asText(rawResult.error)}`);
    }
    if (rawResult.status != null && rawResult.status !== 200 && rawResult.status !== "success") {
      errors.push(`${refId}: status ${asText(rawResult.status)}`);
    }
    const rawFrames = Array.isArray(rawResult.frames) ? rawResult.frames : [];
    for (const rawFrame of rawFrames) {
      if (!isObject(rawFrame)) {
        continue;
      }
      try {
        const frame = dataFrameFromJSON(rawFrame);
        frame.refId ||= refId;
        frames.push(frame);
      } catch (error) {
        errors.push(`${refId}: could not decode data frame: ${(error as Error).message}`);
      }
    }
  }
  return [frames, errors];
}

async function processPanelResult(result: PanelResult, variables: Record<string, TemplateValue>): Promise<void> {
  if (result.errors.length || !result.frames.length) {
    return;
  }

  let frames = result.frames;
  const tableLike = panelIsTableLike(result.panel, frames);
  if (tableLike || result.panel.transformations.length > 0) {
    frames = await applyGrafanaTransformations(frames, result.panel.transformations, variables);
    frames = applyGrafanaFieldOverrides(frames, result.panel.fieldConfig, variables);
  } else {
    frames = applyGrafanaFieldOverrides(frames, result.panel.fieldConfig, variables);
  }
  if (tableLike) {
    frames = applyTableSort(frames, result.panel.options);
  }
  result.frames = frames;
}

export async function applyGrafanaTransformations(
  frames: DataFrame[], transformations: JsonObject[], variables: Record<string, TemplateValue>,
): Promise<DataFrame[]> {
  const configs = dataTransformerConfigs(transformations);
  for (const config of configs) {
    if (!config.disabled && !standardTransformersRegistry.getIfExists(config.id)) {
      throw new DashboardDataError(`unsupported transformation ${JSON.stringify(config.id)}`);
    }
  }
  return await lastValueFrom(transformDataFrame(configs, frames, {
    interpolate: (value: string) => replaceVariables(value, variables),
  }));
}

function applyGrafanaFieldOverrides(
  frames: DataFrame[],
  fieldConfig: FieldConfigSource,
  variables: Record<string, TemplateValue>,
): DataFrame[] {
  return applyFieldOverrides({
    data: frames,
    fieldConfig,
    fieldConfigRegistry: fieldConfigRegistry(),
    replaceVariables: (value: string, scopedVars?: unknown) => replaceVariables(value, variables, scopedVars),
    theme: createTheme(),
    timeZone: "browser",
  });
}

function applyTableSort(frames: DataFrame[], options: JsonObject): DataFrame[] {
  const sortBy = Array.isArray(options.sortBy) ? options.sortBy : [];
  if (!sortBy.length || !isObject(sortBy[0])) {
    return frames;
  }
  const first = sortBy[0];
  const sortName = asText(first.displayName || first.field || first.name);
  if (!sortName) {
    return frames;
  }
  const desc = Boolean(first.desc);
  return frames.map((frame) => {
    const fields = frame.fields;
    const names = fields.map((field) => getFieldDisplayName(field, frame, frames));
    const index = names.indexOf(sortName);
    if (index < 0) {
      return frame;
    }
    const order = Array.from({ length: frame.length }, (_, rowIndex) => rowIndex).sort((left, right) => {
      const diff = compareValues(fields[index].values[left], fields[index].values[right]);
      return desc ? -diff : diff;
    });
    return {
      ...frame,
      fields: fields.map((field) => ({
        ...field,
        values: order.map((rowIndex) => field.values[rowIndex]),
      })),
    };
  });
}

function transformationId(transform: JsonObject): string {
  const spec = isObject(transform.spec) ? transform.spec : {};
  return asText(transform.id || transform.group || spec.id || spec.group);
}

function transformationOptions(transform: JsonObject): JsonObject {
  if (isObject(transform.options)) {
    return transform.options;
  }
  const spec = isObject(transform.spec) ? transform.spec : {};
  return isObject(spec.options) ? spec.options : {};
}

function transformationFilter(transform: JsonObject): DataTransformerConfig["filter"] | undefined {
  const spec = isObject(transform.spec) ? transform.spec : {};
  const filter = isObject(transform.filter) ? transform.filter : isObject(spec.filter) ? spec.filter : undefined;
  const id = filter ? asText(filter.id) : "";
  return id ? { id, options: filter?.options } : undefined;
}

export function dataTransformerConfigs(transformations: JsonObject[]): DataTransformerConfig[] {
  return transformations.flatMap((transformation): DataTransformerConfig[] => {
    const id = transformationId(transformation);
    if (!id) {
      throw new DashboardDataError("transformation has no id");
    }
    const spec = isObject(transformation.spec) ? transformation.spec : {};
    const config: DataTransformerConfig = {
      id,
      options: "options" in transformation ? transformation.options : spec.options ?? {},
    };
    const filter = transformationFilter(transformation);
    if (filter) {
      config.filter = filter;
    }
    const disabled = "disabled" in transformation ? transformation.disabled : spec.disabled;
    if (typeof disabled === "boolean") {
      config.disabled = disabled;
    }
    const topic = "topic" in transformation ? transformation.topic : spec.topic;
    if (typeof topic === "string") {
      config.topic = topic as DataTransformerConfig["topic"];
    }
    return [config];
  });
}

function panelIsTableLike(panel: Panel, frames: DataFrame[]): boolean {
  if (panel.type === "table") {
    return true;
  }
  if (["stat", "timeseries", "piechart", "gauge", "bargauge", "state-timeline"].includes(panel.type)) {
    return false;
  }
  if (panel.transformations.length > 0) {
    return true;
  }
  return frames.some((frame) => {
    const hasNumber = frame.fields.some((field) => field.type === FieldType.number);
    const hasDimension = frame.fields.some((field) => field.type !== FieldType.number && field.type !== FieldType.time);
    return hasNumber && hasDimension;
  });
}

function panelCalcs(panel: Panel): string[] {
  if (panel.type === "stat") {
    const reduceOptions = isObject(panel.options.reduceOptions) ? panel.options.reduceOptions : {};
    if (Array.isArray(reduceOptions.calcs)) {
      return reduceOptions.calcs.map(asText).filter(Boolean);
    }
  }
  const legend = isObject(panel.options.legend) ? panel.options.legend : {};
  if (Array.isArray(legend.calcs)) {
    return legend.calcs.map(asText).filter(Boolean);
  }
  return ["lastNotNull"];
}

function seriesRows(panel: Panel, frames: DataFrame[]): Record<string, string>[] {
  const rows: Record<string, string>[] = [];
  const calcs = panelCalcs(panel);
  for (const frame of frames) {
    for (const field of frame.fields) {
      if (field.type !== FieldType.number) {
        continue;
      }
      const reduced = reduceField({ field, reducers: calcs });
      const row: Record<string, string> = {
        Series: getFieldDisplayName(field, frame, frames),
      };
      for (const calc of calcs) {
        row[calc] = displayValueText(field, (reduced as Record<string, unknown>)[calc] ?? null);
      }
      rows.push(row);
    }
  }
  return rows;
}

function seriesJsonRows(panel: Panel, frames: DataFrame[]): SeriesJson[] {
  const rows: SeriesJson[] = [];
  const calcs = panelCalcs(panel);
  for (const frame of frames) {
    for (const field of frame.fields) {
      if (field.type !== FieldType.number) {
        continue;
      }
      const reduced = reduceField({ field, reducers: calcs }) as Record<string, unknown>;
      const item: SeriesJson = {
        name: getFieldDisplayName(field, frame, frames),
        calcs: {},
        display: {},
      };
      for (const calc of calcs) {
        const value = reduced[calc] ?? null;
        item.calcs[calc] = value;
        item.display[calc] = displayValueText(field, value);
      }
      rows.push(item);
    }
  }
  return rows;
}

function renderTextResult(
  dashboard: JsonObject,
  options: {
    results: PanelResult[];
    variables: Record<string, TemplateValue>;
    start: string;
    end: string;
    maxRows: number;
    maxSeries: number;
    maxWidth: number;
  },
): string {
  const title = asText(dashboard.title) || "(untitled dashboard)";
  const lines = [`Dashboard: ${title}`, `Time: ${options.start} -> ${options.end}`];
  const variableEntries = Object.entries(options.variables).sort(([left], [right]) => left.localeCompare(right));
  if (variableEntries.length) {
    lines.push(`Variables: ${variableEntries.map(([name, value]) => `${name}=${value.display()}`).join(", ")}`);
  }
  lines.push("");

  for (const result of options.results) {
    const panel = result.panel;
    const targetSummary = prepareTargets(panel, options.variables)
      .map((target) => `${target.refId ?? "?"}[${targetDatasource(target)}]`)
      .join(", ");
    lines.push(`Panel ${panel.id}: ${panel.title} (${panel.type})`);
    if (targetSummary) {
      lines.push(`Targets: ${targetSummary}`);
    }
    for (const warning of result.warnings) {
      lines.push(`Warning: ${warning}`);
    }
    for (const error of result.errors) {
      lines.push(`Error: ${error}`);
    }
    if (result.errors.length) {
      lines.push("");
      continue;
    }
    if (!result.frames.length) {
      lines.push("(no data)", "");
      continue;
    }

    if (panelIsTableLike(panel, result.frames)) {
      result.frames.forEach((frame, index) => {
        if (result.frames.length > 1) {
          lines.push(`Frame ${index + 1}: ${frame.name || frame.refId || "(unnamed)"}`);
        }
        lines.push(...renderFrame(frame, result.frames, options.maxRows, options.maxWidth));
      });
    } else {
      const rows = seriesRows(panel, result.frames).slice(0, options.maxSeries);
      if (!rows.length) {
        lines.push("(no numeric series)");
      } else {
        lines.push(...renderTableRows(rows, ["Series", ...panelCalcs(panel)], options.maxSeries, options.maxWidth));
      }
    }
    lines.push("");
  }
  return lines.join("\n");
}

function renderFrame(frame: DataFrame, frames: DataFrame[], maxRows: number, maxWidth: number): string[] {
  const columns = frame.fields.map((field) => getFieldDisplayName(field, frame, frames));
  if (!columns.length || !frame.length) {
    return ["(no rows)"];
  }
  const shownRows: string[][] = [];
  const rowCount = Math.min(frame.length, maxRows);
  for (let rowIndex = 0; rowIndex < rowCount; rowIndex++) {
    shownRows.push(
      frame.fields.map((field) => formatCellText(displayValueText(field, field.values[rowIndex] ?? null), maxWidth)),
    );
  }
  return renderFormattedTableRows(shownRows, columns, frame.length, maxRows);
}

function frameRows(frame: DataFrame, columns?: string[]): JsonObject[] {
  const names = columns || frame.fields.map((field) => getFieldDisplayName(field, frame, [frame]));
  const rows: JsonObject[] = [];
  for (let rowIndex = 0; rowIndex < frame.length; rowIndex++) {
    const row: JsonObject = {};
    frame.fields.forEach((field, fieldIndex) => {
      row[names[fieldIndex]] = field.values[rowIndex] ?? null;
    });
    rows.push(row);
  }
  return rows;
}

function renderTableRows(rows: JsonObject[], columns: string[], maxRows: number, maxWidth: number): string[] {
  const shownRows = rows.slice(0, maxRows);
  const formatted = shownRows.map((row) =>
    columns.map((column) => formatCellText(rawValueText(row[column]), maxWidth))
  );
  return renderFormattedTableRows(formatted, columns, rows.length, maxRows);
}

function renderFormattedTableRows(rows: string[][], columns: string[], totalRows: number, maxRows: number): string[] {
  const widths = columns.map((column, index) => Math.max(column.length, ...rows.map((row) => row[index]?.length || 0)));
  const lines = [
    columns.map((column, index) => column.padEnd(widths[index])).join("  "),
    widths.map((width) => "-".repeat(width)).join("  "),
  ];
  for (const row of rows) {
    lines.push(row.map((value, index) => value.padEnd(widths[index])).join("  "));
  }
  if (totalRows > maxRows) {
    lines.push(`... ${totalRows - maxRows} more row(s)`);
  }
  return lines;
}

function displayValueText(field: Field, value: unknown): string {
  if (field.display) {
    return formattedValueToString(field.display(value));
  }
  return rawValueText(value);
}

function rawValueText(value: unknown): string {
  if (value == null) {
    return "";
  }
  if (typeof value === "number") {
    return Number.isFinite(value) ? value.toPrecision(6).replace(/\.?0+($|e)/, "$1") : String(value);
  }
  return asText(value);
}

function formatCellText(text: string, maxWidth: number): string {
  text = text.replace(/\n/g, "\\n");
  if (text.length > maxWidth) {
    return maxWidth <= 3 ? text.slice(0, maxWidth) : `${text.slice(0, maxWidth - 3)}...`;
  }
  return text;
}

function panelResultToJson(result: PanelResult): PanelJson {
  const panelJson: PanelJson = {
    id: result.panel.id,
    title: result.panel.title,
    type: result.panel.type,
    targetRefs: targetRefs(result.panel),
    errors: result.errors,
    warnings: result.warnings,
    frames: result.frames.map((frame) => {
      const fields = frame.fields.map((field) => getFieldDisplayName(field, frame, result.frames));
      return {
        name: frame.name || "",
        refId: frame.refId || "",
        fields,
        rows: frameRows(frame, fields),
      };
    }),
  };
  if (!panelIsTableLike(result.panel, result.frames)) {
    panelJson.series = seriesJsonRows(result.panel, result.frames);
  }
  return panelJson;
}

function renderPanelList(panels: Panel[]): string {
  const rows = panels.map((panel) => ({
    ID: panel.id,
    Type: panel.type,
    Queries: targetRefs(panel).join(","),
    Title: panel.title,
  }));
  return renderTableRows(rows, ["ID", "Type", "Queries", "Title"], rows.length, 120).join("\n");
}

export function writeOutput(text: string, output?: string): void {
  if (!output || output === "-") {
    console.log(text);
    return;
  }
  const filename = path.isAbsolute(output) ? output : path.resolve(process.cwd(), output);
  fs.mkdirSync(path.dirname(filename), { recursive: true });
  fs.writeFileSync(filename, `${text}\n`, "utf8");
}

function targetRefs(panel: Panel): string[] {
  return panel.targets.map((target, index) => asText(target.refId) || String.fromCharCode("A".charCodeAt(0) + index));
}

function compareValues(left: unknown, right: unknown): number {
  if (left == null && right == null) {
    return 0;
  }
  if (left == null) {
    return 1;
  }
  if (right == null) {
    return -1;
  }
  if (typeof left === "number" && typeof right === "number") {
    return left - right;
  }
  return asText(left).localeCompare(asText(right));
}

function fieldConfigSource(value: unknown): FieldConfigSource {
  const source = isObject(value) ? value : {};
  return {
    defaults: isObject(source.defaults) ? source.defaults : {},
    overrides: Array.isArray(source.overrides) ? source.overrides.filter(isObject) : [],
  } as unknown as FieldConfigSource;
}

function scopedDataContext(scopedVars: unknown):
  | { data: DataFrame[]; frame: DataFrame; field: Field }
  | undefined
{
  if (!isObject(scopedVars)) {
    return undefined;
  }
  const raw = scopedVars.__dataContext;
  if (!isObject(raw) || !isObject(raw.value)) {
    return undefined;
  }
  const value = raw.value;
  if (!Array.isArray(value.data) || !isObject(value.frame) || !isObject(value.field)) {
    return undefined;
  }
  return value as { data: DataFrame[]; frame: DataFrame; field: Field };
}

function parseArgs(argv: string[]): Args {
  const args: Args = {
    dashboard: "",
    listPanels: false,
    panelIds: [],
    panelTypes: [],
    vars: [],
    maxRows: 50,
    maxSeries: 50,
    maxCellWidth: 100,
    includeHiddenTargets: false,
    includeCollapsed: false,
    rawFrames: false,
    timeout: 60,
    concurrency: DEFAULT_QUERY_CONCURRENCY,
    format: "text",
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
    } else if (arg === "--list-panels") {
      args.listPanels = true;
    } else if (arg === "--panel-id") {
      args.panelId = next();
    } else if (arg === "--panel-ids") {
      args.panelIds.push(...parsePanelTypes(next()));
    } else if (arg === "--panel-type") {
      args.panelTypes.push(...parsePanelTypes(next()));
    } else if (arg === "--from") {
      args.start = next();
    } else if (arg === "--to") {
      args.end = next();
    } else if (arg === "--var") {
      args.vars.push(next());
    } else if (arg === "--step") {
      args.step = next();
    } else if (arg === "--max-rows") {
      args.maxRows = parsePositiveInt(arg, next());
    } else if (arg === "--max-series") {
      args.maxSeries = parsePositiveInt(arg, next());
    } else if (arg === "--max-cell-width") {
      args.maxCellWidth = parsePositiveInt(arg, next());
    } else if (arg === "--include-hidden-targets") {
      args.includeHiddenTargets = true;
    } else if (arg === "--include-collapsed") {
      args.includeCollapsed = true;
    } else if (arg === "--raw-frames") {
      args.rawFrames = true;
    } else if (arg === "--timeout") {
      args.timeout = Number.parseFloat(next());
      if (!Number.isFinite(args.timeout) || args.timeout <= 0) {
        throw new DashboardDataError("--timeout expects a positive number");
      }
    } else if (arg === "--concurrency") {
      args.concurrency = parsePositiveInt(arg, next());
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

function parsePositiveInt(name: string, value: string): number {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    throw new DashboardDataError(`${name} expects a positive integer`);
  }
  return parsed;
}

function parsePanelTypes(value: string): string[] {
  const panelTypes = value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  if (!panelTypes.length) {
    throw new DashboardDataError("--panel-type expects a non-empty panel type");
  }
  return panelTypes;
}

function printHelp(): void {
  console.log(`Usage: grafana-inspect data <dashboard.json> [options]

Options:
  --list-panels              List panel ids, titles, types, and query refs
  --panel-id ID              Query only the panel with this id
  --panel-ids ID[,ID...]     Query only these panel ids
  --panel-type TYPE          Filter panels by type, e.g. table or stat; repeatable/comma-separated
  --from TIME                Time range start; defaults to dashboard time
  --to TIME                  Time range end; defaults to dashboard time
  --var NAME=VALUE           Override a dashboard variable; repeatable
  --step DURATION            Set intervalMs for Prometheus/Loki targets, e.g. 30s
  --max-rows N               Max table rows per frame (default: 50)
  --max-series N             Max numeric series rows per panel (default: 50)
  --max-cell-width N         Truncate cells wider than this (default: 100)
  --include-hidden-targets   Also run hidden panel targets
  --include-collapsed        Also include classic panels inside collapsed rows
  --raw-frames               Output raw datasource frames before transformations and field overrides
  --timeout SECONDS          Grafana HTTP timeout in seconds (default: 60)
  --concurrency N            Panel query requests to run in parallel (default: ${DEFAULT_QUERY_CONCURRENCY})
  --format text|json         Output format (default: text)
  --output FILE              Write output to FILE instead of stdout

Environment:
  GRAFANA_URL                 Grafana base URL (default: http://localhost:3000)
  GRAFANA_TOKEN               Optional bearer token; omit for anonymous local Grafana
  GRAFANA_TLS_VERIFY          Verify TLS certificates (default: true)
  GRAFANA_RESOLVE             curl --resolve-style host:port:address rules
  GRAFANA_HOST_HEADER         Optional HTTP Host header
  GRAFANA_SNI_HOSTNAME        Optional TLS SNI hostname

The script also reads these values from .env or mise.toml in the current working directory.`);
}

function isObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function deepClone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function escapeRegex(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function cryptoRandomHex(): string {
  const bytes = new Uint8Array(16);
  globalThis.crypto.getRandomValues(bytes);
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function isCliEntrypoint(): boolean {
  return process.argv[1] ? path.resolve(process.argv[1]) === fileURLToPath(import.meta.url) : false;
}

if (isCliEntrypoint()) {
  main(process.argv.slice(2)).then(
    (code) => {
      process.exitCode = code;
    },
    (error) => {
      const message = error instanceof DashboardDataError ? error.message : (error as Error).stack || String(error);
      console.error(`error: ${message}`);
      process.exitCode = 2;
    },
  );
}
