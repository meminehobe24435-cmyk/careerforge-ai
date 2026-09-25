import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiError } from '@careerforge/shared';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { DEMO_CLAIMS } from '@/components/validator/demo-claims';
import { CONFIDENCE_TOOLTIP } from '@/components/validator/verdict-copy';
import { ValidatorView } from '@/components/validator/validator-view';
import { fetchEvidenceIndex, validateClaim } from '@/lib/validator-api';
import type { ClaimStatus, ValidatedClaim } from '@/lib/validator-api';

/**
 * The page's contract with its reader.
 *
 * Six things matter more than the layout:
 *
 * 1. a preset button sends its *own sentence* through the real endpoint — a canned animation would
 *    be a lie about what the page does;
 * 2. each verdict renders its own copy, because "Verified by evidence" and "No sufficient evidence
 *    found" must never be interchangeable;
 * 3. the confidence block always carries the tooltip sentence — a bare percentage beside a verdict
 *    is the number a reader would misread as "probability this is true";
 * 4. a rule code this build does not know shows the raw code rather than a friendly invention;
 * 5. a verdict with no rewrite says why it has none;
 * 6. a rejected response is an error state with the request id and a retry, never a blank panel.
 *
 * jsdom applies no CSS, so the single-column layout is asserted through roles and text only.
 */

vi.mock('@/lib/validator-api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/validator-api')>();
  return {
    ...actual,
    validateClaim: vi.fn(),
    fetchEvidenceIndex: vi.fn(),
  };
});

const mocked = vi.mocked({ validateClaim, fetchEvidenceIndex });

function resultOf(
  status: ClaimStatus,
  overrides: Partial<ValidatedClaim['claim']> = {},
): ValidatedClaim {
  return {
    claimId: '11111111-2222-3333-4444-555555555555',
    claim: {
      claim: '使用 STM32 与 FreeRTOS 实现串级 PID 控制环',
      status,
      confidence: 0.781,
      reasons: [],
      sources: [
        {
          evidenceId: 'ev-doc',
          title: 'wei-zhang-resume.md',
          kind: 'document_chunk',
          relevance: 1,
          channel: 'keyword',
          locator: '—',
          url: null,
          snippet: '使用 STM32F4 与 FreeRTOS 编写任务调度与串级 PID 控制环',
        },
      ],
      safeRewrite: null,
      unknowns: [],
      hasQuantifiedClaim: false,
      independentSourceCount: 2,
      ruleVersion: 'claim_rules@1.0.0',
      model: 'heuristic',
      ...overrides,
    },
  };
}

function renderView() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const user = userEvent.setup();
  render(
    <QueryClientProvider client={client}>
      <ValidatorView />
    </QueryClientProvider>,
  );
  return user;
}

async function renderResult(result: ValidatedClaim) {
  mocked.validateClaim.mockResolvedValue(result);
  const user = renderView();
  // The button is disabled on an empty box on purpose, so a verdict is requested the way a reader
  // would request one: type a sentence, then press the button.
  await user.type(await screen.findByLabelText('Résumé sentence'), result.claim.claim);
  await user.click(screen.getByTestId('validate-claim'));
  await screen.findByTestId('validator-result');
  return user;
}

beforeEach(() => {
  mocked.validateClaim.mockReset();
  mocked.fetchEvidenceIndex.mockReset();
  mocked.fetchEvidenceIndex.mockResolvedValue({
    byId: {
      'ev-doc': {
        id: 'ev-doc',
        kind: 'document_chunk',
        title: 'wei-zhang-resume.md',
        confidence: 0.8,
      },
    },
    count: 6,
    truncated: false,
  });
});

