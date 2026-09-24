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
  isAiCosts,
  isAiRunDetail,
  isAiRunList,
  isApplicationBoard,
  isCacheStats,
  isCategoryPerformanceList,
  isCostByAgentList,
  isCostByFeatureList,
  isDashboardResponse,
  isFunnelResponse,
  isPromptVersionList,
  isPublicProfileResponse,
  isRatesResponse,
  isRecord,
  isSkillCorrelationList,
  isTimelineResponse,
  toServiceHealthStatus,
} from '../../../packages/shared/src/api/guards.ts';
import {
  APPLICATION_STATUSES,
  type ApplicationBoardResponse,
  type ApplicationStatus,
  type CategoryPerformance,
  type FunnelResponse,
  type PublicProfileResponse,
  type RatesResponse,
  type TimelineResponse,
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

    /* 6b. Analytics, against a board whose contents this script just built.
     *
     * The funnel is deterministic here — one card, moved to interview — so the numbers are
     * asserted rather than merely fetched. A funnel endpoint that "returns 200" is worthless;
     * one that reports the wrong count is worse than useless. */
    const funnelRaw = await client.get<unknown>('/analytics/funnel?range=all');
    if (!isFunnelResponse(funnelRaw)) {
      throw new Error('GET /analytics/funnel is not the documented shape (missing meta/stages)');
    }
    const funnel = funnelRaw as FunnelResponse;
    const counts = Object.fromEntries(funnel.stages.map((stage) => [stage.key, stage.count]));
    if (counts['applications'] !== 1 || counts['interviews'] !== 1) {
      throw new Error(`funnel disagrees with the board it just built: ${JSON.stringify(counts)}`);
    }
    if (funnel.meta.windowBasis !== 'applications' || funnel.meta.notes.length === 0) {
      throw new Error('the funnel did not state its window basis');
    }
    pass(
      'GET /analytics/funnel',
      `applications=${counts['applications']} interviews=${counts['interviews']} ` +
        `cohort=${funnel.meta.cohortSize} basis=${funnel.meta.windowBasis}`,
    );

    const ratesRaw = await client.get<unknown>('/analytics/rates?range=all');
    if (!isRatesResponse(ratesRaw)) throw new Error('GET /analytics/rates is not the documented shape');
    const rates = ratesRaw as RatesResponse;
    const interviewCard = rates.cards.find((card) => card.key === 'interviewRate');
    if (!interviewCard || interviewCard.denominator !== 1 || interviewCard.numerator !== 1) {
      throw new Error(`unexpected interview rate card: ${JSON.stringify(interviewCard)}`);
    }
    if (interviewCard.sufficient) {
      throw new Error('one application must not be reported as a sufficient sample');
    }
    pass(
      'GET /analytics/rates',
      `interviewRate=${interviewCard.numerator}/${interviewCard.denominator} ` +
        `sufficient=${interviewCard.sufficient} (n<${rates.meta.minimumSample})`,
    );

    const correlation = await client.get<unknown>('/analytics/skill-correlation?range=all');
    if (!isSkillCorrelationList(correlation)) {
      throw new Error('GET /analytics/skill-correlation is not the documented shape');
    }
    pass('GET /analytics/skill-correlation', `rows=${(correlation as unknown[]).length}`);

    const categories = await client.get<unknown>('/analytics/categories?range=all');
    if (!isCategoryPerformanceList(categories)) {
      throw new Error('GET /analytics/categories is not the documented shape');
    }
    const firstCategory = (categories as CategoryPerformance[])[0];
    pass(
      'GET /analytics/categories',
      firstCategory
        ? `category=${firstCategory.category} applications=${firstCategory.applications}`
        : 'no category rows',
    );

    const timelineRaw = await client.get<unknown>('/analytics/timeline?range=all');
    if (!isTimelineResponse(timelineRaw)) {
      throw new Error('GET /analytics/timeline is not the documented shape');
    }
    const timeline = timelineRaw as TimelineResponse;
    if (timeline.buckets.length === 0) throw new Error('the trend returned no months');
    pass(
      'GET /analytics/timeline',
      `entries=${timeline.entries.length} months=${timeline.buckets.length} ` +
        `basis=${timeline.meta.windowBasis}`,
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

  /* 7. The public candidate page: published, anonymous, and free of PII.
   *
   * The demo account is unpublished by default, so this checks the 404 first — the state a
   * stranger actually meets — then publishes, fetches **without a token**, and scans the
   * response with the same patterns the redactor uses. It un-publishes again at the end: a
   * smoke test that leaves a public page behind has changed what the next run measures. */
  try {
    const settings = await client.get<Record<string, unknown>>('/public/settings');
    const slug = typeof settings['slug'] === 'string' ? settings['slug'] : null;
    if (!slug) throw new Error('the demo account has no slug to publish under');
    if (settings['isPublished']) {
      await client.post('/public/publish', { published: false });
    }

    const before = await client.get<unknown>(`/public/candidate/${slug}`).then(
      () => 'reachable',
      (error: unknown) => (error instanceof ApiError ? String(error.status) : String(error)),
    );
    pass('GET /public (unpublished)', `${before} — 陌生人看到的是 404，不是半成品页`);

    await client.post('/public/publish', { published: true });
    const page = await client.get<unknown>(`/public/candidate/${slug}`, { auth: false });
    if (!isPublicProfileResponse(page)) {
      throw new Error('GET /public/candidate/{slug} is not the documented shape');
    }
    const publicPage = page as PublicProfileResponse;
    const body = JSON.stringify(publicPage);
    if (/[\w.+-]+@[\w-]+\.[\w.]+/.test(body)) throw new Error('the public page publishes an email');
    if (/(?<!\d)1[3-9]\d{9}(?!\d)/.test(body)) throw new Error('the public page publishes a phone');
    pass(
      'GET /public/candidate/:slug',
      `anonymous ok · skills=${publicPage.skills.length} ` +
        `coverage=${publicPage.meta.evidenceCoverage.toFixed(2)} ` +
        `hidden=[${publicPage.meta.hiddenSections.join(',')}] · no PII`,
    );

    const hidden = await client.patch<Record<string, unknown>>('/public/settings', {
      sections: { skills: false },
    });
    const afterHide = await client.get<unknown>(`/public/candidate/${slug}`, { auth: false });
    if (!isPublicProfileResponse(afterHide)) throw new Error('the page stopped validating');
    if ((afterHide as PublicProfileResponse).skills.length !== 0) {
      throw new Error('switching a section off did not take effect on the next read');
    }
    pass('PATCH /public/settings', `skills hidden → 0 skills on the next anonymous read`);

    await client.patch('/public/settings', { sections: { skills: true } });
    await client.post('/public/publish', { published: false });
    void hidden;
  } catch (error) {
    fail('public candidate page', error);
  }

  /* 8. AI observability: an AI operation must be findable, costed and attributed.
   *
   * The check performs a real AI operation first, then looks for it. Asserting the *link* between
   * the two is the point: `llm_calls` had no writer at all until PHASE 11, so the rows existing is
   * the thing worth proving. Tokens and cost are asserted as consistent rather than non-zero: the
   * zero-key heuristic path genuinely spends nothing, and a smoke test demanding non-zero tokens
   * would be demanding a lie on this deployment. */
  try {
    await client.post('/ai/analyze/jd', {
      text: '招聘嵌入式软件工程师，要求熟悉 STM32 与 FreeRTOS，熟悉 CAN 总线通信协议。',
    });
    // A second identical call: the cache is shared app-wide, so this one should be served from
    // the first one's entry. Asserted rather than assumed — "cache hit rate" is one of the phase's
    // exit criteria, and a rate nobody has seen rise is a rate nobody has checked.
    await client.post('/ai/analyze/jd', {
      text: '招聘嵌入式软件工程师，要求熟悉 STM32 与 FreeRTOS，熟悉 CAN 总线通信协议。',
    });

    const runs = await client.get<Record<string, unknown>>('/ai-runs?limit=5');
    // The runtime guard the AI Runs page uses, applied to the live payload: if it rejects, the page
    // would render "INVALID_RESPONSE" instead of a table, so this is the check that the page works.
    if (!isAiRunList(runs)) throw new Error('GET /ai-runs does not satisfy isAiRunList');
    const items = runs['items'] as Record<string, unknown>[];
    if (items.length === 0) throw new Error('the AI operation just performed is not in /ai-runs');
    const run = items[0] as Record<string, unknown>;
    if (typeof run['latencyMs'] !== 'number' || run['latencyMs'] <= 0) {
      throw new Error(`the run has no measured latency: ${String(run['latencyMs'])}`);
    }
    if (!run['promptVersion']) throw new Error('the run does not name its prompt version');
    pass(
      'GET /ai-runs',
      `${String(run['workflow'])} status=${String(run['status'])} ` +
        `latency=${String(run['latencyMs'])}ms tokens=${String(run['totalTokens'])} ` +
        `prompt=${String(run['promptVersion'])} steps=${String(run['stepCount'])}`,
    );

    const detail = await client.get<Record<string, unknown>>(`/ai-runs/${String(run['id'])}`);
    if (!isAiRunDetail(detail)) throw new Error('GET /ai-runs/:id does not satisfy isAiRunDetail');
    const steps = detail['steps'] as unknown[];
    const calls = detail['calls'] as unknown[];
    if (steps.length === 0) throw new Error('the run has no step chain to drill into');
    if (calls.length === 0) throw new Error('the run recorded no model call');
    pass(
      'GET /ai-runs/:id',
      `steps=[${steps
        .map((step) => String((step as Record<string, unknown>)['name']))
        .join(',')}] calls=${calls.length}`,
    );

    const costs = await client.get<Record<string, unknown>>('/ai-costs?range=7d');
    if (!isAiCosts(costs)) throw new Error('GET /ai-costs does not satisfy isAiCosts');
    const totals = costs['totals'] as Record<string, unknown>;
    if (Number(totals['runs']) < items.length) {
      throw new Error('/ai-costs reports fewer runs than /ai-runs listed');
    }
    pass(
      'GET /ai-costs',
      `runs=${String(totals['runs'])} calls=${String(totals['modelCalls'])} ` +
        `tokens=${String(totals['tokens'])} budget=$${String(costs['dailyBudgetUsd'])}`,
    );

    // The two breakdowns the cost page needs; without them the panels would render empty rather
    // than wrong, which is exactly the kind of failure nobody notices.
    const byAgent = await client.get<unknown>('/ai-costs/by-agent?range=7d');
    if (!isCostByAgentList(byAgent)) throw new Error('GET /ai-costs/by-agent failed its guard');
    const byFeature = await client.get<unknown>('/ai-costs/by-feature?range=7d');
    if (!isCostByFeatureList(byFeature)) throw new Error('GET /ai-costs/by-feature failed its guard');
    const agentNames = byAgent.map((row) => row.agent).join(',');
    const featureNames = byFeature.map((row) => `${row.feature}[${row.workflows.join('+')}]`).join(',');
    if (byFeature.length === 0) throw new Error('the AI work just performed is in no feature bucket');
    pass('GET /ai-costs/by-agent+by-feature', `agents=[${agentNames}] features=[${featureNames}]`);

    const cache = await client.get<Record<string, unknown>>('/cache/stats');
    if (!isCacheStats(cache)) throw new Error('GET /cache/stats does not satisfy isCacheStats');
    const kinds = (cache['byKind'] as Record<string, unknown>[]).map((entry) => String(entry['kind']));
    if (kinds.join(',') !== 'llm,embedding,tool') {
      throw new Error(`cache kinds are incomplete: ${kinds.join(',')}`);
    }
    const process = cache['process'] as Record<string, unknown>;
    if (Number(process['processHits']) < 1) {
      throw new Error(
        'two identical AI requests produced no cache hit; the shared cache is not working',
      );
    }
    pass(
      'GET /cache/stats',
      `kinds=[${kinds.join(',')}] hits=${String(process['processHits'])} ` +
        `misses=${String(process['processMisses'])} rate=${String(process['hitRate'])}`,
    );

    const prompts = await client.get<unknown>('/prompts');
    if (!isPromptVersionList(prompts)) throw new Error('GET /prompts failed its guard');
    const promptRows = prompts;
    if (promptRows.length === 0) throw new Error('the prompt registry is empty');
    const active = promptRows.filter((row) => row.isActive).length;
    pass('GET /prompts', `${promptRows.length} prompts, ${active} active, all versioned`);
  } catch (error) {
    fail('ai observability', error);
  }

  /* 9. An error path: the envelope must still be an envelope. */
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
