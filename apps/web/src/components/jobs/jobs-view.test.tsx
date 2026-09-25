import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { DEMO_JD_TEXT } from '@/components/jobs/demo-jd';
import { JobsView } from '@/components/jobs/jobs-view';
import { ApiError, api } from '@/lib/api';
import type { JobDetail, JobMatch, MatchDimension, SkillTree } from '@/lib/jobs-api';

/**
 * The page's contract with its reader, asserted through the real fetchers and guards.
 *
 * `@/lib/api` is the only module mocked, so every test below exercises the wiring the browser
 * gets: the client → the typed fetcher → its runtime guard → the hook → the components. That is
 * why the rejected-shape test means something — the guard really runs, and the page really
 * refuses to draw a tree it could not validate.
 *
 * Five assertions carry the product's principles:
 *
 * 1. the score breakdown explains itself and its five contributions add up to the reported score;
 * 2. **Unknown is never rendered as Missing**, and the two arrive from different lists;
 * 3. the empty state names the next action in a sentence, not a shrug;
 * 4. a shape the guard refuses fails loudly — `INVALID_RESPONSE`, the endpoint, the field, the
 *    request id — instead of producing an empty tree that looks like an answer;
 * 5. the demo button carries a real posting, and analysing it really produces an analysis.
 *
 * Panel buttons are found by their exact accessible name: the empty state offers “Load Demo JD”
 * too (it is the page's only action before anything is analysed), and that one is labelled
 * “Load Demo JD（填入左侧输入框）” so the two are distinguishable to a screen reader — and to
 * these queries.
 */

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return {
    ...actual,
    api: { ...actual.api, get: vi.fn(), post: vi.fn() },
  };
});

const mocked = vi.mocked(api);

const JOB_ID = '19708201-13a1-4d00-88ab-0a90bd4778cc';

function analysisOf(overrides: Partial<JobDetail> = {}): JobDetail {
  return {
    id: JOB_ID,
    company: '某某智能科技',
    role: '嵌入式软件工程师（电机控制方向）',
    level: null,
    location: '上海 · 张江',
    educationRequirement: '本科',
    yearsExperienceMin: 3,
    parseStatus: 'heuristic_fallback',
    parseConfidence: 1,
    source: 'paste',
    requiredCount: 4,
    preferredCount: 1,
    bonusCount: 1,
    matchScore: null,
    createdAt: '2026-09-25T16:30:54Z',
    responsibilities: ['负责基于 STM32 的无刷直流电机控制固件开发与调试；'],
    niceToHave: [],
    keywords: ['STM32', 'FreeRTOS'],
    skills: [],
    analysis: { warnings: ['结果已降级（原因：no_api_key）'] },
    descriptionChars: 459,
    ...overrides,
  };
}

function dimensions(): Record<string, MatchDimension> {
  return {
    skill: {
      key: 'skill',
      label: '技能匹配',
      score: 36.97,
      weight: 0.4,
      weighted: 14.79,
      formula: 'Σ(requirement_weight × effective_level) / Σ(requirement_weight)',
      notes: ['无证据的技能按 40% 计入'],
      evidenceIds: ['e1', 'e2', 'e3'],
    },
    experience: {
      key: 'experience',
      label: '经历匹配',
      score: 0,
      weight: 0.25,
      weighted: 0,
      formula: '100 × (0.60 × min(1, years/required) + 0.40 × min(1, relevant_roles/2))',
      notes: ['要求年限 3，候选人 0'],
      evidenceIds: [],
    },
    project: {
      key: 'project',
      label: '项目匹配',
      score: 25.85,
      weight: 0.2,
      weighted: 5.17,
      formula: '100 × (0.60 × 项目技能覆盖率 + 0.40 × 项目平均证据强度)',
      notes: ['项目数 5'],
      evidenceIds: [],
    },
    education: {
      key: 'education',
      label: '学历匹配',
      score: 100,
      weight: 0.05,
      weighted: 5,
      formula: '学历等级比对（缺失不加分也不额外惩罚）',
      notes: ['学历达到要求'],
      evidenceIds: [],
    },
    evidence: {
      key: 'evidence',
      label: '证据强度',
      score: 87,
      weight: 0.1,
      weighted: 8.7,
      formula: '100 × (0.65 × 命中技能平均置信度 + 0.35 × 有证据的命中比例)',
      notes: ['命中技能 1 个，平均置信度 0.80'],
      evidenceIds: [],
    },
  };
}

