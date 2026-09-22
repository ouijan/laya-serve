import createClient from "openapi-fetch";
import type { components, paths } from "./schema";

/**
 * Type names mirror the TypeSafe SDK (docs.typesafe.ai) so moving between
 * this server and the hosted API is a change of import, not of code.
 */
export type Question = components["schemas"]["Question"];
export type SystemOneRequest = components["schemas"]["SystemOneRequest"];
export type SystemOneResponse = components["schemas"]["SystemOneResponse"];
export type ChoiceAnswer = components["schemas"]["ChoiceAnswer"];
export type ScoreAnswer = components["schemas"]["ScoreAnswer"];
export type NoulAnswer = components["schemas"]["NoulAnswer"];
export type Answer = ChoiceAnswer | ScoreAnswer | NoulAnswer;
export type Usage = components["schemas"]["Usage"];
export type HealthResponse = components["schemas"]["HealthResponse"];

/** laya extra: which checkpoint served the request, and why. */
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
 * Typed client for laya-serve. Types are generated from the server's own
 * OpenAPI spec, so they cannot drift: `bun run build` regenerates them.
 */
export function createLayaClient(options: LayaClientOptions) {
	const { baseUrl, fetch } = options;
	const client = createClient<paths>(fetch ? { baseUrl, fetch } : { baseUrl });

	return {
		/** Evaluate typed questions against a state in one forward pass. */
		async systemOne(body: SystemOneRequest): Promise<SystemOneResponse> {
			return unwrap(await client.POST("/v1/systemone", { body }));
		},

		/** Which checkpoint would serve this, without a forward pass. */
		async route(body: SystemOneRequest): Promise<Routing> {
			return unwrap(await client.POST("/v1/route", { body }));
		},

		/** Readiness, resident checkpoints and resolved device. */
		async health(): Promise<HealthResponse> {
			return unwrap(await client.GET("/health", {}));
		},
	};
}

export type LayaClient = ReturnType<typeof createLayaClient>;

/** Narrow an answer by its `type` discriminator. */
export function isChoice(answer: Answer): answer is ChoiceAnswer {
	return answer.type === "choice";
}

export function isScore(answer: Answer): answer is ScoreAnswer {
	return answer.type === "score";
}

export function isNoul(answer: Answer): answer is NoulAnswer {
	return answer.type === "noul";
}
