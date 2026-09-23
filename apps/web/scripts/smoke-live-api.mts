/**
 * Contract smoke test: run the real frontend client against a running API.
 *
 * The dashboard, the evidence graph and the job list are fetched through exactly the code
 * the browser uses — `@careerforge/shared`'s client plus its runtime guards — so a response
 * shape that drifted from `docs/API.md` fails here instead of rendering an empty page.
 *
 * Run it against a live backend:
 *
 *     pnpm --filter @careerforge/web smoke:api
 *     API_BASE_URL=http://127.0.0.1:8001/api/v1 pnpm --filter @careerforge/web smoke:api
 *
 * Exits non-zero on the first contract violation, with the requestId of the failing call —
 * which is the point of having a correlation id in the first place.
 *
 * The imports reach into `packages/shared/src/api/*.ts` rather than `@careerforge/shared`
 * on purpose: that package's entry re-exports `./api`, a *directory* import, which Next and
 * every bundler resolve but Node's ESM loader does not. The files below are the same client
 * and the same guards the app imports; only the specifier differs.
 */

import {
  ApiError,
  DEFAULT_API_BASE_URL,
  createApiClient,
} from '../../../packages/shared/src/api/client.ts';
import {
  isApplicationBoard,
  isDashboardResponse,
  isRecord,
  toServiceHealthStatus,
} from '../../../packages/shared/src/api/guards.ts';
import {
  APPLICATION_STATUSES,
  type ApplicationBoardResponse,
  type ApplicationStatus,
} from '../../../packages/shared/src/api/types.ts';

const baseUrl = process.env['API_BASE_URL']?.trim() || DEFAULT_API_BASE_URL;

interface Check {
  name: string;
  detail: string;
}

const checks: Check[] = [];
let token: string | null = null;

const client = createApiClient({
  baseUrl,
  getToken: () => token,
  onUnauthorized: () => {
    console.error('  ! the API rejected the demo token');
  },
});

function pass(name: string, detail: string): void {
  checks.push({ name, detail });
  console.log(`  ok   ${name.padEnd(22)} ${detail}`);
}

function fail(name: string, error: unknown): never {
  if (error instanceof ApiError) {
    console.error(
      `  FAIL ${name.padEnd(22)} ${error.code} (status ${error.status}` +
        `${error.requestId ? `, requestId ${error.requestId}` : ''}): ${error.message}`,
    );
  } else {
    console.error(`  FAIL ${name.padEnd(22)} ${String(error)}`);
  }
  process.exit(1);
}

