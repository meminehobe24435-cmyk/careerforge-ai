import { describe, expect, it } from 'vitest';

import type { AiRun, AiStep } from '@careerforge/shared';
import { isAiCosts, isAiRunDetail, isAiRunList } from '@careerforge/shared';

import {
  COSTS,
  DAY,
  RUN_DETAIL,
  RUN_LIST,
  call,
  run,
  step,
  unavailableRun,
  without,
} from '@/lib/observability-guard-fixtures';

/**
 * The run and cost guards of API.md §2.12.
 *
 * These are the guards that stand between a malformed payload and a page that renders a number
 * nobody measured. Each one is checked from both sides: a *valid* payload (typed with the frozen
 * contract type, so the positive case cannot drift away from the interface it guards) must pass,
 * and a payload that is genuinely different — a removed key, a string where a number belongs, a
 * status outside the enum — must be rejected.
 *
 * **PHASE 13 added a third side.** The usage columns are nullable (migration `0009`), so a count is
 * now legal in three shapes — a finite number, `null`, or absent — and illegal in one: anything
 * that is not a number. The tests below pin all four, because "accept `null`" and "still reject
 * `'150'`" are the two halves of the same fix and a guard that only did the first would silently
 * start accepting strings.
 *
 * Where a guard does **not** reject something the list above would suggest, that is asserted as
 * an accepted case and named in the test, rather than left for a reader to discover. The guards
 * are documented as being about "presence and type, not about totals", and the tests below pin
 * exactly which of the two jobs each one actually does.
 *
 * The cache, prompt and per-entity breakdown guards live in `observability-cache-guards.test.ts`.
 * One valid payload each lives in `observability-guard-fixtures.ts`, so the two files cannot
 * disagree about what "valid" means.
 */