describe('the claim validator page', () => {
  it('opens with the empty state, not with a fabricated verdict', async () => {
    renderView();
    expect(
      await screen.findByText('Validate a resume statement against your evidence.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Resume Claim Validator' })).toBeInTheDocument();
    expect(
      screen.getByText('Check whether a resume statement is actually supported by your evidence.'),
    ).toBeInTheDocument();
    expect(mocked.validateClaim).not.toHaveBeenCalled();
    // The gate is only run by an explicit action; a default claim would be a demo, not a product.
    expect(screen.queryByTestId('validator-result')).toBeNull();
  });

  it('sends a preset’s own sentence through the real endpoint', async () => {
    mocked.validateClaim.mockResolvedValue(resultOf('supported'));
    const user = renderView();

    await user.click(await screen.findByTestId('demo-claim-partial'));

    await waitFor(() => expect(mocked.validateClaim).toHaveBeenCalledTimes(1));
    const weak = DEMO_CLAIMS.find((claim) => claim.id === 'partial');
    expect(mocked.validateClaim).toHaveBeenCalledWith({
      text: weak?.text,
      section: 'summary',
    });
    // The sentence lands in the textarea too: the preset is a shortcut for typing.
    expect(screen.getByLabelText('Résumé sentence')).toHaveValue(weak?.text);
    expect(await screen.findByTestId('validator-result')).toBeInTheDocument();
  });

  it('disables the button and skeletons the result panel while the gate runs', async () => {
    let release: (value: ValidatedClaim) => void = () => {};
    mocked.validateClaim.mockImplementation(
      () =>
        new Promise<ValidatedClaim>((resolve) => {
          release = resolve;
        }),
    );
    const user = renderView();

    await user.type(await screen.findByLabelText('Résumé sentence'), '使用 STM32 开发固件');
    await user.click(screen.getByTestId('validate-claim'));

    expect(await screen.findByTestId('validator-skeleton')).toBeInTheDocument();
    expect(screen.getByTestId('validate-claim')).toBeDisabled();

    release(resultOf('supported'));
    await screen.findByTestId('validator-result');
    expect(screen.queryByTestId('validator-skeleton')).toBeNull();
  });

  it.each([
    ['supported', 'Verified by evidence'],
    ['partially_supported', 'Some parts are supported, but the wording overstates the evidence'],
    ['unsupported', 'No sufficient evidence found'],
  ] as const)('states the %s verdict in its own words', async (status, label) => {
    await renderResult(resultOf(status));
    expect(screen.getByTestId('verdict-label')).toHaveTextContent(label);
    expect(screen.getByTestId('verdict-badge')).toHaveTextContent(status);
    // Band and number, both from the API's confidence value.
    expect(screen.getByTestId('confidence')).toHaveTextContent('High · 78%');
    // The live stack returns a high confidence on an unsupported verdict, so the card has to say
    // which question the number answers or the two panels read as a contradiction.
    const note = screen.queryByTestId('confidence-note');
    if (status === 'unsupported') {
      expect(note).toHaveTextContent(/not whether that evidence supports the sentence/);
    } else {
      expect(note).toBeNull();
    }
  });

  it('explains what confidence is, in the exact sentence, on hover', async () => {
    const user = await renderResult(resultOf('partially_supported'));

    await user.hover(screen.getByRole('button', { name: 'What confidence means' }));

    const tooltip = await screen.findByRole('tooltip');
    expect(tooltip).toHaveTextContent(CONFIDENCE_TOOLTIP);
  });

  it('lists each cited source with its channel and confidence', async () => {
    await renderResult(resultOf('supported'));

    const source = within(screen.getByTestId('evidence-source'));
    expect(source.getByRole('link', { name: 'wei-zhang-resume.md' })).toHaveAttribute(
      'href',
      '/app/evidence-graph?node=ev-doc',
    );
    expect(source.getByText('channel keyword')).toBeInTheDocument();
    expect(source.getByText('1.00')).toBeInTheDocument();
    // Confidence comes from the evidence record, not from the citation's relevance.
    expect(source.getByText('0.80')).toBeInTheDocument();
  });

  it('renders the ownership rule as an ownership risk, and an unknown code as itself', async () => {
    await renderResult(
      resultOf('partially_supported', {
        reasons: [
          {
            rule: 'superlative_language',
            severity: 'warning',
            message:
              '「主导」是职责范围的断言，而证据中没有出现「主导」——证据支持不了「由你主导/独立完成」这个范围说法。',
            evidenceIds: [],
          },
          {
            rule: 'future_rule_9000',
            severity: 'blocker',
            message: 'the gate learned something new',
            evidenceIds: [],
          },
        ],
        unknowns: ['kubernetes'],
      }),
    );

    const titles = screen.getAllByTestId('risk-title').map((node) => node.textContent);
    expect(titles).toContain('Claim implies ownership beyond the available evidence');
    // No invented sentence for a code this build cannot describe.
    expect(titles).toContain('future_rule_9000');
    expect(screen.getByTestId('unknowns')).toHaveTextContent('kubernetes');
  });

  it('explains a rejected claim’s rule codes only when asked', async () => {
    const user = await renderResult(
      resultOf('unsupported', {
        reasons: [
          {
            rule: 'numeric_without_evidence',
            severity: 'blocker',
            message: '「90%」在证据中找不到同类量化数据。',
            evidenceIds: [],
          },
        ],
      }),
    );

    expect(screen.queryByTestId('rule-explanation')).toBeNull();
    const toggle = screen.getByTestId('why-rejected');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');

    await user.click(toggle);

    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    const explanation = within(screen.getByTestId('rule-explanation'));
    expect(explanation.getByText(/numeric_without_evidence/)).toBeInTheDocument();
    expect(explanation.getByText(/runs before any model is consulted/)).toBeInTheDocument();
    expect(explanation.getByText('「90%」在证据中找不到同类量化数据。')).toBeInTheDocument();
  });

  it('offers an evidence-safe rewrite with the original above it', async () => {
    await renderResult(
      resultOf('partially_supported', {
        safeRewrite: {
          text: '使用 STM32 与 FreeRTOS 实现串级 PID 控制环',
          removedClaims: ['tensorflow'],
          rationale: '由证据验证模型给出的降级表述',
        },
      }),
    );

    expect(screen.getByTestId('rewrite-text')).toHaveTextContent(
      '使用 STM32 与 FreeRTOS 实现串级 PID 控制环',
    );
    expect(screen.getByTestId('rewrite-original')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Copy rewrite' })).toBeInTheDocument();
    expect(screen.getByText(/Removed:/)).toHaveTextContent('tensorflow');
  });

  it('says why there is no rewrite instead of showing an empty panel', async () => {
    await renderResult(
      resultOf('unsupported', {
        reasons: [
          {
            rule: 'numeric_without_evidence',
            severity: 'blocker',
            message: '「90%」在证据中找不到同类量化数据。',
            evidenceIds: [],
          },
          {
            rule: 'skill_not_in_graph',
            severity: 'warning',
            message: '证据中未出现：kubernetes、rust。',
            evidenceIds: [],
          },
        ],
      }),
    );

    const declined = within(screen.getByTestId('rewrite-declined'));
    expect(declined.getByText('No evidence-safe wording offered')).toBeInTheDocument();
    expect(
      declined.getByText(/still name a technology the evidence never mentions/),
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Copy rewrite' })).toBeNull();
  });

  it('reports a rejected request with its code, request id and a retry', async () => {
    mocked.validateClaim.mockRejectedValue(
      new ApiError({
        code: 'INVALID_RESPONSE',
        message:
          'POST /evidence/validate 返回的结构与它声明的契约不一致（缺少 data.claim.confidence）',
        requestId: 'req_01HZ',
        status: 200,
      }),
    );
    const user = renderView();

    await user.type(await screen.findByLabelText('Résumé sentence'), '使用 STM32 开发固件');
    await user.click(screen.getByTestId('validate-claim'));

    const alert = await screen.findByRole('alert');
    expect(within(alert).getByText('The gate did not answer')).toBeInTheDocument();
    expect(within(alert).getByText('INVALID_RESPONSE')).toBeInTheDocument();
    expect(within(alert).getByText('req_01HZ')).toBeInTheDocument();

    mocked.validateClaim.mockResolvedValue(resultOf('supported'));
    await user.click(within(alert).getByRole('button', { name: /Retry the same claim/ }));
    await waitFor(() => expect(mocked.validateClaim).toHaveBeenCalledTimes(2));
    expect(await screen.findByTestId('validator-result')).toBeInTheDocument();
  });

  it('warns when a verdict belongs to a sentence that has since changed', async () => {
    const user = await renderResult(resultOf('supported'));

    await user.type(screen.getByLabelText('Résumé sentence'), '又改了一句');

    expect(screen.getByTestId('edited-since')).toBeInTheDocument();
  });

  it('tells the reader when the evidence base is empty, rather than blaming the sentence', async () => {
    mocked.fetchEvidenceIndex.mockResolvedValue({ byId: {}, count: 0, truncated: false });
    renderView();

    expect(await screen.findByText('Your evidence base is empty')).toBeInTheDocument();
  });

  /**
   * The rule panel's heading is the reader's first question, and it has to be the question the
   * verdict raises. It used to read "Why was this rejected?" over every verdict — including
   * `supported`, where the page asked why a sentence it had just verified had been rejected.
   */
  it.each([
    ['supported', 'Why is this supported?'],
    ['partially_supported', 'Why is this only partially supported?'],
    ['unsupported', 'Why was this rejected?'],
    ['contradicted', 'Why was this rejected?'],
  ] as const)('asks the %s verdict’s own question in the rule panel', async (status, heading) => {
    await renderResult(
      resultOf(status, {
        reasons: [
          {
            rule: 'superlative_language',
            severity: 'warning',
            message: '「主导」是职责范围的断言，而证据中没有出现「主导」。',
            evidenceIds: [],
          },
        ],
      }),
    );

    expect(screen.getByRole('heading', { name: heading })).toBeInTheDocument();
  });

  it('never asks why a supported sentence was rejected', async () => {
    await renderResult(resultOf('supported'));

    expect(screen.queryByText('Why was this rejected?')).toBeNull();
  });

  /**
   * No rule codes means there is no objection to list, so the section is not rendered at all and
   * the explanation that takes its place states what the verdict actually rested on.
   */
  it('replaces an empty rejection section with what carried the claim', async () => {
    await renderResult(resultOf('supported'));

    // The empty panel is gone — heading, `0 rule codes` badge and toggle included.
    expect(screen.queryByTestId('why-rejected')).toBeNull();
    expect(screen.queryByText('0 rule codes')).toBeNull();
    expect(screen.queryByText('Why was this rejected?')).toBeNull();

    const affirmative = within(screen.getByTestId('affirmative-explanation'));
    expect(affirmative.getByText('What carries this sentence')).toBeInTheDocument();
    // The API's own figures, not a re-derivation: the claim fixture reports 2 independent kinds.
    expect(affirmative.getByText(/2 independent evidence kinds/)).toBeInTheDocument();
    expect(affirmative.getByText(/document_chunk/)).toBeInTheDocument();
    expect(affirmative.getByText(/High · 78%/)).toBeInTheDocument();
  });

  it('explains a code-free rejection as arithmetic rather than showing an empty list', async () => {
    await renderResult(resultOf('unsupported'));

    expect(screen.queryByTestId('why-rejected')).toBeNull();
    const affirmative = within(screen.getByTestId('affirmative-explanation'));
    expect(affirmative.getByText('Why no rule is listed')).toBeInTheDocument();
    expect(affirmative.getByText(/no rule objection to show you/)).toBeInTheDocument();
  });

  it('keeps the rule detail panel, with its own heading, once a rule has fired', async () => {
    await renderResult(
      resultOf('partially_supported', {
        reasons: [
          {
            rule: 'single_source_only',
            severity: 'warning',
            message: '目前只有 1 条独立来源。',
            evidenceIds: [],
          },
        ],
      }),
    );

    expect(screen.queryByTestId('affirmative-explanation')).toBeNull();
    expect(
      screen.getByRole('heading', { name: 'Why is this only partially supported?' }),
    ).toBeInTheDocument();
    expect(screen.getByTestId('why-rejected')).toBeInTheDocument();
  });
});
