import { z } from 'zod';

import type { ApiEnvelope, ApiErrorDetail, ApiErrorPayload } from './types';

/**
 * Typed `fetch` wrapper around the CareerForge API.
 *
 * Contract rules enforced here (docs/API.md §1.1):
 *  - every response body is an `ApiEnvelope`; `data` is unwrapped, the envelope is not;
 *  - every failure becomes an `ApiError` carrying `code`, `message`, `requestId`, `status`;
 *  - a transport failure is an `ApiError` too (`code: 'NETWORK_ERROR'`, `status: 0`), so
 *    callers never have to branch on `TypeError` vs API errors — the UI can honestly say
 *    "backend not reachable" without inventing numbers.
 */

/** Default base URL, matching docs/API.md "Base URL". */
export const DEFAULT_API_BASE_URL = 'http://localhost:8000/api/v1';

/** Header used to correlate client logs with the backend `requestId` (API.md §1.1). */
export const REQUEST_ID_HEADER = 'X-Request-Id';

const envelopeSchema = z.object({
  success: z.boolean(),
  data: z.unknown().optional(),
  error: z.unknown().nullable().optional(),
  requestId: z.string().optional(),
});

export type HttpMethod = 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';

export interface ApiErrorInit {
  code: string;
  message: string;
  requestId?: string | null;
  status?: number;
  details?: ApiErrorDetail[];
  body?: unknown;
  isNetworkError?: boolean;
  cause?: unknown;
}

export class ApiError extends Error {
  /** Machine-readable code (API.md §1.6 or a client-side code). */
  readonly code: string;
  /** Correlation id — always rendered in error UIs so a user can report a real trace. */
  readonly requestId: string | null;
  /** HTTP status; `0` means the request never produced a response. */
  readonly status: number;
  readonly details?: ApiErrorDetail[];
  /** Raw body when the response was not a valid envelope (kept for honest debugging). */
  readonly body?: unknown;
  /** `true` when `fetch` itself failed (DNS, connection refused, offline, timeout). */
  readonly isNetworkError: boolean;

  constructor(init: ApiErrorInit) {
    super(init.message, init.cause === undefined ? undefined : { cause: init.cause });
    this.name = 'ApiError';
    this.code = init.code;
    this.requestId = init.requestId ?? null;
    this.status = init.status ?? 0;
    this.details = init.details;
    this.body = init.body;
    this.isNetworkError = init.isNetworkError ?? false;
  }

  /** `NOT_FOUND`-style helpers keep call sites readable. */
  get isUnauthorized(): boolean {
    return this.status === 401 || this.code === 'UNAUTHORIZED' || this.code === 'TOKEN_EXPIRED';
  }
}

export function isApiError(value: unknown): value is ApiError {
  return value instanceof ApiError;
}

/** Anything → a human sentence, for `toast.error(...)` and error panels. */
export function getErrorMessage(error: unknown, fallback = '请求失败，请稍后重试'): string {
  if (isApiError(error)) return error.message;
  if (error instanceof Error && error.message) return error.message;
  if (typeof error === 'string' && error) return error;
  return fallback;
}

export type TokenGetter = () => string | null | undefined | Promise<string | null | undefined>;

export interface ApiClientOptions {
  /** Defaults to `NEXT_PUBLIC_API_BASE_URL` when resolvable, else `DEFAULT_API_BASE_URL`. */
  baseUrl?: string;
  /** Called for every request that opts into auth (`auth !== false`). */
  getToken?: TokenGetter;
  /** Invoked once per 401/TOKEN_EXPIRED response — used to drop a stale session. */
  onUnauthorized?: (error: ApiError) => void;
  /** Test/SSR override; defaults to the global `fetch`. */
  fetchImpl?: typeof fetch;
  defaultHeaders?: Record<string, string>;
  /** Per-request timeout in ms. `0` disables the timeout. Defaults to 20s. */
  timeoutMs?: number;
}

export interface RequestOptions {
  method?: HttpMethod;
  /** JSON body — serialised and sent with `Content-Type: application/json`. */
  json?: unknown;
  /** Raw body (FormData, Blob, …) — sent as-is. */
  body?: BodyInit | null;
  headers?: Record<string, string>;
  /** Query params; `undefined` / `null` values are dropped. */
  query?: Record<string, string | number | boolean | undefined | null>;
  signal?: AbortSignal;
  /** Set `false` for public endpoints (no `Authorization` header). */
  auth?: boolean;
  /** Outgoing correlation id; a fresh one is generated when omitted. */
  requestId?: string;
  timeoutMs?: number;
}