describe('isAiRunList', () => {
  it('accepts a list the AI Runs page can render', () => {
    expect(isAiRunList(RUN_LIST)).toBe(true);
    // A brand-new deployment: an empty page is a valid page.
    expect(isAiRunList({ items: [], total: 0, limit: 50, offset: 0 })).toBe(true);
  });

  it('rejects a run missing a field the page prints', () => {
    expect(isAiRunList({ ...RUN_LIST, items: [without(run(), 'agent')] })).toBe(false);
    expect(isAiRunList({ ...RUN_LIST, items: [without(run(), 'workflow')] })).toBe(false);
    expect(isAiRunList({ ...RUN_LIST, items: [without(run(), 'id')] })).toBe(false);
  });

  it('rejects a token count and a page total that are not numbers', () => {
    expect(
      isAiRunList({ ...RUN_LIST, items: [run({ totalTokens: '150' as unknown as number })] }),
    ).toBe(false);
    expect(isAiRunList({ ...RUN_LIST, total: '1' as unknown as number })).toBe(false);
    // A boolean where a flag is expected, the other way round.
    expect(
      isAiRunList({ ...RUN_LIST, items: [run({ cacheHit: 'false' as unknown as boolean })] }),
    ).toBe(false);
  });

  it('rejects a non-finite number, which is the only numeric check the guard makes', () => {
    expect(isAiRunList({ ...RUN_LIST, items: [run({ totalTokens: Number.NaN })] })).toBe(false);
    expect(
      isAiRunList({ ...RUN_LIST, items: [run({ stepCount: Number.POSITIVE_INFINITY })] }),
    ).toBe(false);
  });

  it('rejects anything that is not a list of runs', () => {
    expect(isAiRunList(null)).toBe(false);
    expect(isAiRunList('nope')).toBe(false);
    expect(isAiRunList({ ...RUN_LIST, items: 'nope' })).toBe(false);
    expect(isAiRunList(without(RUN_LIST, 'items'))).toBe(false);
  });

  it('accepts a negative count and an unknown status — it checks presence and type only', () => {
    // Documented hole, asserted so it cannot be mistaken for coverage: `isNumber` accepts any
    // finite number, and `status` is typed `AiRunStatus | (string & {})` on purpose so a new
    // server-side status cannot blank the page. Neither is a rejection this guard claims to make.
    expect(isAiRunList({ ...RUN_LIST, items: [run({ totalTokens: -5 })] })).toBe(true);
    expect(isAiRunList({ ...RUN_LIST, items: [run({ status: 'exploded' })] })).toBe(true);
    expect(isAiRunList({ ...RUN_LIST, items: [run({ costUsd: -0.5 })] })).toBe(true);
  });

  /**
   * The PHASE 13 contract: `null` is not `0`, and the honest payload must be able to reach the UI.
   *
   * Before this, the guard rejected the entire list because `totalTokens` was `null`, so a page
   * whose whole point is "we did not measure this" could only ever show an error panel.
   */
  it('accepts a run whose usage was never reported, as null', () => {
    expect(isAiRunList({ ...RUN_LIST, items: [unavailableRun()] })).toBe(true);
    // Every nullable count, one at a time, so a single relaxed field cannot cover for a strict one.
    for (const key of [
      'promptTokens',
      'completionTokens',
      'totalTokens',
      'cachedTokens',
      'costUsd',
      'costCny',
    ] as const) {
      expect(isAiRunList({ ...RUN_LIST, items: [run({ [key]: null } as Partial<AiRun>)] })).toBe(
        true,
      );
    }
    // `usageStatus: null` is a pre-PHASE-13 row, not a contract violation.
    expect(isAiRunList({ ...RUN_LIST, items: [run({ usageStatus: null })] })).toBe(true);
    expect(isAiRunList({ ...RUN_LIST, items: [run({ usageStatus: 'legacy' })] })).toBe(true);
  });

  it('accepts a missing count, which is the same fact as a null one', () => {
    expect(isAiRunList({ ...RUN_LIST, items: [without(unavailableRun(), 'totalTokens')] })).toBe(
      true,
    );
    expect(isAiRunList({ ...RUN_LIST, items: [without(run(), 'cachedTokens')] })).toBe(true);
    expect(isAiRunList({ ...RUN_LIST, items: [without(run(), 'costUsd')] })).toBe(true);
    expect(isAiRunList({ ...RUN_LIST, items: [without(run(), 'usageStatus')] })).toBe(true);
  });

  it('still rejects a count that is the wrong type, null or not', () => {
    // The other half of the relaxation: only `null`/absent joins the number as legal.
    expect(
      isAiRunList({ ...RUN_LIST, items: [run({ totalTokens: 'null' as unknown as number })] }),
    ).toBe(false);
    expect(isAiRunList({ ...RUN_LIST, items: [run({ costUsd: {} as unknown as number })] })).toBe(
      false,
    );
    expect(
      isAiRunList({ ...RUN_LIST, items: [unavailableRun({ costCny: '0' as unknown as number })] }),
    ).toBe(false);
    expect(
      isAiRunList({ ...RUN_LIST, items: [run({ usageStatus: 5 as unknown as string })] }),
    ).toBe(false);
    expect(
      isAiRunList({ ...RUN_LIST, items: [unavailableRun({ promptTokens: Number.NaN })] }),
    ).toBe(false);
  });
});

describe('isAiRunDetail', () => {
  it('accepts a run with its step chain and calls', () => {
    expect(isAiRunDetail(RUN_DETAIL)).toBe(true);
    // A run that made no call at all is still a readable detail.
    expect(isAiRunDetail({ ...RUN_DETAIL, steps: [], calls: [] })).toBe(true);
  });

  it('rejects a detail without its step chain', () => {
    expect(isAiRunDetail(without(RUN_DETAIL, 'steps'))).toBe(false);
    expect(isAiRunDetail({ ...RUN_DETAIL, steps: 'nope' as unknown as AiStep[] })).toBe(false);
    expect(isAiRunDetail({ ...RUN_DETAIL, steps: [without(step(), 'name')] })).toBe(false);
  });

  it('rejects a call without the provider that served it', () => {
    expect(isAiRunDetail({ ...RUN_DETAIL, calls: [without(call(), 'provider')] })).toBe(false);
    expect(isAiRunDetail(without(RUN_DETAIL, 'calls'))).toBe(false);
  });

  it('inherits the run checks, so a broken run is not rescued by a valid chain', () => {
    expect(isAiRunDetail({ ...RUN_DETAIL, agent: undefined })).toBe(false);
    expect(isAiRunDetail({ ...RUN_DETAIL, totalTokens: '150' })).toBe(false);
  });

  it('accepts a chain whose steps and calls carry no usage', () => {
    // A step that made no model call and a step whose call went unreported both arrive this way;
    // `usageStatus` is what tells them apart, so the guard must let them through.
    expect(
      isAiRunDetail({
        ...RUN_DETAIL,
        steps: [step({ tokens: null, costUsd: null, usageStatus: 'unavailable' })],
        calls: [call({ totalTokens: null, costUsd: null, usageStatus: 'unavailable' })],
      }),
    ).toBe(true);
    expect(isAiRunDetail({ ...RUN_DETAIL, steps: [step({ usageStatus: null })] })).toBe(true);
  });

  it('rejects a step or call whose count is the wrong type', () => {
    expect(
      isAiRunDetail({ ...RUN_DETAIL, steps: [step({ tokens: '150' as unknown as number })] }),
    ).toBe(false);
    expect(
      isAiRunDetail({ ...RUN_DETAIL, calls: [call({ costUsd: 'x' as unknown as number })] }),
    ).toBe(false);
    expect(
      isAiRunDetail({ ...RUN_DETAIL, calls: [call({ usageStatus: 7 as unknown as string })] }),
    ).toBe(false);
  });
});

