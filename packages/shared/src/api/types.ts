/**
 * API contract types — a direct mirror of `docs/API.md` (v1.0, frozen spec).
 *
 * Conventions that are enforced everywhere in this file:
 *  - every response is wrapped in `ApiEnvelope` (`{ success, data, error, requestId }`);
 *  - `requestId` is always present and is the correlation id used in error UIs;
 *  - field names/shapes are copied verbatim from the API document — do not "improve" them
 *    here, change `docs/API.md` first (single source of truth).
 */

/* ------------------------------------------------------------------ *
 * 1. Envelope + errors (API.md §1.1, §1.6)
 * ------------------------------------------------------------------ */

/** Error codes frozen in API.md §1.6. Kept as a union so `switch` stays exhaustive. */
export type KnownApiErrorCode =
  | 'VALIDATION_ERROR'
  | 'UNSUPPORTED_FILE_TYPE'
  | 'FILE_TOO_LARGE'
  | 'UNAUTHORIZED'
  | 'TOKEN_EXPIRED'
  | 'FORBIDDEN'
  | 'NOT_FOUND'
  | 'CONFLICT'
  | 'PAYLOAD_TOO_LARGE'
  | 'CLAIM_REJECTED'
  | 'RATE_LIMITED'
  | 'AI_BUDGET_EXCEEDED'
  | 'AI_PROVIDER_ERROR'
  | 'GITHUB_ERROR'
  | 'DEPENDENCY_UNAVAILABLE'
  | 'AI_PROVIDER_UNAVAILABLE'
  | 'INTERNAL_ERROR';

/**
 * Codes the *client* synthesises; the backend never sends these.
 * They exist so "backend down" and "garbage response" are distinguishable in the UI.
 */
export type ClientSideErrorCode = 'NETWORK_ERROR' | 'INVALID_RESPONSE';

export type ApiErrorCode = KnownApiErrorCode | ClientSideErrorCode;

/** `details` of a `VALIDATION_ERROR` (API.md §1.1). */
export interface ApiErrorDetail {
  field: string;
  issue: string;
}

export interface ApiErrorPayload {
  /** Unknown codes are tolerated (open union keeps autocomplete for the known ones). */
  code: KnownApiErrorCode | (string & {});
  message: string;
  details?: ApiErrorDetail[];
}

/** The one and only response envelope (API.md §1.1). */
export interface ApiEnvelope<T> {
  success: boolean;
  data: T | null;
  error: ApiErrorPayload | null;
  requestId: string;
}

/** Degradation/observability block carried by AI-ish responses (API.md §1.8). */
export interface ApiMeta {
  provider?: string;
  model?: string;
  promptVersion?: string;
  /** `true` = answered by a fallback provider (heuristic). Must be surfaced, never hidden. */
  degraded?: boolean;
  cacheHit?: boolean;
  confidence?: number;
  tookMs?: number;
}

/* ------------------------------------------------------------------ *
 * 2. Pagination + async tasks (API.md §1.3, §1.4)
 * ------------------------------------------------------------------ */

export interface Paginated<T> {
  items: T[];
  nextCursor: string | null;
  total: number;
}

export type TaskStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';

export interface TaskAccepted {
  taskId: string;
  status: TaskStatus | (string & {});
  streamUrl?: string;
}

/* ------------------------------------------------------------------ *
 * 3. Auth + user (API.md §2.1)
 * ------------------------------------------------------------------ */

/** `local` = Local Mode (raw resume text never leaves the device). */
export type StorageScope = 'cloud' | 'local';

export interface User {
  id: string;
  email: string;
  displayName: string;
  isDemo: boolean;
  storageScope: StorageScope;
}

/** Token bundle returned by /auth/demo, /auth/login and /auth/refresh. */
export interface AuthTokens {
  accessToken: string;
  refreshToken: string;
  /** Access-token lifetime in seconds (API.md §1.2: 1800 = 30 min). */
  expiresIn: number;
}

