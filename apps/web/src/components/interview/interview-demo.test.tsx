import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, renderHook, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';

import { demoSession } from '@/components/interview/demo-script';
import { InterviewView } from '@/components/interview/interview-view';
import {
  JOB_ID,
  QUESTION_ONE,
  SESSION_ID,
  capabilities,
  jobDetail,
  jobList,
  session,
  turnResponse,
} from '@/components/interview/interview-fixtures';
import { useInterviewController, writeSessionParam } from '@/hooks/use-interview';
import { isDemoSession } from '@/hooks/use-interview-setup';
import { interviewApi } from '@/lib/interview-api';
import { interviewTargetApi } from '@/lib/interview-target-api';

/**
 * The Demo session.
 *
 * It is a **fast path through the real state machine**, and this is where that claim is checked:
 * the sample posting is parsed by `POST /jobs/analyze`, the job is read back through
 * `GET /jobs/{id}`, the session is started through `POST /ai/interview/start`, and every scripted
 * answer is submitted to `POST /ai/interview/{id}/answer` in turn — after which the session is
 * closed by `finish`. Nothing is replayed: the difficulty transitions and the scorecard the demo
 * ends on are produced by the backend.
 *
 * The page is also labelled: a reload of a demo session must not present scripted answers as the
 * reader's own, so the id is remembered locally and the banner is asserted below.
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

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  window.localStorage.clear();
  window.history.replaceState({}, '', '/app/interview');
  vi.clearAllMocks();
  mockedTargets.targetJobs.mockResolvedValue(jobList());
  mockedTargets.capabilities.mockResolvedValue(capabilities());
  mockedTargets.analyseJob.mockResolvedValue(jobList().items[0]!);
  mockedTargets.jobDetail.mockResolvedValue(jobDetail());
  mocked.startSession.mockResolvedValue(session());
  mocked.finish.mockResolvedValue(session());
});

describe('the demo run', () => {
  it('drives the real endpoints in order, with scripted answer text', async () => {
    const answers: string[] = [];
    mocked.answer.mockImplementation(async (_id: string, text: string) => {
      answers.push(text);
      return turnResponse();
    });

    const { result } = renderHook(
      // The URL is written by the hook that owns it, so the demo's landing spot is asserted for real.
      () => useInterviewController(null, (id) => writeSessionParam(id)),
      { wrapper },
    );

    let created: unknown = null;
    await act(async () => {
      created = await result.current.runDemo({ ...demoSession, stepPauseMs: 0 });
    });

    // 1. the sample posting is parsed for real…
    expect(mockedTargets.analyseJob).toHaveBeenCalledTimes(1);
    expect(mockedTargets.analyseJob.mock.calls[0]?.[0]).toContain('FastAPI');
    // 2. …read back as the stored analysis (`warnings`-free), and used to start the session.
    expect(mockedTargets.jobDetail).toHaveBeenCalledWith(JOB_ID);
    expect(mocked.startSession).toHaveBeenCalledWith({
      mode: 'technical',
      job: jobDetail().analysis,
      difficulty: 1,
    });
    // 3. every answer went through the answer endpoint, not into a local array.
    expect(answers).toHaveLength(demoSession.steps);
    expect(answers[0]).toBe(demoSession.answerFor(0, 'python'));
    expect(answers[1]).toBe(demoSession.answerFor(1, 'fastapi'));
    expect(mocked.answer.mock.calls[0]?.[0]).toBe(SESSION_ID);
    // 4. and the session was closed by finish, which is what produces the scorecard.
    expect(mocked.finish).toHaveBeenCalledWith(SESSION_ID);
    expect(created).not.toBeNull();
    // 5. it is a session like any other: resumable, and marked as a demo.
    expect(isDemoSession(SESSION_ID)).toBe(true);
    expect(window.location.search).toBe(`?session=${SESSION_ID}`);
  });

  it('stops early on request instead of forcing the whole script', async () => {
    mocked.answer.mockResolvedValue(turnResponse());
    const { result } = renderHook(() => useInterviewController(null, vi.fn()), { wrapper });

    await act(async () => {
      const running = result.current.runDemo({ ...demoSession, stepPauseMs: 0 });
      result.current.cancelDemo();
      await running;
    });

    expect(mocked.answer).not.toHaveBeenCalled();
    expect(mocked.finish).not.toHaveBeenCalled();
  });

  it('labels a demo session in the workspace, even after a reload', async () => {
    window.localStorage.setItem('careerforge.interview.demo', JSON.stringify([SESSION_ID]));
    window.history.replaceState({}, '', `/app/interview?session=${SESSION_ID}`);
    mocked.session.mockResolvedValue(session());

    render(<InterviewView />, { wrapper });

    expect(await screen.findByText(QUESTION_ONE)).toBeInTheDocument();
    // The badge in the header and the banner above the workspace both say it.
    expect(screen.getAllByText('Demo session').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/不是回放/)).toBeInTheDocument();
  });

  it('does not label a normal session as a demo', async () => {
    window.history.replaceState({}, '', `/app/interview?session=${SESSION_ID}`);
    mocked.session.mockResolvedValue(session());

    render(<InterviewView />, { wrapper });
    expect(await screen.findByText(QUESTION_ONE)).toBeInTheDocument();
    expect(screen.queryByText('Demo session')).toBeNull();
  });
});