describe('isAiCosts', () => {
  it('accepts a summary the Cost page can render', () => {
    expect(isAiCosts(COSTS)).toBe(true);
    // No spend yet: an empty series and zero totals are a valid payload.
    expect(
      isAiCosts({
        ...COSTS,
        days: [],
        totals: { runs: 0, modelCalls: 0, tokens: 0, costUsd: 0, costCny: 0, latencyMs: 0 },
      }),
    ).toBe(true);
  });

  it('rejects a payload without its totals or its budget', () => {
    expect(isAiCosts(without(COSTS, 'totals'))).toBe(false);
    expect(isAiCosts(without(COSTS, 'dailyBudgetUsd'))).toBe(false);
    expect(isAiCosts({ ...COSTS, dailyBudgetUsd: '5' as unknown as number })).toBe(false);
  });

  it('rejects a cost that arrived as a string and a run count that did', () => {
    expect(
      isAiCosts({ ...COSTS, totals: { ...COSTS.totals, costUsd: '0.0012' as unknown as number } }),
    ).toBe(false);
    expect(
      isAiCosts({ ...COSTS, totals: { ...COSTS.totals, runs: '1' as unknown as number } }),
    ).toBe(false);
  });

  it('rejects a daily series that is not a series', () => {
    expect(isAiCosts({ ...COSTS, days: 'nope' })).toBe(false);
    expect(isAiCosts({ ...COSTS, days: [without(DAY, 'day')] })).toBe(false);
    expect(isAiCosts({ ...COSTS, days: [without(DAY, 'costUsd')] })).toBe(false);
    expect(isAiCosts({ ...COSTS, days: [{ ...DAY, costUsd: 'x' }] })).toBe(false);
  });

  it('accepts a negative total — nothing here claims to reject one', () => {
    expect(isAiCosts({ ...COSTS, totals: { ...COSTS.totals, costUsd: -1 } })).toBe(true);
  });

  /**
   * `unaccountedRuns` is what turns the total into a stated floor, so the page prints it.
   *
   * Absent is tolerated — an older API simply never said — and the page then treats it as 0 and
   * prints "Total cost" instead of "Known cost". A non-number is not tolerated: the page prints
   * this number, and a page that prints `undefined` is broken in a way no test should bless.
   */
  it('accepts the unaccounted-run count, including absent, and rejects the wrong type', () => {
    expect(isAiCosts({ ...COSTS, unaccountedRuns: 3 })).toBe(true);
    expect(isAiCosts({ ...COSTS, unaccountedRuns: 0 })).toBe(true);
    expect(isAiCosts(without(COSTS, 'unaccountedRuns'))).toBe(true);
    expect(isAiCosts({ ...COSTS, unaccountedRuns: null })).toBe(true);
    expect(isAiCosts({ ...COSTS, unaccountedRuns: '3' as unknown as number })).toBe(false);
    expect(isAiCosts({ ...COSTS, unaccountedRuns: Number.NaN })).toBe(false);
  });
});