export interface ApiClient {
  readonly baseUrl: string;
  request<T>(path: string, options?: RequestOptions): Promise<T>;
  get<T>(path: string, options?: Omit<RequestOptions, 'method' | 'json' | 'body'>): Promise<T>;
  post<T>(
    path: string,
    json?: unknown,
    options?: Omit<RequestOptions, 'method' | 'json'>,
  ): Promise<T>;
  patch<T>(
    path: string,
    json?: unknown,
    options?: Omit<RequestOptions, 'method' | 'json'>,
  ): Promise<T>;
  delete<T>(path: string, options?: Omit<RequestOptions, 'method' | 'json'>): Promise<T>;
}

/**
 * Best-effort read of `NEXT_PUBLIC_API_BASE_URL`.
 *
 * Deliberately not `process.env.X` syntax: bundlers only inline that exact form, and the
 * shared package is bundler-agnostic. Next.js apps pass the value explicitly
 * (`apps/web/src/lib/api.ts`), so this is only a convenience for Node/SSR callers.
 */
export function resolveApiBaseUrl(explicit?: string): string {
  const trimmed = explicit?.trim();
  if (trimmed) return trimmed.replace(/\/+$/, '');
  const env = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process
    ?.env;
  const fromEnv = env?.['NEXT_PUBLIC_API_BASE_URL']?.trim();
  if (fromEnv) return fromEnv.replace(/\/+$/, '');
  return DEFAULT_API_BASE_URL;
}

function createRequestId(): string {
  const cryptoLike = (globalThis as { crypto?: { randomUUID?: () => string } }).crypto;
  const uuid = cryptoLike?.randomUUID?.();
  if (uuid) return `req_${uuid.replace(/-/g, '')}`;
  return `req_${Math.random().toString(16).slice(2).padEnd(24, '0').slice(0, 24)}`;
}

function buildUrl(baseUrl: string, path: string, query?: RequestOptions['query']): string {
  const normalisedPath = path.startsWith('/') ? path : `/${path}`;
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value === undefined || value === null) continue;
    search.set(key, String(value));
  }
  const qs = search.toString();
  return `${baseUrl}${normalisedPath}${qs ? `?${qs}` : ''}`;
}

function readErrorDetails(value: unknown): ApiErrorDetail[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const details: ApiErrorDetail[] = [];
  for (const entry of value) {
    if (typeof entry !== 'object' || entry === null) continue;
    const record = entry as Record<string, unknown>;
    const field = record['field'];
    const issue = record['issue'];
    if (typeof field === 'string' && typeof issue === 'string') details.push({ field, issue });
  }
  return details.length > 0 ? details : undefined;
}

function readErrorPayload(value: unknown): ApiErrorPayload | undefined {
  if (typeof value !== 'object' || value === null) return undefined;
  const record = value as Record<string, unknown>;
  const code = record['code'];
  const message = record['message'];
  if (typeof code !== 'string') return undefined;
  const payload: ApiErrorPayload = {
    code,
    message: typeof message === 'string' && message ? message : code,
  };
  const details = readErrorDetails(record['details']);
  if (details) payload.details = details;
  return payload;
}

function snippet(text: string, max = 240): string {
  const collapsed = text.replace(/\s+/g, ' ').trim();
  return collapsed.length > max ? `${collapsed.slice(0, max)}…` : collapsed;
}

function combineSignals(
  signal: AbortSignal | undefined,
  timeoutMs: number,
): AbortSignal | undefined {
  const timeoutFactory = (AbortSignal as unknown as { timeout?: (ms: number) => AbortSignal })
    .timeout;
  if (timeoutMs <= 0 || typeof timeoutFactory !== 'function') return signal;
  const timeoutSignal = timeoutFactory(timeoutMs);
  if (!signal) return timeoutSignal;
  const anyFactory = (AbortSignal as unknown as { any?: (s: AbortSignal[]) => AbortSignal }).any;
  if (typeof anyFactory === 'function') return anyFactory([signal, timeoutSignal]);
  return signal;
}

