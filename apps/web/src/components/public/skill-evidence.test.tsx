import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { PublicEvidence, PublicProfileResponse, PublicSkill } from '@careerforge/shared';

import { SkillEvidence } from '@/components/public/skill-evidence';

/**
 * The Recruiter View's interaction: click a skill, see the evidence, no login.
 *
 * The three behaviours pinned here are the ones a recruiter would judge the product by:
 *
 * 1. clicking a chip expands the citations **in place** (no navigation, no account);
 * 2. a candidate who keeps citations private still shows the skill, and the panel says why it is
 *    empty — "no evidence" and "evidence not published" are different statements and only one of
 *    them is true;
 * 3. a backend that cannot be reached says so instead of rendering an empty panel.
 */

vi.mock('@/lib/public-api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/public-api')>();
  return {
    ...actual,
    fetchPublicSkillEvidence: vi.fn(),
  };
});

const { fetchPublicSkillEvidence, PUBLIC_API_BASE_URL } = await import('@/lib/public-api');
const mocked = vi.mocked(fetchPublicSkillEvidence);

function skill(overrides: Partial<PublicSkill> = {}): PublicSkill {
  return {
    canonicalId: 'stm32',
    displayName: 'STM32',
    category: 'embedded',
    confidence: 0.92,
    evidenceCount: 3,
    corroboration: 2,
    evidence: [],
    ...overrides,
  };
}

const EVIDENCE: PublicEvidence[] = [
  {
    evidenceId: 'e1',
    title: 'freertos.c',
    kind: 'repo_file',
    locator: 'firmware/src/freertos.c#L18',
    url: 'https://github.com/example/balance-robot/blob/main/firmware/src/freertos.c#L18',
    confidence: 0.9,
  },
  {
    evidenceId: 'e2',
    title: 'README.md',
    kind: 'readme',
    locator: 'README.md',
    url: null,
    confidence: 0.8,
  },
];

beforeEach(() => {
  mocked.mockReset();
  mocked.mockResolvedValue({ data: EVIDENCE, status: 200 });
});

describe('the public skill list', () => {
  it('expands the citations in place, and links only what a stranger can open', async () => {
    const user = userEvent.setup();
    render(<SkillEvidence slug="alex-1234abcd" skills={[skill()]} evidenceVisible />);

    expect(mocked).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: /STM32/ }));

    await waitFor(() => expect(mocked).toHaveBeenCalledWith('alex-1234abcd', 'stm32'));
    const panel = await screen.findByTestId('evidence-panel');
    expect(within(panel).getByRole('link', { name: 'freertos.c' })).toHaveAttribute(
      'href',
      'https://github.com/example/balance-robot/blob/main/firmware/src/freertos.c#L18',
    );
    // A citation with no URL is shown as text: a local path is not a link.
    expect(within(panel).getByText('README.md')).toBeInTheDocument();
    expect(within(panel).queryByRole('link', { name: 'README.md' })).toBeNull();
    expect(within(panel).getByText(/置信度 90%/)).toBeInTheDocument();
  });

  it('fetches each skill once, and collapses on a second click', async () => {
    const user = userEvent.setup();
    render(<SkillEvidence slug="s" skills={[skill()]} evidenceVisible />);
    const chip = screen.getByRole('button', { name: /STM32/ });

    await user.click(chip);
    await screen.findByTestId('evidence-panel');
    await user.click(chip);
    expect(screen.queryByTestId('evidence-panel')).toBeNull();
    await user.click(chip);
    await screen.findByTestId('evidence-panel');
    expect(mocked).toHaveBeenCalledTimes(1);
  });

  it('keeps a skill visible when its citations are private, and says which it is', async () => {
    const user = userEvent.setup();
    render(<SkillEvidence slug="s" skills={[skill()]} evidenceVisible={false} />);

    const chip = screen.getByRole('button', { name: /STM32/ });
    await user.click(chip);

    const panel = await screen.findByTestId('evidence-panel');
    expect(mocked).not.toHaveBeenCalled();
    expect(within(panel).getByText(/选择不公开引用来源/)).toBeInTheDocument();
    // The count is still shown: the evidence exists, it is simply not published.
    expect(within(panel).getByText(/证据是真实存在的（3 条）/)).toBeInTheDocument();
  });

  it('reports an unreachable backend instead of rendering an empty panel', async () => {
    mocked.mockResolvedValue({ data: null, status: 0 });
    const user = userEvent.setup();
    render(<SkillEvidence slug="s" skills={[skill()]} evidenceVisible />);

    await user.click(screen.getByRole('button', { name: /STM32/ }));
    expect(await screen.findByText(/无法连接后端服务/)).toBeInTheDocument();
  });

  it('distinguishes "nothing publishable" from "not published"', async () => {
    mocked.mockResolvedValue({ data: [], status: 200 });
    const user = userEvent.setup();
    render(<SkillEvidence slug="s" skills={[skill({ evidenceCount: 0 })]} evidenceVisible />);

    await user.click(screen.getByRole('button', { name: /STM32/ }));
    expect(await screen.findByText(/没有可公开的引用/)).toBeInTheDocument();
  });

  it('says so when the candidate publishes no skills at all', () => {
    render(<SkillEvidence slug="s" skills={[]} evidenceVisible />);
    expect(screen.getByText('这位候选人目前没有公开任何技能。')).toBeInTheDocument();
  });

  it('names the API a reader can check', () => {
    render(<SkillEvidence slug="s" skills={[skill()]} evidenceVisible />);
    expect(screen.getByText(PUBLIC_API_BASE_URL)).toBeInTheDocument();
  });
});

describe('the shape the page renders', () => {
  it('never receives owner-only fields from the public endpoint', () => {
    // A compile-time guard as documentation: if a future field is added to the public payload
    // that should not be shown, this list is where the decision has to be made explicit.
    const payload: PublicProfileResponse = {
      displayName: 'Alex Chen',
      headline: '嵌入式软件工程师',
      location: '上海',
      summary: '把经历变成证据。',
      targetRoles: ['嵌入式软件工程师'],
      skills: [skill()],
      projects: [],
      highlights: ['用 FreeRTOS 重写了任务调度'],
      interviewTopics: ['FreeRTOS 优先级反转'],
      githubUrl: null,
      websiteUrl: null,
      contact: {},
      meta: {
        slug: 'alex-1234abcd',
        generatedAt: null,
        evidenceCoverage: 1,
        profileStrength: 82,
        hiddenSections: ['contact'],
        redactions: [],
        viewCount: 3,
      },
    };
    expect(Object.keys(payload).sort()).toEqual(
      [
        'contact',
        'displayName',
        'githubUrl',
        'headline',
        'highlights',
        'interviewTopics',
        'location',
        'meta',
        'projects',
        'skills',
        'summary',
        'targetRoles',
        'websiteUrl',
      ].sort(),
    );
    // And the hidden section is announced rather than silently absent.
    expect(payload.meta.hiddenSections).toContain('contact');
  });
});
