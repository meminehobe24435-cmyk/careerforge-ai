import { describe, expect, it } from 'vitest';

import {
  CONFIDENCE_TOOLTIP,
  MIN_INDEPENDENT_SOURCES,
  VERDICT_COPY,
  affirmativeExplanation,
  allowsResumeInclusion,
  channelLabel,
  evidenceGraphHref,
  noRewriteCopy,
  overallSeverity,
  readConfidence,
  riskItems,
  rulePanelTitle,
} from '@/components/validator/verdict-copy';
import type { ClaimReason, ClaimSource, ClaimStatus } from '@/lib/validator-api';

/**
 * The page's vocabulary, asserted against the code it was copied from.
 *
 * These are not layout tests: they pin the sentences a reader will act on, the confidence
 * tooltip's exact wording, and the rule-code mapping — including the two codes that hide two
 * different rules behind one name, and the fallback for a code this build has never seen.
 */

function reason(overrides: Partial<ClaimReason> = {}): ClaimReason {
  return {
    rule: 'superlative_language',
    severity: 'warning',
    message: '「主导」：「主导」意味着主导权，需要有可验证的职责范围',
    evidenceIds: [],
    ...overrides,
  };
}

describe('verdict copy', () => {
  it('states each verdict in audit language, not as a grade', () => {
    expect(VERDICT_COPY.supported.label).toBe('Verified by evidence');
    expect(VERDICT_COPY.partially_supported.label).toBe(
      'Some parts are supported, but the wording overstates the evidence',
    );
    expect(VERDICT_COPY.unsupported.label).toBe('No sufficient evidence found');
    // `contradicted` is the one verdict that accuses, and it says so rather than reading softer.
    expect(VERDICT_COPY.contradicted.label).toBe('Evidence conflicts with this claim');
  });

  it('derives résumé inclusion from the status, exactly as the enum does', () => {
    expect(allowsResumeInclusion('supported')).toBe(true);
    expect(allowsResumeInclusion('partially_supported')).toBe(true);
    expect(allowsResumeInclusion('unsupported')).toBe(false);
    expect(allowsResumeInclusion('contradicted')).toBe(false);
    expect(allowsResumeInclusion('pending')).toBe(false);
    // The gate's own constant, quoted rather than remembered.
    expect(MIN_INDEPENDENT_SOURCES).toBe(2);
  });
});

describe('confidence', () => {
  it('carries the exact tooltip sentence', () => {
    expect(CONFIDENCE_TOOLTIP).toBe(
      'Confidence estimates how strongly the available evidence supports this verdict. It is not a probability of truth.',
    );
  });

  it('shows band and number together, with banded thresholds', () => {
    expect(readConfidence(0.89).text).toBe('High · 89%');
    expect(readConfidence(0.62).text).toBe('Medium · 62%');
    expect(readConfidence(0.31).text).toBe('Low · 31%');
    // The bands are the gate's own thresholds: 0.75 supported, 0.45 partial.
    expect(readConfidence(0.75).band).toBe('High');
    expect(readConfidence(0.74).band).toBe('Medium');
    expect(readConfidence(0.45).band).toBe('Medium');
    expect(readConfidence(0.44).band).toBe('Low');
  });

  it('never invents a value for a non-number', () => {
    expect(readConfidence(Number.NaN).text).toBe('Low · 0%');
  });
});

