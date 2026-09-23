import {
  ApiError,
  DEFAULT_API_BASE_URL,
  createApiClient,
  isDashboardResponse,
  type DashboardResponse,
  type DemoLoginResponse,
  type LoginRequest,
  type LoginResponse,
  type SystemHealthResponse,
  type User,
} from '@careerforge/shared';

import { clearSession, getAccessToken } from './auth';

/**
 * The app's single API entry point.
 *
 * `NEXT_PUBLIC_API_BASE_URL` must be read with the literal `process.env.X` syntax so
 * Next inlines it at build time; the shared client keeps `DEFAULT_API_BASE_URL` as the
 * fallback (`http://localhost:8000/api/v1`, docs/API.md §Base URL).
 */
export const API_BASE_URL: string =
  process.env.NEXT_PUBLIC_API_BASE_URL?.trim() || DEFAULT_API_BASE_URL;

const client = createApiClient({
  baseUrl: API_BASE_URL,
  getToken: () => getAccessToken(),
  // A stale/expired token is dropped locally so the auth guard can bounce to /login.
  onUnauthorized: () => clearSession(),
});

/** `GET /dashboard` (API.md §2.10) — validated before the UI can render numbers. */
async function fetchDashboard(): Promise<DashboardResponse> {
  const data = await client.get<unknown>('/dashboard');
  if (!isDashboardResponse(data)) {
    throw new ApiError({
      code: 'INVALID_RESPONSE',
      message:
        'GET /dashboard 返回的结构与 docs/API.md §2.10 不一致（缺少 profileStrength.score 或 stats 六项指标）',
      requestId: null,
      status: 200,
      body: data,
    });
  }
  return data;
}

/**
 * `GET /system/health` (API.md §2.13) — the body is not frozen by the spec, so the raw
 * payload is returned and normalised in the UI, which shows it verbatim when it is not
 * an expected shape rather than guessing a health status.
 */
async function fetchSystemHealth(): Promise<SystemHealthResponse> {
  return client.get<SystemHealthResponse>('/system/health', { auth: false });
}

export const api = {
  baseUrl: API_BASE_URL,

  /* auth (API.md §2.1) */
  demoLogin: () => client.post<DemoLoginResponse>('/auth/demo', undefined, { auth: false }),
  login: (payload: LoginRequest) =>
    client.post<LoginResponse>('/auth/login', payload, { auth: false }),
  me: () => client.get<User>('/auth/me'),

  /* dashboards */
  dashboard: fetchDashboard,
  systemHealth: fetchSystemHealth,

  /* escape hatch for phases that have not landed yet */
  request: client.request,
  get: client.get,
  post: client.post,
  patch: client.patch,
} as const;

export { ApiError };