async function main(): Promise<void> {
  console.log(`CareerForge API contract smoke test → ${baseUrl}\n`);

  /* 1. Demo login — the same call the login page makes. */
  try {
    const session = await client.post<{ accessToken: string; user: { email: string } }>(
      '/auth/demo',
      undefined,
      { auth: false },
    );
    token = session.accessToken;
    pass('POST /auth/demo', `signed in as ${session.user.email}`);
  } catch (error) {
    fail('POST /auth/demo', error);
  }

  /* 2. The home page's single aggregate, validated by the guard the UI uses. */
  try {
    const raw = await client.get<unknown>('/dashboard');
    if (!isDashboardResponse(raw)) {
      throw new Error(
        'GET /dashboard does not satisfy isDashboardResponse (docs/API.md §2.10)',
      );
    }
    const unavailable = isRecord(raw.meta) ? Object.keys(raw.meta['unavailable'] ?? {}) : [];
    pass(
      'GET /dashboard',
      `strength=${raw.profileStrength.score} evidence=${raw.stats.evidenceCoverage} ` +
        `match=${raw.stats.resumeMatch} radar=${raw.skillsRadar.length} ` +
        `unavailable=[${unavailable.join(',')}]`,
    );
  } catch (error) {
    fail('GET /dashboard', error);
  }

  /* 3. Health — the status is normalised by the shared helper, as the system page does. */
  try {
    const health = await client.get<Record<string, unknown>>('/system/health', { auth: false });
    const services = Array.isArray(health['services']) ? health['services'] : [];
    const summary = services
      .filter(isRecord)
      .map((entry) => `${String(entry['name'])}=${toServiceHealthStatus(entry['status'])}`)
      .join(' ');
    pass('GET /system/health', summary || 'no per-service detail');
  } catch (error) {
    fail('GET /system/health', error);
  }

  /* 4. The evidence graph — the endpoint the canvas will read. */
  try {
    const graph = await client.get<Record<string, unknown>>('/evidence-graph?limit=200');
    const nodes = Array.isArray(graph['nodes']) ? graph['nodes'] : [];
    const edges = Array.isArray(graph['edges']) ? graph['edges'] : [];
    const unresolved = graph['unresolvedNodeCount'];
    pass(
      'GET /evidence-graph',
      `nodes=${String(graph['nodeCount'])} edges=${String(graph['edgeCount'])} ` +
        `payload=${nodes.length}/${edges.length} unresolved=${String(unresolved)}`,
    );
  } catch (error) {
    fail('GET /evidence-graph', error);
  }

  /* 5. Jobs and a match, if any posting exists. */
  try {
    const listing = await client.get<Record<string, unknown>>('/jobs?limit=5');
    const items = Array.isArray(listing['items']) ? listing['items'] : [];
    pass('GET /jobs', `total=${String(listing['total'])} items=${items.length}`);

    const first = items.filter(isRecord)[0];
    if (first && typeof first['id'] === 'string') {
      const match = await client.get<Record<string, unknown>>(`/jobs/${first['id']}/match`);
      const dimensions = isRecord(match['dimensions']) ? Object.keys(match['dimensions']) : [];
      pass(
        `GET /jobs/:id/match`,
        `score=${String(match['score'])} dimensions=[${dimensions.join(',')}]`,
      );
    }
  } catch (error) {
    fail('GET /jobs', error);
  }

  /* 6. The application board: create → guard → move → reorder → delete.
   *
   * This is the only check that writes. It cleans up after itself, because a smoke test that
   * leaves cards behind changes the dashboard numbers of the next run — and a test that
   * alters the thing it measures eventually fails for the wrong reason. */
  try {
    const created = await client.post<Record<string, unknown>>('/applications', {
      company: 'Smoke 测试公司',
      role: '契约测试岗',
      status: 'wishlist',
      notes: 'smoke-live-api.mts 创建，运行结束时删除',
    });
    const cardId = created['id'];
    if (typeof cardId !== 'string') throw new Error('POST /applications returned no id');
    pass('POST /applications', `id=${cardId.slice(0, 8)} status=${String(created['status'])}`);

    const raw = await client.get<unknown>('/applications/board');
    if (!isApplicationBoard(raw)) {
      throw new Error(
        `GET /applications/board is not the documented shape (七列不全或卡片缺少 id/status/company)`,
      );
    }
    const board: ApplicationBoardResponse = raw;
    pass(
      'GET /applications/board',
      `columns=${board.columns.length} total=${board.total} archived=${board.archived}`,
    );

    const statuses = board.columns.map((column) => column.status);
    if (statuses.join(',') !== APPLICATION_STATUSES.join(',')) {
      throw new Error(`board column order drifted: got ${statuses.join(',')}`);
    }
    pass('board column order', statuses.join(' · '));

    await client.patch(`/applications/reorder`, {
      items: [{ id: cardId, status: 'interview' satisfies ApplicationStatus, position: 0 }],
    });
    const moved = await client.get<Record<string, unknown>>(`/applications/${cardId}`);
    if (moved['status'] !== 'interview') {
      throw new Error(`expected the card in interview, got ${String(moved['status'])}`);
    }
    const events = Array.isArray(moved['events']) ? moved['events'] : [];
    pass(
      'PATCH /applications/reorder',
      `status=interview events=${events.length} (每次变更都留痕)`,
    );

    await client.delete(`/applications/${cardId}`);
    const gone = await client.get<unknown>(`/applications/${cardId}`).then(
      () => 'still there',
      (error: unknown) => (error instanceof ApiError ? error.code : String(error)),
    );
    pass('DELETE /applications/:id', `deleted, then GET → ${gone}`);
  } catch (error) {
    fail('applications board', error);
  }

  /* 7. An error path: the envelope must still be an envelope. */
  try {
    await client.get('/definitely-not-a-route');
    fail('GET unknown route', new Error('expected a 404, got a success'));
  } catch (error) {
    if (error instanceof ApiError && error.code === 'NOT_FOUND' && error.requestId) {
      pass('GET unknown route', `404 ${error.code} with requestId`);
    } else {
      fail('GET unknown route', error);
    }
  }

  console.log(`\n${checks.length} checks passed against ${baseUrl}`);
}

await main();
