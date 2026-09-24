import {
  ApiError,
  DEFAULT_API_BASE_URL,
  createApiClient,
  isAiCosts,
  isAiRunDetail,
  isAiRunList,
  isApplicationBoard,
  isApplicationDetail,
  isCacheStats,
  isCategoryPerformanceList,
  isCostByAgentList,
  isCostByFeatureList,
  isDashboardResponse,
  isFunnelResponse,
  isPromptVersionList,
  isRatesResponse,
  isSkillCorrelationList,
  isTimelineResponse,
  type AiCosts,
  type AiRunDetail,
  type AiRunFilters,
  type AiRunList,
  type AnalyticsRange,
  type ApplicationBoardResponse,
  type ApplicationCreateRequest,
  type ApplicationDetail,
  type ApplicationReorderItem,
  type ApplicationUpdateRequest,
  type CacheStats,
  type CategoryPerformance,
  type CostByAgent,
  type CostByFeature,
  type DashboardResponse,
  type DemoLoginResponse,
  type FunnelResponse,
  type LoginRequest,
  type LoginResponse,
  type ObservabilityRange,
  type PromptVersion,
  type PublicSettingsResponse,
  type RatesResponse,
  type SkillCorrelation,
  type SystemHealthResponse,
  type TimelineResponse,
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

/**
 * `GET /applications/board` (API.md §2.9) — validated before the board can render it.
 *
 * The guard requires all seven columns, so a backend that dropped one fails loudly here
 * instead of producing a board that silently shows six stages.
 */
async function fetchApplicationBoard(
  options: { includeArchived?: boolean } = {},
): Promise<ApplicationBoardResponse> {
  const data = await client.get<unknown>('/applications/board', {
    query: options.includeArchived ? { includeArchived: true } : undefined,
  });
  if (!isApplicationBoard(data)) {
    throw new ApiError({
      code: 'INVALID_RESPONSE',
      message:
        'GET /applications/board 返回的结构与 docs/API.md §2.9 不一致（七列不全或卡片缺少 id/status/company）',
      requestId: null,
      status: 200,
      body: data,
    });
  }
  return data;
}

async function reorderApplications(items: ApplicationReorderItem[]): Promise<unknown> {
  return client.patch<unknown>('/applications/reorder', { items });
}

async function fetchApplication(id: string): Promise<ApplicationDetail> {
  const data = await client.get<unknown>(`/applications/${id}`);
  if (!isApplicationDetail(data)) {
    throw new ApiError({
      code: 'INVALID_RESPONSE',
      message: 'GET /applications/{id} 返回的结构与 docs/API.md §2.9 不一致',
      requestId: null,
      status: 200,
      body: data,
    });
  }
  return data;
}

/* analytics (API.md §2.11) — guarded before a chart can draw them */

async function fetchFunnel(range: AnalyticsRange): Promise<FunnelResponse> {
  const data = await client.get<unknown>('/analytics/funnel', { query: { range } });
  if (!isFunnelResponse(data)) {
    throw new ApiError({
      code: 'INVALID_RESPONSE',
      message: 'GET /analytics/funnel 返回的结构与 docs/API.md §2.11 不一致（缺 meta 或 stages）',
      requestId: null,
      status: 200,
      body: data,
    });
  }
  return data;
}

async function fetchRates(range: AnalyticsRange): Promise<RatesResponse> {
  const data = await client.get<unknown>('/analytics/rates', { query: { range } });
  if (!isRatesResponse(data)) {
    throw new ApiError({
      code: 'INVALID_RESPONSE',
      message: 'GET /analytics/rates 返回的结构与 docs/API.md §2.11 不一致',
      requestId: null,
      status: 200,
      body: data,
    });
  }
  return data;
}

async function fetchSkillCorrelation(range: AnalyticsRange): Promise<SkillCorrelation[]> {
  const data = await client.get<unknown>('/analytics/skill-correlation', { query: { range } });
  if (!isSkillCorrelationList(data)) {
    throw new ApiError({
      code: 'INVALID_RESPONSE',
      message: 'GET /analytics/skill-correlation 返回的结构与 docs/API.md §2.11 不一致',
      requestId: null,
      status: 200,
      body: data,
    });
  }
  return data;
}

async function fetchCategories(range: AnalyticsRange): Promise<CategoryPerformance[]> {
  const data = await client.get<unknown>('/analytics/categories', { query: { range } });
  if (!isCategoryPerformanceList(data)) {
    throw new ApiError({
      code: 'INVALID_RESPONSE',
      message: 'GET /analytics/categories 返回的结构与 docs/API.md §2.11 不一致',
      requestId: null,
      status: 200,
      body: data,
    });
  }
  return data;
}

async function fetchTimeline(range: AnalyticsRange): Promise<TimelineResponse> {
  const data = await client.get<unknown>('/analytics/timeline', { query: { range } });
  if (!isTimelineResponse(data)) {
    throw new ApiError({
      code: 'INVALID_RESPONSE',
      message: 'GET /analytics/timeline 返回的结构与 docs/API.md §2.11 不一致',
      requestId: null,
      status: 200,
      body: data,
    });
  }
  return data;
}

/* AI observability (API.md §2.12) — seven endpoints, one guard each */

/**
 * A rejected shape, with the field that was expected named in the message.
 *
 * The seven observability endpoints return `null`-able measurements (`latencyMs`, `hitRate`), so a
 * missing field and an honest `null` are easy to confuse: the guard rejects the first and the pages
 * print "—" for the second. The message says which one the caller asked for, because a page that
 * renders a wrong shape is worse than a page that refuses to.
 */
function invalidResponse(path: string, expectation: string, body: unknown): ApiError {
  return new ApiError({
    code: 'INVALID_RESPONSE',
    message: `${path} 返回的结构与 docs/API.md §2.12 不一致（${expectation}）`,
    requestId: null,
    status: 200,
    body,
  });
}

async function fetchAiRuns(filters: AiRunFilters = {}): Promise<AiRunList> {
  const data = await client.get<unknown>('/ai-runs', { query: { ...filters } });
  if (!isAiRunList(data)) {
    throw invalidResponse('GET /ai-runs', '缺少 items/total 或某条运行缺少 id/status', data);
  }
  return data;
}

async function fetchAiRun(id: string): Promise<AiRunDetail> {
  const data = await client.get<unknown>(`/ai-runs/${id}`);
  if (!isAiRunDetail(data)) {
    throw invalidResponse('GET /ai-runs/{id}', '缺少步骤链 steps 或调用记录 calls', data);
  }
  return data;
}

async function fetchAiCosts(range: ObservabilityRange): Promise<AiCosts> {
  const data = await client.get<unknown>('/ai-costs', { query: { range } });
  if (!isAiCosts(data)) {
    throw invalidResponse('GET /ai-costs', '缺少 totals 或 dailyBudgetUsd', data);
  }
  return data;
}

async function fetchCostsByAgent(range: ObservabilityRange): Promise<CostByAgent[]> {
  const data = await client.get<unknown>('/ai-costs/by-agent', { query: { range } });
  if (!isCostByAgentList(data)) {
    throw invalidResponse('GET /ai-costs/by-agent', '某一行缺少 agent/runs/tokens', data);
  }
  return data;
}

async function fetchCostsByFeature(range: ObservabilityRange): Promise<CostByFeature[]> {
  const data = await client.get<unknown>('/ai-costs/by-feature', { query: { range } });
  if (!isCostByFeatureList(data)) {
    throw invalidResponse('GET /ai-costs/by-feature', '某一行缺少 feature/workflows', data);
  }
  return data;
}

async function fetchCacheStats(): Promise<CacheStats> {
  const data = await client.get<unknown>('/cache/stats');
  if (!isCacheStats(data)) {
    throw invalidResponse('GET /cache/stats', '缺少 byKind 或 process.hitRate', data);
  }
  return data;
}

async function fetchPrompts(): Promise<PromptVersion[]> {
  const data = await client.get<unknown>('/prompts');
  if (!isPromptVersionList(data)) {
    throw invalidResponse('GET /prompts', '某一行缺少 name/version/isActive', data);
  }
  return data;
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

  /* application tracker (API.md §2.9) */
  applicationBoard: fetchApplicationBoard,
  application: fetchApplication,
  createApplication: (payload: ApplicationCreateRequest) =>
    client.post<unknown>('/applications', payload),
  updateApplication: (id: string, payload: ApplicationUpdateRequest) =>
    client.patch<unknown>(`/applications/${id}`, payload),
  reorderApplications,
  deleteApplication: (id: string) => client.delete<void>(`/applications/${id}`),

  /* analytics (API.md §2.11) */
  funnel: fetchFunnel,
  rates: fetchRates,
  skillCorrelation: fetchSkillCorrelation,
  categories: fetchCategories,
  timeline: fetchTimeline,

  /* AI observability (API.md §2.12) */
  aiRuns: fetchAiRuns,
  aiRun: fetchAiRun,
  aiCosts: fetchAiCosts,
  costsByAgent: fetchCostsByAgent,
  costsByFeature: fetchCostsByFeature,
  cacheStats: fetchCacheStats,
  prompts: fetchPrompts,

  /* public page — the owner's side (API.md §2.13) */
  publicSettings: () => client.get<PublicSettingsResponse>('/public/settings'),
  publishPublicProfile: (payload: { published: boolean; sections?: Record<string, boolean> }) =>
    client.post<PublicSettingsResponse>('/public/publish', payload),
  updatePublicSettings: (payload: {
    sections?: Record<string, boolean>;
    hiddenSkills?: string[];
  }) => client.patch<PublicSettingsResponse>('/public/settings', payload),

  /* escape hatch for phases that have not landed yet */
  request: client.request,
  get: client.get,
  post: client.post,
  patch: client.patch,
} as const;

export { ApiError };