/** `data` of `POST /auth/demo` — copied from API.md §2.1. */
export interface DemoLoginResponse extends AuthTokens {
  user: User;
}

/**
 * `POST /auth/login` is not spelled out field-by-field in API.md §2.1; the document
 * shows the demo response only. The frontend assumes the same token+user envelope and
 * treats a mismatch as a contract drift to be fixed in `docs/API.md` (not patched here).
 */
export type LoginResponse = DemoLoginResponse;

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest extends LoginRequest {
  displayName?: string;
}

export interface RefreshRequest {
  refreshToken: string;
}

/* ------------------------------------------------------------------ *
 * 4. Dashboard aggregate (API.md §2.10)
 * ------------------------------------------------------------------ */

export interface DashboardProfileStrength {
  score: number;
  delta7d?: number;
}

/** Fractions are 0..1 for the three coverage/match metrics; the rest are counts. */
export interface DashboardStats {
  evidenceCoverage: number;
  skillCoverage: number;
  resumeMatch: number;
  applications: number;
  interviews: number;
  offers: number;
}

export interface SkillRadarPoint {
  skill: string;
  user: number;
  market: number;
}

export interface DashboardRecentJob {
  jobId: string;
  company: string;
  role: string;
  matchScore: number;
  status: string;
}

export interface DashboardNextAction {
  type: string;
  title: string;
  /** ISO-8601 timestamp. */
  at: string;
}

export interface DashboardMeta {
  cacheHit?: boolean;
  tookMs?: number;
  /**
   * Metric key → the phase that will provide its data source.
   *
   * A zero on a dashboard reads as "you have none". For a metric whose feature does not
   * exist yet (the application tracker), that would be a claim the system cannot make, so
   * the API names it here and the UI says "not tracked yet" instead of showing the zero.
   */
  unavailable?: Record<string, string>;
  /** Metric key → the definition actually used to compute it (`口径`), shipped with the number. */
  definitions?: Record<string, string>;
}

/** `data` of `GET /dashboard` (API.md §2.10). */
export interface DashboardResponse {
  profileStrength: DashboardProfileStrength;
  stats: DashboardStats;
  skillsRadar: SkillRadarPoint[];
  recentJobs: DashboardRecentJob[];
  nextActions: DashboardNextAction[];
  meta?: DashboardMeta;
}

/* ------------------------------------------------------------------ *
 * 5. System health (API.md §2.13)
 * ------------------------------------------------------------------ */

export type ServiceHealthStatus = 'ok' | 'degraded' | 'down' | 'unknown';

export interface ServiceHealthEntry {
  /** Stable service key, e.g. `api` · `postgres` · `redis` · `vector_store` · `llm_provider`. */
  name: string;
  status: ServiceHealthStatus;
  /** Free-form human explanation (redacted by the backend, never secrets). */
  detail?: string;
  latencyMs?: number;
  version?: string;
}

/**
 * NOTE (contract gap): API.md §2.13 describes `GET /system/health` as
 * "API / DB / Redis / Vector / LLM provider 状态" but does not freeze the body.
 * This is the frontend's assumed shape; `apps/web` normalises defensively and shows the
 * raw payload when it does not match, instead of inventing a health status.
 */
export interface SystemHealthResponse {
  status: ServiceHealthStatus;
  services: ServiceHealthEntry[];
  checkedAt?: string;
  version?: Record<string, string> | null;
  meta?: ApiMeta;
}

/* ------------------------------------------------------------------ *
 * 6. Domain enums shared across later phases (API.md §2.5)
 * ------------------------------------------------------------------ */

export type ClaimStatus = 'supported' | 'partially_supported' | 'unsupported' | 'contradicted';

export type EvidenceKind = 'repo_file' | 'commit' | 'readme' | 'doc' | 'self_report' | 'manual';