describe('rule code → risk', () => {
  it('renders the quantified blocker as a measurable-evidence finding', () => {
    const [risk] = riskItems([
      reason({ rule: 'numeric_without_evidence', severity: 'blocker', message: '「90%」…' }),
    ]);
    expect(risk?.title).toBe('Quantified result is not backed by measurable evidence');
    expect(risk?.severity).toBe('blocker');
    expect(risk?.code).toBe('numeric_without_evidence');
    expect(risk?.unknown).toBe(false);
  });

  it('renders the ownership gap as an ownership finding, not as generic over-claiming', () => {
    const [risk] = riskItems([
      reason({
        rule: 'superlative_language',
        severity: 'warning',
        // The message marker produced only by `detect_ownership_gap` (claim_rules.py:237).
        message:
          '「主导」是职责范围的断言，而证据中没有出现「主导」——证据能支持你做过这件事，但支持不了「由你主导/独立完成」这个范围说法，因此最多只能判为 partially_supported。',
      }),
    ]);
    expect(risk?.title).toBe('Claim implies ownership beyond the available evidence');
    expect(risk?.explanation).toContain('capped at partially supported');
  });

  it('keeps plain superlative wording distinct from the ownership cap', () => {
    const [risk] = riskItems([
      reason({ message: '「精通」：「精通」是最强的能力断言，需要非常充分的证据' }),
    ]);
    expect(risk?.title).toBe('Over-claiming wording the evidence cannot carry');
  });

  it('maps every code the API can return', () => {
    const codes = [
      'numeric_without_evidence',
      'superlative_language',
      'no_evidence_match',
      'single_source_only',
      'timeline_conflict',
      'skill_not_in_graph',
      'low_confidence_sources',
      'quantified_skill_unsupported',
    ];
    for (const code of codes) {
      const [risk] = riskItems([reason({ rule: code, message: `${code} message` })]);
      expect(risk?.code).toBe(code);
      expect(risk?.unknown).toBe(false);
      // Every mapped code has a real finding sentence and a one-line explanation.
      expect(risk?.title.length ?? 0).toBeGreaterThan(8);
      expect(risk?.explanation.length ?? 0).toBeGreaterThan(20);
    }
  });

  it('separates the two rules that share low_confidence_sources', () => {
    const [contradiction] = riskItems([
      reason({ rule: 'low_confidence_sources', severity: 'blocker', message: '证据与断言冲突：…' }),
    ]);
    const [degraded] = riskItems([
      reason({
        rule: 'low_confidence_sources',
        severity: 'info',
        message: '模型判定不可用，本次结论仅基于确定性规则与证据检索',
      }),
    ]);
    expect(contradiction?.title).toBe('Evidence conflicts with this claim');
    expect(degraded?.title).toBe('Model judgement unavailable');
  });

  it('falls back to the raw code instead of inventing a friendly sentence', () => {
    const [risk] = riskItems([
      reason({ rule: 'brand_new_rule_v9', severity: 'blocker', message: 'raw message' }),
    ]);
    expect(risk?.title).toBe('brand_new_rule_v9');
    expect(risk?.unknown).toBe(true);
    expect(risk?.explanation).toContain('Unknown rule code');
    expect(risk?.messages).toEqual(['raw message']);
  });

  it('groups repeated reasons under one code but keeps every message', () => {
    const risks = riskItems([
      reason({ message: '「主导」…' }),
      reason({ message: '「独立完成」…' }),
      reason({ rule: 'skill_not_in_graph', severity: 'warning', message: 'kubernetes' }),
    ]);
    expect(risks).toHaveLength(2);
    expect(risks[0]?.messages).toHaveLength(2);
    expect(overallSeverity([reason({ severity: 'blocker' })])).toBe('blocker');
    expect(overallSeverity([])).toBe('none');
  });
});

describe('no rewrite offered', () => {
  it('explains the decline when an unsupported noun would remain', () => {
    const copy = noRewriteCopy([
      reason({ rule: 'numeric_without_evidence', severity: 'blocker' }),
      reason({ rule: 'skill_not_in_graph', severity: 'warning' }),
    ]);
    expect(copy.title).toBe('No evidence-safe wording offered');
    expect(copy.body).toContain('still name a technology the evidence never mentions');
  });

  it('explains the decline for a blocked number with nothing droppable', () => {
    const copy = noRewriteCopy([reason({ rule: 'numeric_without_evidence', severity: 'blocker' })]);
    expect(copy.title).toBe('No evidence-safe wording offered');
    expect(copy.body).toContain('Nothing could be dropped here');
  });

  it('explains that an ownership objection cannot be rewritten away', () => {
    // Measured on the live gate: a claim that is only an ownership overstatement comes back
    // `partially_supported` with `safe_rewrite: null`.
    const copy = noRewriteCopy([
      reason({
        message: '「主导」是职责范围的断言，而证据中没有出现「主导」——证据支持不了这个范围说法。',
      }),
    ]);
    expect(copy.title).toBe('No evidence-safe wording offered');
    expect(copy.body).toContain('cannot soften an ownership assertion');
  });

  it('says a supported claim needs no rewrite', () => {
    expect(noRewriteCopy([]).title).toBe('No rewrite needed');
  });
});