function matchOf(overrides: Partial<JobMatch> = {}): JobMatch {
  return {
    jobId: JOB_ID,
    score: 33.66,
    dimensions: dimensions(),
    strengths: [
      {
        canonicalId: 'stm32',
        displayName: 'STM32',
        requirement: 'required',
        userLevel: 'moderate',
        evidenceCount: 3,
        confidence: 0.8,
        reason: '3 条证据，置信度 0.80',
      },
    ],
    gaps: [
      {
        canonicalId: 'autosar',
        displayName: 'AUTOSAR',
        requirement: 'bonus',
        severity: 'low',
        jdEvidence: '2. 熟悉 AUTOSAR Classic 架构；',
      },
    ],
    unknowns: [
      {
        canonicalId: 'kubernetes',
        displayName: 'Kubernetes',
        requirement: 'bonus',
        reason: '简历与证据图谱中均无相关信息',
        askUser: '你是否接触过 Kubernetes？如有请补充证据。',
      },
    ],
    why: {
      formula: '0.40·skill + 0.25·experience + 0.20·project + 0.05·education + 0.10·evidence',
      algorithmVersion: 'match@1.0.0',
      evidenceUsed: ['e1', 'e2', 'e3'],
      notes: ['命中要求技能 1 个，缺口 1 个，待确认 1 个'],
      explanation: '技能维度 37 分（权重 40%），证据强度 87 分，加权合计 33.7 分。',
      computedAt: '2026-09-25T16:30:54.751149Z',
    },
    evidenceCoverage: 1,
    confidence: 0.8,
    degraded: true,
    narrative: '',
    warnings: ['结果已降级（原因：no_api_key）'],
    ...overrides,
  };
}

function skillRow(canonicalId: string | null, rawText: string, requirement = 'required') {
  return {
    canonicalId,
    rawText,
    requirement,
    weight: requirement === 'required' ? 1 : 0.3,
    jdEvidence: `${rawText} 出现在 JD 的哪一句`,
    mentions: 1,
  };
}

function treeOf(overrides: Partial<SkillTree> = {}): SkillTree {
  return {
    jobId: JOB_ID,
    role: '嵌入式软件工程师（电机控制方向）',
    company: '某某智能科技',
    required: [
      skillRow('stm32', 'STM32'),
      skillRow('autosar', 'AUTOSAR'),
      skillRow('kubernetes', 'Kubernetes'),
      skillRow('motor_control', 'Motor Control'),
    ],
    preferred: [skillRow('free_rtos', 'FreeRTOS', 'preferred')],
    bonus: [skillRow('git', 'Git', 'bonus')],
    unmatchedCount: 0,
    ...overrides,
  };
}

/** Wire the two client methods the jobs fetchers use, per path. */
function wireApi(
  options: {
    analysis?: JobDetail;
    tree?: SkillTree | (() => Promise<SkillTree>);
    match?: JobMatch;
    stored?: JobMatch | null;
  } = {},
) {
  const analysis = options.analysis ?? analysisOf();
  const tree = options.tree ?? treeOf();
  const match = options.match ?? matchOf();
  const stored = options.stored === undefined ? matchOf() : options.stored;

  mocked.post.mockImplementation((path: string) => {
    if (path === '/jobs/analyze') return Promise.resolve(analysis);
    if (path.endsWith('/match')) return Promise.resolve(match);
    return Promise.reject(new Error(`unexpected POST ${path}`));
  });
  mocked.get.mockImplementation((path: string) => {
    if (path.endsWith('/skill-tree')) {
      return typeof tree === 'function' ? tree() : Promise.resolve(tree);
    }
    if (path.endsWith('/match')) {
      // `null` is the API's "this job has not been matched yet": a 404, which the fetcher turns
      // into a state rather than an error.
      if (stored === null) {
        return Promise.reject(
          new ApiError({
            code: 'NOT_FOUND',
            message: 'This job has not been matched yet',
            requestId: 'req_not_matched',
            status: 404,
            body: null,
          }),
        );
      }
      return Promise.resolve(stored);
    }
    if (path.startsWith('/jobs/')) return Promise.resolve(analysis);
    return Promise.reject(new Error(`unexpected GET ${path}`));
  });
  return { analysis, tree, match, stored };
}

function renderView(props: { initialJobId?: string | null } = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const user = userEvent.setup();
  render(
    <QueryClientProvider client={client}>
      <JobsView initialJobId={props.initialJobId ?? null} />
    </QueryClientProvider>,
  );
  return user;
}

