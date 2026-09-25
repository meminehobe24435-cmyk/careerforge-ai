import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ApiError } from '@careerforge/shared';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { InterviewView } from '@/components/interview/interview-view';
import {
  JOB_ID,
  QUESTION_ONE,
  SESSION_ID,
  capabilities,
  jobDetail,
  jobList,
  session,
  skillTree,
} from '@/components/interview/interview-fixtures';
import { interviewApi } from '@/lib/interview-api';
import { interviewTargetApi } from '@/lib/interview-target-api';

/**
 * The setup path, and the one thing it must get right: **the session that starts is a real one.**
 *
 * The assertions are about arguments, not about pixels — the job goes to the API as the parsed
 * `JDAnalysis` object read back from `GET /jobs/{id}` (not as a bare id, which the endpoint does
 * not accept), the mode and starting difficulty travel with it, and the returned session id lands
 * in the URL so a refresh resumes rather than restarts.
 */

vi.mock('@/lib/interview-api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/interview-api')>();
  return {
    ...actual,
    interviewApi: {
      startSession: vi.fn(),
      answer: vi.fn(),
      finish: vi.fn(),
      session: vi.fn(),
      abandon: vi.fn(),
    },
  };
});

vi.mock('@/lib/interview-target-api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/interview-target-api')>();
  return {
    ...actual,
    interviewTargetApi: {
      targetJobs: vi.fn(),
      jobDetail: vi.fn(),
      analyseJob: vi.fn(),
      skillTree: vi.fn(),
      capabilities: vi.fn(),
    },
  };
});

const mocked = vi.mocked(interviewApi);
const mockedTargets = vi.mocked(interviewTargetApi);

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <InterviewView />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  window.localStorage.clear();
  window.history.replaceState({}, '', '/app/interview');
  vi.clearAllMocks();
  mockedTargets.targetJobs.mockResolvedValue(jobList());
  mockedTargets.capabilities.mockResolvedValue(capabilities());
  mockedTargets.skillTree.mockResolvedValue(skillTree());
  mockedTargets.jobDetail.mockResolvedValue(jobDetail());
});

describe('the setup screen', () => {
  it('offers the real interview modes and refuses to offer a mixed one', async () => {
    renderPage();
    await screen.findByLabelText('目标岗位');

    for (const mode of ['technical', 'project', 'behavioral', 'system_design', 'hr']) {
      expect(await screen.findByLabelText(new RegExp(`mode=${mode}`))).toBeInTheDocument();
    }
    expect(screen.queryByLabelText(/mode=mixed/)).toBeNull();
    // The brief's "stress interview" is in the enum but has no distinct implementation on the
    // zero-key path, so it is not offered as a choice.
    expect(screen.queryByLabelText(/mode=stress/)).toBeNull();
  });

  it('says what to do when the account has no analysed job yet', async () => {
    mockedTargets.targetJobs.mockResolvedValue({ items: [], total: 0 });
    renderPage();

    expect(await screen.findByText('选择一个岗位并开始一次会话')).toBeInTheDocument();
    expect(screen.getByText(/Choose a role and start a session/)).toBeInTheDocument();
  });

  it('cannot start until a target job is chosen', async () => {
    renderPage();
    const start = await screen.findByRole('button', { name: /开始面试/ });
    expect(start).toBeDisabled();

    await userEvent.selectOptions(await screen.findByLabelText('目标岗位'), JOB_ID);
    await waitFor(() => expect(start).toBeEnabled());
  });

  it('starts a real session with the stored analysis, and puts the id in the URL', async () => {
    mocked.startSession.mockResolvedValue(session());
    renderPage();

    await userEvent.selectOptions(await screen.findByLabelText('目标岗位'), JOB_ID);
    await userEvent.click(screen.getByRole('radio', { name: /L2 工程/ }));
    await userEvent.click(screen.getByRole('button', { name: /开始面试/ }));

    await waitFor(() => expect(mocked.startSession).toHaveBeenCalledTimes(1));
    expect(mockedTargets.jobDetail).toHaveBeenCalledWith(JOB_ID);
    expect(mocked.startSession).toHaveBeenCalledWith({
      mode: 'technical',
      job: jobDetail().analysis,
      difficulty: 2,
    });

    // The workspace took over, and the URL is what a refresh will read.
    expect(await screen.findByText(QUESTION_ONE)).toBeInTheDocument();
    expect(window.location.search).toBe(`?session=${SESSION_ID}`);
  });

  it('parses a pasted JD and selects the posting it created', async () => {
    mockedTargets.targetJobs.mockResolvedValue({ items: [], total: 0 });
    mockedTargets.analyseJob.mockResolvedValue(jobList().items[0]!);
    renderPage();

    const textarea = await screen.findByLabelText(/粘贴岗位描述/);
    await userEvent.type(
      textarea,
      '招聘后端工程师，要求熟悉 Python 与 FastAPI，负责接口设计与性能优化。',
    );
    await userEvent.click(screen.getByRole('button', { name: /解析并选择岗位/ }));

    await waitFor(() => expect(mockedTargets.analyseJob).toHaveBeenCalledTimes(1));
    expect(mockedTargets.analyseJob.mock.calls[0]?.[0]).toContain('FastAPI');
    // The analysis ran, so the same page can now show the posting's requirements.
    await waitFor(() => expect(mockedTargets.skillTree).toHaveBeenCalledWith(JOB_ID));
  });

  it('states the boundaries it cannot change', async () => {
    renderPage();
    await screen.findByLabelText('目标岗位');

    // No focus input, and the reason is on screen rather than left to be discovered.
    expect(screen.queryByLabelText(/关注方向|focus/i)).toBeNull();
    expect(screen.getByText(/只接受 mode \/ job \/ profile \/ difficulty/)).toBeInTheDocument();
    expect(await screen.findByText('in-process')).toBeInTheDocument();
  });
});