describe('source provenance copy', () => {
  it('names the retriever channel the API reported', () => {
    expect(channelLabel('semantic')).toBe('semantic');
    expect(channelLabel('keyword')).toBe('keyword');
    expect(channelLabel('both')).toBe('semantic + keyword');
    // An unrecognised channel is shown verbatim rather than dropped.
    expect(channelLabel('graph')).toBe('graph');
  });

  it('links a cited source to its node in the evidence graph', () => {
    const href = evidenceGraphHref({
      evidenceId: '11111111-2222-3333-4444-555555555555',
      title: 'motor_control.c',
      kind: 'repo_file',
      relevance: 1,
      channel: 'both',
      locator: 'motor_control.c:42',
      url: null,
      snippet: '',
    });
    expect(href).toBe('/app/evidence-graph?node=11111111-2222-3333-4444-555555555555');
  });
});

describe('the rule panel asks the question the verdict raises', () => {
  it('phrases the heading for each verdict instead of asking about a rejection every time', () => {
    expect(rulePanelTitle('supported')).toBe('Why is this supported?');
    expect(rulePanelTitle('partially_supported')).toBe('Why is this only partially supported?');
    expect(rulePanelTitle('unsupported')).toBe('Why was this rejected?');
    expect(rulePanelTitle('contradicted')).toBe('Why was this rejected?');
  });

  it('never asks why a supported sentence was rejected', () => {
    for (const status of ['supported', 'partially_supported'] as const) {
      expect(rulePanelTitle(status).toLowerCase()).not.toContain('rejected');
    }
  });

  it('stays neutral for a verdict it has no phrasing for', () => {
    // `pending` is a real status: no gate decision has been made, so there is nothing to reject.
    expect(rulePanelTitle('pending')).toBe('Why this verdict?');
    // …and so is a status a newer backend added, which must not be read as a rejection.
    expect(rulePanelTitle('needs_review' as ClaimStatus)).toBe('Why this verdict?');
  });
});

describe('the explanation that replaces an empty rule list', () => {
  function source(overrides: Partial<ClaimSource> = {}): ClaimSource {
    return {
      evidenceId: 'ev-1',
      title: 'resume.md',
      kind: 'document_chunk',
      relevance: 1,
      channel: 'keyword',
      locator: '—',
      url: null,
      snippet: '使用 STM32 与 FreeRTOS 编写任务调度',
      ...overrides,
    };
  }

  const evidence = {
    sources: [source(), source({ evidenceId: 'ev-2', kind: 'manual', channel: 'manual' })],
    independentSourceCount: 2,
    confidence: 0.81,
  };

  it('states what carried a supported sentence, in the API’s own figures', () => {
    const copy = affirmativeExplanation('supported', evidence);
    expect(copy.title).toBe('What carries this sentence');
    expect(copy.body).toContain('No rule fired');
    // The count and the kinds are the payload's, not a re-derivation.
    expect(copy.body).toContain('2 independent evidence kinds');
    expect(copy.body).toContain('document_chunk / manual');
    expect(copy.body).toContain(`minimum of ${MIN_INDEPENDENT_SOURCES}`);
    expect(copy.body).toContain('High · 81%');
  });

  it('uses the singular for a single independent source and omits kinds it was not given', () => {
    const copy = affirmativeExplanation('supported', {
      sources: [],
      independentSourceCount: 1,
      confidence: 0.5,
    });
    expect(copy.body).toContain('1 independent evidence kind');
    expect(copy.body).not.toContain('across');
  });

  it('does not claim a rejection for a verdict that is not one', () => {
    for (const status of ['supported', 'partially_supported', 'unsupported'] as const) {
      expect(affirmativeExplanation(status, evidence).title.toLowerCase()).not.toContain('reject');
    }
  });

  it('explains a partial verdict without rule codes as arithmetic, not as an objection', () => {
    const copy = affirmativeExplanation('partially_supported', evidence);
    expect(copy.title).toBe('What this verdict rests on');
    expect(copy.body).toContain('below the 0.75');
    expect(copy.body).toContain('unknowns');
  });

  it('says plainly that no rule is listed rather than rendering an empty section', () => {
    const copy = affirmativeExplanation('unsupported', {
      ...evidence,
      independentSourceCount: 0,
      sources: [],
    });
    expect(copy.title).toBe('Why no rule is listed');
    expect(copy.body).toContain('no rule objection to show you');
    expect(copy.body).toContain('0 independent evidence kinds');
  });
});