export function createApiClient(options: ApiClientOptions = {}): ApiClient {
  const baseUrl = resolveApiBaseUrl(options.baseUrl);
  const fetchImpl = options.fetchImpl ?? ((...args) => fetch(...args));
  const defaultTimeout = options.timeoutMs ?? 20_000;

  async function request<T>(path: string, requestOptions: RequestOptions = {}): Promise<T> {
    const method = requestOptions.method ?? 'GET';
    const wantsAuth = requestOptions.auth !== false;
    const requestId = requestOptions.requestId ?? createRequestId();
    const timeoutMs = requestOptions.timeoutMs ?? defaultTimeout;

    const headers = new Headers({ Accept: 'application/json', ...options.defaultHeaders });
    for (const [key, value] of Object.entries(requestOptions.headers ?? {})) {
      headers.set(key, value);
    }
    headers.set(REQUEST_ID_HEADER, requestId);

    if (wantsAuth && options.getToken) {
      const token = await options.getToken();
      if (token) headers.set('Authorization', `Bearer ${token}`);
    }

    let body: BodyInit | null | undefined = requestOptions.body;
    if (requestOptions.json !== undefined && body === undefined) {
      headers.set('Content-Type', 'application/json');
      body = JSON.stringify(requestOptions.json);
    }

    const url = buildUrl(baseUrl, path, requestOptions.query);

    let response: Response;
    try {
      response = await fetchImpl(url, {
        method,
        headers,
        body: body ?? null,
        signal: combineSignals(requestOptions.signal, timeoutMs),
        cache: 'no-store',
      });
    } catch (cause) {
      const aborted = cause instanceof Error && cause.name === 'AbortError';
      throw new ApiError({
        code: 'NETWORK_ERROR',
        message: aborted
          ? `请求超时：${timeoutMs}ms 内未收到响应（${url}）`
          : '无法连接到后端服务，请确认 API 已启动',
        requestId,
        status: 0,
        isNetworkError: true,
        cause,
      });
    }

    const headerRequestId = response.headers.get(REQUEST_ID_HEADER) ?? requestId;
    const raw = await response.text();

    if (!raw) {
      if (response.ok) return null as T;
      throw new ApiError({
        code: `HTTP_${response.status}`,
        message: `服务端返回空响应（HTTP ${response.status}）`,
        requestId: headerRequestId,
        status: response.status,
      });
    }

    let parsed: unknown;
    try {
      parsed = JSON.parse(raw);
    } catch (cause) {
      throw new ApiError({
        code: 'INVALID_RESPONSE',
        message: `服务端返回的不是 JSON（HTTP ${response.status}）：${snippet(raw)}`,
        requestId: headerRequestId,
        status: response.status,
        body: raw,
        cause,
      });
    }

    const envelope = envelopeSchema.safeParse(parsed);
    if (!envelope.success) {
      throw new ApiError({
        code: 'INVALID_RESPONSE',
        message: `响应缺少标准信封字段 { success, data, error, requestId }（HTTP ${response.status}）`,
        requestId: headerRequestId,
        status: response.status,
        body: parsed,
      });
    }

    const body_ = envelope.data as ApiEnvelope<unknown>;
    const envelopeRequestId = body_.requestId || headerRequestId;
    const errorPayload = readErrorPayload(body_.error);

    if (!response.ok || body_.success !== true) {
      const error = new ApiError({
        code: errorPayload?.code ?? `HTTP_${response.status}`,
        message: errorPayload?.message ?? `请求失败（HTTP ${response.status}）`,
        requestId: envelopeRequestId,
        status: response.status,
        details: errorPayload?.details,
        body: parsed,
      });
      if (error.isUnauthorized) options.onUnauthorized?.(error);
      throw error;
    }

    return body_.data as T;
  }

  return {
    baseUrl,
    request,
    get: (path, opts) => request(path, { ...opts, method: 'GET' }),
    post: (path, json, opts) => request(path, { ...opts, method: 'POST', json }),
    patch: (path, json, opts) => request(path, { ...opts, method: 'PATCH', json }),
    delete: (path, opts) => request(path, { ...opts, method: 'DELETE' }),
  };
}