/** Load the demo posting and run the analysis — the page's primary path. */
async function analyzeDemo(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: 'Load Demo JD' }));
  await user.click(screen.getByRole('button', { name: 'Analyze' }));
  await screen.findByRole('heading', { name: '嵌入式软件工程师（电机控制方向）' });
}

beforeEach(() => {
  wireApi();
});

describe('the JD Intelligence page', () => {
  it('offers an actionable sentence and the demo posting before anything is analysed', () => {
    renderView();

    expect(screen.getByRole('heading', { name: 'JD Intelligence' })).toBeInTheDocument();
    expect(
      screen.getByText(
        'Understand what the role actually asks for, how well you match, and where the gaps are.',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Paste a job description to see how your evidence lines up.'),
    ).toBeInTheDocument();
    // The empty state's action loads the same demo posting as the panel's button.
    expect(screen.getAllByRole('button', { name: /Load Demo JD/ })).toHaveLength(2);
    // Nothing is claimed about a job that was never analysed.
    expect(screen.queryByLabelText('匹配分数')).toBeNull();
  });

  it('analyses the demo posting and explains the score it reports', async () => {
    const user = renderView();
    await analyzeDemo(user);

    expect(mocked.post).toHaveBeenCalledWith(
      '/jobs/analyze',
      expect.objectContaining({ text: DEMO_JD_TEXT, source: 'paste' }),
    );
    expect(await screen.findByText('某某智能科技')).toBeInTheDocument();
    expect(screen.getByLabelText('匹配分数')).toHaveTextContent('33.66');

    const why = screen.getByRole('button', { name: /Why 33\.66%/ });
    expect(why).toHaveAttribute('aria-expanded', 'false');
    await user.click(why);

    const table = within(screen.getByRole('table'));
    // Every dimension, its weight, its own score and what it contributes to the total.
    expect(table.getByText('技能匹配')).toBeInTheDocument();
    expect(table.getByText('40%')).toBeInTheDocument();
    expect(table.getByText('36.97')).toBeInTheDocument();
    expect(table.getByText('14.79')).toBeInTheDocument();
    expect(table.getByText(/Σ\(requirement_weight × effective_level\)/)).toBeInTheDocument();
    // The engine's own notes travel with the dimension they explain.
    expect(table.getByText(/无证据的技能按 40% 计入/)).toBeInTheDocument();
    expect(table.getByText(/要求年限 3，候选人 0/)).toBeInTheDocument();
    // …and the panel shows the arithmetic agreeing with the headline number.
    expect(screen.getByText(/Σ 加权 33.66 \/ 报告分数 33.66/)).toBeInTheDocument();
    expect(why).toHaveAttribute('aria-expanded', 'true');
  });

  it('keeps Unknown separate from Missing, on the tree and in the conclusions', async () => {
    const user = renderView();
    await analyzeDemo(user);

    const missingRow = document.querySelector('[data-verdict="missing"]') as HTMLElement;
    const unknownRow = document.querySelector('[data-verdict="unknown"]') as HTMLElement;
    expect(missingRow).not.toBeNull();
    expect(unknownRow).not.toBeNull();

    expect(within(missingRow).getByText('Missing')).toBeInTheDocument();
    expect(within(unknownRow).getByText('Unknown')).toBeInTheDocument();
    // The two states carry different evidence: a severity vs the engine's own question.
    expect(within(missingRow).getByText(/severity low/)).toBeInTheDocument();
    expect(within(unknownRow).getByText(/你是否接触过 Kubernetes/)).toBeInTheDocument();
    expect(within(missingRow).queryByText(/你是否接触过/)).toBeNull();

    // And the conclusion lists never mix them: `kubernetes` is an unknown, never a gap.
    expect(document.querySelector('[data-unknown="kubernetes"]')).not.toBeNull();
    expect(document.querySelector('[data-gap="kubernetes"]')).toBeNull();
    expect(document.querySelector('[data-gap="autosar"]')).not.toBeNull();

    // A requirement the payload never classified says so, instead of being guessed into a gap.
    expect(document.querySelector('[data-verdict="unreported"]')).not.toBeNull();
    expect(screen.getAllByText(/Not in result/).length).toBeGreaterThan(0);
  });

  it('says which stage is running while the analysis is in flight, without faking progress', async () => {
    let release: (value: JobDetail) => void = () => {};
    mocked.post.mockImplementation((path: string) => {
      if (path === '/jobs/analyze') {
        return new Promise<JobDetail>((resolve) => {
          release = resolve;
        });
      }
      return Promise.resolve(matchOf());
    });

    const user = renderView();
    await user.click(screen.getByRole('button', { name: 'Load Demo JD' }));
    await user.click(screen.getByRole('button', { name: 'Analyze' }));

    const list = await screen.findByRole('list', { name: 'Analysis steps' });
    const current = within(list).getByText('Parsing job description').closest('li');
    expect(current).toHaveAttribute('aria-current', 'step');
    // The stages after the in-flight one are explicitly not claimed.
    expect(within(list).getByText('Building gap analysis').closest('li')).not.toHaveAttribute(
      'aria-current',
    );
    // And the page tells the reader why there is no per-step progress to show.
    expect(screen.getByText(/服务端不上报中间阶段/)).toBeInTheDocument();
    expect(screen.getByText(/已等待/)).toBeInTheDocument();

    release(analysisOf());
    await screen.findByRole('heading', { name: '嵌入式软件工程师（电机控制方向）' });
    // Once the response landed, the list becomes the audit record of what it proved.
    await waitFor(() => expect(screen.getByText(/5\/5 完成/)).toBeInTheDocument());
  });

  it('fails loudly when the skill tree does not match the documented shape', async () => {
    // `preferred` and `bonus` missing: a tree drawn as "0 requirements" would look like an
    // answer, so the guard refuses it and the page names the endpoint that misbehaved.
    wireApi({
      tree: () => Promise.resolve({ jobId: JOB_ID, required: [] } as unknown as SkillTree),
    });
    renderView({ initialJobId: JOB_ID });

    // The query retries once, so the error state arrives after the retry delay.
    expect(await screen.findByText('技能树读取失败', {}, { timeout: 5_000 })).toBeInTheDocument();
    expect(screen.getByText('INVALID_RESPONSE')).toBeInTheDocument();
    expect(screen.getByText(/三层 required\/preferred\/bonus 不完整/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /重试/ })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /查看状态页/ })).toHaveAttribute('href', '/system');
    // No empty tree is drawn behind the error.
    expect(screen.queryByText('JD Skill Tree')).toBeNull();
  });

  it('surfaces a failed analysis with its request id instead of a stack trace', async () => {
    mocked.post.mockRejectedValue(
      new ApiError({
        code: 'VALIDATION_ERROR',
        message: "unknown source 'nope'",
        requestId: 'req_01M3CPAYVZSS91ZZR9GCKFFFSN',
        status: 400,
        body: null,
      }),
    );

    const user = renderView();
    await user.click(screen.getByRole('button', { name: 'Load Demo JD' }));
    await user.click(screen.getByRole('button', { name: 'Analyze' }));

    expect(await screen.findByText('岗位解析失败')).toBeInTheDocument();
    expect(screen.getByText('VALIDATION_ERROR')).toBeInTheDocument();
    expect(screen.getByText('req_01M3CPAYVZSS91ZZR9GCKFFFSN')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /查看状态页/ })).toHaveAttribute('href', '/system');
  });

  it('prints an unreported coverage as a dash, not as 0%, when it reads a stored match', async () => {
    // The stored-match endpoint serialises `evidenceCoverage: 0.0` while never computing it, so a
    // page that printed the number would report 0% for a match the live endpoint calls 100%.
    wireApi({
      stored: matchOf({ evidenceCoverage: 0, confidence: 0, degraded: false, warnings: [] }),
    });
    renderView({ initialJobId: JOB_ID });

    await screen.findByRole('heading', { name: '嵌入式软件工程师（电机控制方向）' });
    const coverage = screen.getByText('Evidence Coverage').closest('div') as HTMLElement;
    expect(within(coverage).getByText('—')).toBeInTheDocument();
    expect(
      within(coverage).getByText(/GET \/jobs\/\{id\}\/match 不返回该字段/),
    ).toBeInTheDocument();
    // `degraded` is not reported either, so no badge claims the result was (or was not) degraded.
    expect(screen.queryByText('degraded')).toBeNull();
    expect(screen.getAllByText('GET /jobs/{id}/match').length).toBeGreaterThan(0);
  });

  it('says a posting has no stored match rather than showing an old score', async () => {
    wireApi({ stored: null });
    renderView({ initialJobId: JOB_ID });

    await screen.findByRole('heading', { name: '嵌入式软件工程师（电机控制方向）' });
    expect(screen.getByLabelText('匹配分数')).toHaveTextContent('—');
    expect(screen.getByText('match 等待计算')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重新计算匹配' })).toBeInTheDocument();
  });
});
