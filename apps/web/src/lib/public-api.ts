import {
  DEFAULT_API_BASE_URL,
  isPublicEvidenceList,
  isPublicProfileResponse,
  type PublicEvidence,
  type PublicProfileResponse,
} from '@careerforge/shared';

/**
 * Reads for the public candidate page.
 *
 * Deliberately **not** built on `lib/api.ts`: that client attaches the session token from
 * `localStorage`, and this page is the one surface that must render identically for a stranger
 * with no account, no token and no cookies. A plain `fetch` with `cache: 'no-store'` also lets
 * the page be a server component — no hydration round-trip before the content exists, which is
 * what makes a shared link open with the candidate's evidence already on screen.
 */
const BASE_URL: string = process.env.NEXT_PUBLIC_API_BASE_URL?.trim() || DEFAULT_API_BASE_URL;

export interface PublicFetchResult<T> {
  data: T | null;
  status: number;
}

async function getJson<T>(path: string): Promise<PublicFetchResult<T>> {
  try {
    const response = await fetch(`${BASE_URL}${path}`, {
      headers: { Accept: 'application/json' },
      cache: 'no-store',
    });
    if (!response.ok) return { data: null, status: response.status };
    const envelope = (await response.json()) as { success?: boolean; data?: unknown };
    return { data: (envelope.data ?? null) as T, status: response.status };
  } catch {
    // A failed fetch is reported as 0 — "could not ask" is not the same as "not found", and the
    // page distinguishes them rather than showing a 404 for a backend that is not running.
    return { data: null, status: 0 };
  }
}

export async function fetchPublicProfile(
  slug: string,
): Promise<PublicFetchResult<PublicProfileResponse>> {
  const result = await getJson<unknown>(`/public/candidate/${encodeURIComponent(slug)}`);
  if (result.data === null) return { data: null, status: result.status };
  if (!isPublicProfileResponse(result.data)) {
    return { data: null, status: 502 };
  }
  return { data: result.data, status: result.status };
}

export async function fetchPublicSkillEvidence(
  slug: string,
  skillId: string,
): Promise<PublicFetchResult<PublicEvidence[]>> {
  const result = await getJson<unknown>(
    `/public/candidate/${encodeURIComponent(slug)}/evidence/${encodeURIComponent(skillId)}`,
  );
  if (result.data === null) return { data: null, status: result.status };
  if (!isPublicEvidenceList(result.data)) return { data: null, status: 502 };
  return { data: result.data, status: result.status };
}

export const PUBLIC_API_BASE_URL = BASE_URL;
