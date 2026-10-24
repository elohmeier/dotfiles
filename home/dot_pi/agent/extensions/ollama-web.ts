import {
	DEFAULT_MAX_BYTES,
	DEFAULT_MAX_LINES,
	type ExtensionAPI,
	type ExtensionContext,
	formatSize,
	truncateHead,
} from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

// Ollama Cloud web search/fetch (https://docs.ollama.com/capabilities/web-search).
// The key comes from the ollama-cloud provider in models.json, else OLLAMA_API_KEY.
const BASE_URL = "https://ollama.com/api";
const PROVIDER = "ollama-cloud";

async function apiKey(ctx: ExtensionContext): Promise<string> {
	const key = (await ctx.modelRegistry.getApiKeyForProvider(PROVIDER).catch(() => undefined)) ?? process.env.OLLAMA_API_KEY;
	if (!key) throw new Error(`No Ollama API key: configure the ${PROVIDER} provider in models.json or set OLLAMA_API_KEY`);
	return key;
}

async function call<T>(ctx: ExtensionContext, path: string, body: unknown, signal?: AbortSignal): Promise<T> {
	const response = await fetch(`${BASE_URL}/${path}`, {
		method: "POST",
		headers: { Authorization: `Bearer ${await apiKey(ctx)}`, "Content-Type": "application/json" },
		body: JSON.stringify(body),
		signal,
	});
	if (!response.ok) {
		const text = await response.text().catch(() => "");
		throw new Error(`Ollama ${path} failed (${response.status}): ${text || response.statusText}`);
	}
	return (await response.json()) as T;
}

function limit(text: string): string {
	const t = truncateHead(text, { maxLines: DEFAULT_MAX_LINES, maxBytes: DEFAULT_MAX_BYTES });
	return t.truncated ? `${t.content}\n\n[Truncated to ${formatSize(DEFAULT_MAX_BYTES)} / ${DEFAULT_MAX_LINES} lines]` : t.content;
}

interface SearchResponse {
	results: { title: string; url: string; content: string }[];
}

interface FetchResponse {
	title: string;
	content: string;
	links: string[];
}

export default function (pi: ExtensionAPI) {
	pi.registerTool({
		name: "web_search",
		label: "Web Search",
		description: "Search the web for current information via Ollama Cloud. Returns titles, URLs, and page excerpts.",
		promptSnippet: "Search the web for current information",
		parameters: Type.Object({
			query: Type.String({ description: "Search query" }),
			max_results: Type.Optional(Type.Integer({ description: "Number of results, 1-10 (default 5)", minimum: 1, maximum: 10 })),
		}),
		async execute(_toolCallId, params, signal, _onUpdate, ctx) {
			const data = await call<SearchResponse>(ctx, "web_search", { query: params.query, max_results: params.max_results ?? 5 }, signal);
			const text = data.results.length
				? data.results.map((r, i) => `## ${i + 1}. ${r.title}\n${r.url}\n\n${r.content.trim()}`).join("\n\n")
				: "No results.";
			return {
				content: [{ type: "text", text: limit(text) }],
				details: { query: params.query, urls: data.results.map((r) => r.url) },
			};
		},
	});

	pi.registerTool({
		name: "web_fetch",
		label: "Web Fetch",
		description: "Fetch a web page via Ollama Cloud and return its title, main content as text, and links.",
		promptSnippet: "Fetch the content of a web page by URL",
		parameters: Type.Object({
			url: Type.String({ description: "URL to fetch" }),
		}),
		async execute(_toolCallId, params, signal, _onUpdate, ctx) {
			const data = await call<FetchResponse>(ctx, "web_fetch", { url: params.url }, signal);
			const links = data.links?.length ? `\n\n## Links\n${data.links.join("\n")}` : "";
			return {
				content: [{ type: "text", text: limit(`# ${data.title}\n${params.url}\n\n${data.content.trim()}${links}`) }],
				details: { url: params.url, title: data.title, links: data.links?.length ?? 0 },
			};
		},
	});
}
