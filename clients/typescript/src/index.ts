import createClient from "openapi-fetch";
import type { components, paths } from "./schema";

export type PredictRequest = components["schemas"]["PredictRequest"];
export type PredictResponse = components["schemas"]["PredictResponse"];
export type HealthResponse = components["schemas"]["HealthResponse"];
export type Routing = components["schemas"]["Routing"];

export interface LayaClientOptions {
	/** e.g. "http://your-box:11500" */
	baseUrl: string;
	/** Passed through to fetch; use it for timeouts via AbortSignal. */
	fetch?: typeof globalThis.fetch;
}

export class LayaError extends Error {
	constructor(
		readonly status: number,
		readonly detail: unknown,
	) {
		super(`laya ${status}: ${JSON.stringify(detail)}`);
		this.name = "LayaError";
	}
}

interface FetchResult<T> {
	data?: T;
	error?: unknown;
	response: Response;
}

/**
 * Endpoints without a request body have no documented error response, so
 * openapi-fetch types their `error` as `never`. Going through `response.ok`
 * keeps one code path for every endpoint.
 */
function unwrap<T>(result: FetchResult<T>): T {
	const { data, error, response } = result;
	if (!response.ok || data === undefined) {
		throw new LayaError(response.status, error ?? null);
	}
	return data;
}

/**
 * Typed client for laya-serve. Types come from the server's own OpenAPI spec,
 * so they cannot drift: `bun run build` regenerates them.
 */
export function createLayaClient(options: LayaClientOptions) {
	const { baseUrl, fetch } = options;
	const client = createClient<paths>(fetch ? { baseUrl, fetch } : { baseUrl });

	return {
		/** Native inference. Omit `model` to let the router choose. */
		async predict(body: PredictRequest): Promise<PredictResponse> {
			return unwrap(await client.POST("/predict", { body }));
		},

		/** Routing decision only, no forward pass. */
		async route(body: PredictRequest): Promise<Routing> {
			return unwrap(await client.POST("/route", { body }));
		},

		/** Readiness, resident checkpoints and resolved device. */
		async health(): Promise<HealthResponse> {
			return unwrap(await client.GET("/health", {}));
		},
	};
}

export type LayaClient = ReturnType<typeof createLayaClient>;
