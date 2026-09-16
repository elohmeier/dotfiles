import * as dns from "node:dns";
import * as fs from "node:fs";
import * as http from "node:http";
import * as https from "node:https";
import { DashboardDataError } from "./errors.js";
const DEFAULT_GRAFANA_URL = "http://localhost:3000";
interface ResolveRule {
  host: string;
  port: number;
  address: string;
}

export interface GrafanaConfig {
  baseUrl: string;
  verify: boolean;
  hostHeader?: string;
  sniHostname?: string;
  resolve: ResolveRule[];
}

export function grafanaConfig(): GrafanaConfig {
  const normalUrl = env("GRAFANA_URL", DEFAULT_GRAFANA_URL) || DEFAULT_GRAFANA_URL;
  const normalHost = new URL(normalUrl).hostname;
  const resolve = parseResolveRules(env("GRAFANA_RESOLVE"));

  return {
    baseUrl: normalUrl.replace(/\/+$/, ""),
    verify: envBool("GRAFANA_TLS_VERIFY", true),
    hostHeader: env("GRAFANA_HOST_HEADER", resolve.length ? normalHost : undefined),
    sniHostname: env("GRAFANA_SNI_HOSTNAME"),
    resolve,
  };
}

export function grafanaToken(): string {
  return env("GRAFANA_TOKEN") || "";
}

function env(name: string, defaultValue?: string): string | undefined {
  const value = process.env[name];
  return value == null || value === "" ? defaultValue : value;
}

function envBool(name: string, defaultValue: boolean): boolean {
  const value = env(name);
  if (value == null) {
    return defaultValue;
  }
  const normalized = value.trim().toLowerCase();
  if (["1", "true", "yes", "y", "on"].includes(normalized)) {
    return true;
  }
  if (["0", "false", "no", "n", "off"].includes(normalized)) {
    return false;
  }
  throw new DashboardDataError(`${name} must be a boolean value, got ${JSON.stringify(value)}`);
}

function parseResolveRules(value?: string): ResolveRule[] {
  if (!value) {
    return [];
  }
  return value
    .trim()
    .split(/[,\s]+/)
    .filter(Boolean)
    .map((item) => {
      const [host, portText, addressWithRest] = item.split(":", 3);
      if (!host || !portText || !addressWithRest) {
        throw new DashboardDataError(
          `GRAFANA_RESOLVE entries must use curl --resolve syntax 'host:port:address', got ${JSON.stringify(item)}`,
        );
      }
      const port = Number.parseInt(portText, 10);
      if (!Number.isInteger(port) || port <= 0 || port > 65535) {
        throw new DashboardDataError(`GRAFANA_RESOLVE port out of range in ${JSON.stringify(item)}`);
      }
      const address = addressWithRest.startsWith("[") && addressWithRest.endsWith("]")
        ? addressWithRest.slice(1, -1)
        : addressWithRest;
      return { host, port, address };
    });
}

export async function grafanaJsonRequest(
  config: GrafanaConfig,
  token: string,
  request: { method: "GET" | "POST"; pathname: string; search?: string; body?: unknown; timeout: number },
): Promise<{ statusCode: number; text: string; json: unknown }> {
  const attempts = 3;
  let lastError: unknown;
  for (let attempt = 1; attempt <= attempts; attempt++) {
    try {
      return await grafanaJsonRequestOnce(config, token, request);
    } catch (error) {
      lastError = error;
      if (attempt === attempts || !isTransientRequestError(error)) {
        throw error;
      }
      await sleep(250 * attempt);
    }
  }
  throw lastError;
}

async function grafanaJsonRequestOnce(
  config: GrafanaConfig,
  token: string,
  request: { method: "GET" | "POST"; pathname: string; search?: string; body?: unknown; timeout: number },
): Promise<{ statusCode: number; text: string; json: unknown }> {
  const base = new URL(config.baseUrl);
  const isHttps = base.protocol === "https:";
  const body = request.body === undefined ? undefined : JSON.stringify(request.body);
  const port = base.port ? Number.parseInt(base.port, 10) : isHttps ? 443 : 80;
  const headers: Record<string, string | number> = {
    Accept: "application/json",
  };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    headers["Content-Length"] = Buffer.byteLength(body);
  }
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  } else if (process.env.GRAFANA_USERNAME && process.env.GRAFANA_PASSWORD) {
    headers.Authorization = `Basic ${Buffer.from(`${process.env.GRAFANA_USERNAME}:${process.env.GRAFANA_PASSWORD}`).toString("base64")}`;
  }
  if (config.hostHeader) {
    headers.Host = config.hostHeader;
  }

  const options: http.RequestOptions | https.RequestOptions = {
    protocol: base.protocol,
    hostname: base.hostname,
    port,
    method: request.method,
    path: `${base.pathname.replace(/\/$/, "")}${request.pathname}${request.search || ""}`,
    headers,
    timeout: request.timeout * 1000,
    lookup: (hostname, lookupOptions, callback) => {
      const options = typeof lookupOptions === "object" ? lookupOptions : {};
      const family = options.family === 6 ? 6 : 4;
      const match = config.resolve.find((rule) =>
        rule.host.toLowerCase() === hostname.toLowerCase() && rule.port === port
      );
      if (match) {
        if (options.all) {
          callback(null, [{ address: match.address, family }] as never, family);
        } else {
          callback(null, match.address, family);
        }
        return;
      }
      dns.lookup(hostname, lookupOptions, callback);
    },
  };
  if (isHttps) {
    (options as https.RequestOptions).rejectUnauthorized = config.verify;
    if (process.env.GRAFANA_CA_FILE) (options as https.RequestOptions).ca = fs.readFileSync(process.env.GRAFANA_CA_FILE);
    (options as https.RequestOptions).servername = config.sniHostname || base.hostname;
  }

  return new Promise((resolve, reject) => {
    const req = (isHttps ? https : http).request(options, (res) => {
      const chunks: Buffer[] = [];
      res.on("data", (chunk) => chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk)));
      res.on("end", () => {
        const text = Buffer.concat(chunks).toString("utf8");
        let json: unknown;
        try {
          json = JSON.parse(text);
        } catch {
          json = undefined;
        }
        resolve({ statusCode: res.statusCode || 0, text, json });
      });
    });
    req.on("timeout", () => req.destroy(new Error(`request timed out after ${request.timeout}s`)));
    req.on("error", reject);
    if (body !== undefined) {
      req.write(body);
    }
    req.end();
  });
}

function isTransientRequestError(error: unknown): boolean {
  if (!(error instanceof Error)) {
    return false;
  }
  const code = (error as NodeJS.ErrnoException).code || "";
  return (
    code === "ECONNRESET"
    || code === "ETIMEDOUT"
    || code === "EPIPE"
    || /socket hang up|request timed out|read ECONNRESET/i.test(error.message)
  );
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