describe('resuming from the URL', () => {
  it('rehydrates a session instead of showing the setup form', async () => {
    window.history.replaceState({}, '', `/app/interview?session=${SESSION_ID}`);
    const resumed = session({
      currentLevel: 'engineering',
      turns: [
        {
          turnIndex: 0,
          role: 'interviewer',
          content: QUESTION_ONE,
          topic: 'python',
          level: 'concept',
          score: null,
        },
        {
          turnIndex: 1,
          role: 'candidate',
          content: '我用 None 作为默认值，避免共享可变对象。',
          topic: 'python',
          level: null,
          score: 72.5,
        },
        {
          turnIndex: 2,
          role: 'interviewer',
          content: 'FastAPI 的依赖注入是怎么工作的？',
          topic: 'fastapi',
          level: 'engineering',
          score: null,
        },
      ],
    });
    mocked.session.mockResolvedValue(resumed);

    renderPage();

    expect(await screen.findByText('FastAPI 的依赖注入是怎么工作的？')).toBeInTheDocument();
    expect(mocked.session).toHaveBeenCalledWith(SESSION_ID);
    // The transcript survived, and the level came from the server rather than from a guess.
    // (The badge and the difficulty ladder both name the level, so this is a count, not a match.)
    expect(screen.getAllByText(/L2 工程/).length).toBeGreaterThan(0);
    expect(screen.getByText(/第 2 题/)).toBeInTheDocument();
    expect(screen.queryByText('会话设置')).toBeNull();
  });

  it('explains an expired link (in-process store) and offers a new session', async () => {
    window.history.replaceState({}, '', `/app/interview?session=${SESSION_ID}`);
    mocked.session.mockRejectedValue(
      new ApiError({
        code: 'NOT_FOUND',
        message: 'Interview session not found',
        requestId: 'req_gone',
        status: 404,
      }),
    );

    renderPage();

    // `retry: 1` on the session query means the first failure is retried before the page gives up.
    expect(
      await screen.findByText('这个会话已经不在后端了', {}, { timeout: 8000 }),
    ).toBeInTheDocument();
    expect(screen.getByText('req_gone')).toBeInTheDocument();
    const start = screen.getByRole('button', { name: '开始新的会话' });
    await userEvent.click(start);
    await waitFor(() => expect(window.location.search).toBe(''));
    expect(await screen.findByLabelText('目标岗位')).toBeInTheDocument();
  });
});
