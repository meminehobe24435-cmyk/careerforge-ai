import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ApiError } from '@careerforge/shared';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { InterviewView } from '@/components/interview/interview-view';
import {
  FEEDBACK,
  QUESTION_ONE,
  QUESTION_TWO,
  SESSION_ID,
  capabilities,
  demoted,
  evaluation,
  held,
  jobList,
  promoted,
  scorecard,
  session,
  turnResponse,
} from '@/components/interview/interview-fixtures';
import { interviewApi } from '@/lib/interview-api';
import { interviewTargetApi } from '@/lib/interview-target-api';

/**
 * One answer, end to end, and the failure that must not cost the session.
 *
 * The four assertions that matter:
 *
 * 1. the answer text goes to `POST /ai/interview/{id}/answer`, and the *next question plus its
 *    evaluation* are what come back — the page has to append both, not replace one with the other;
 * 2. the difficulty notice appears **only** when the API reports that the level actually moved.
 *    `_adapt` sends a `difficulty_change` on every turn, including "kept the same level" ones, so a
 *    notice rendered unconditionally would be permanently on screen and therefore meaningless;
 * 3. a failed turn keeps the session: the transcript, the question and the typed answer all stay,
 *    with a retry that resubmits *that* answer;
 * 4. retrying re-reads the session first, because a timed-out POST may have been processed —
 *    re-posting blindly would put the same answer in the transcript twice.
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
const ANSWER = '我用 None 作为默认值，避免可变对象在多次调用之间被共享。';

function renderWorkspace() {
  window.history.replaceState({}, '', `/app/interview?session=${SESSION_ID}`);
  mocked.session.mockResolvedValue(session());
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <InterviewView />
    </QueryClientProvider>,
  );
}

async function submitAnswer(text = ANSWER) {
  const box = await screen.findByLabelText('你的回答');
  await userEvent.type(box, text);
  await userEvent.click(screen.getByRole('button', { name: /提交回答/ }));
  return box;
}

beforeEach(() => {
  window.localStorage.clear();
  vi.clearAllMocks();
  mockedTargets.targetJobs.mockResolvedValue(jobList());
  mockedTargets.capabilities.mockResolvedValue(capabilities());
});

describe('the workspace', () => {
  it('appends the next question and its evaluation after an answer', async () => {
    mocked.answer.mockResolvedValue(turnResponse());
    renderWorkspace();

    await screen.findByText(QUESTION_ONE);
    expect(screen.getByText(/第 1 题/)).toBeInTheDocument();

    const box = await submitAnswer();

    await waitFor(() => expect(mocked.answer).toHaveBeenCalledWith(SESSION_ID, ANSWER));
    // The next question arrived…
    expect(await screen.findByText(QUESTION_TWO)).toBeInTheDocument();
    expect(screen.getByText(/第 2 题/)).toBeInTheDocument();
    // …and so did the evaluation of the answer that produced it.
    expect(screen.getByText(FEEDBACK)).toBeInTheDocument();
    expect(screen.getByText('68.6')).toBeInTheDocument();
    expect(screen.getByText('未提及「cost」')).toBeInTheDocument();
    // The form is cleared only after the round trip succeeded.
    expect(box).toHaveValue('');
    // The session column counts topics and questions straight off the transcript it was given:
    // two interviewer turns (python, fastapi) against a three-topic plan.
    expect(screen.getByText(/2 \/ 3 个计划主题 · 已问 2 题/)).toBeInTheDocument();
  });

  it('shows the difficulty notice only when the level actually moved', async () => {
    mocked.answer.mockResolvedValue(
      turnResponse({ evaluation: evaluation({ score: 83.46 }), difficultyChange: promoted() }),
    );
    renderWorkspace();
    await screen.findByText(QUESTION_ONE);
    await submitAnswer();

    const notice = await screen.findByText('难度提升');
    const block = notice.closest('[data-difficulty-notice]') as HTMLElement;
    expect(block).toHaveAttribute('data-difficulty-notice', 'up');
    // The reason is the API's own sentence, not a paraphrase.
    expect(
      within(block).getByText(/原因：回答得分 83，高于 75，进入更深一层追问/),
    ).toBeInTheDocument();
    expect(within(block).getByText(/L1 概念 → L2 工程/)).toBeInTheDocument();
  });

  it('says nothing about difficulty when the API reports no change', async () => {
    mocked.answer.mockResolvedValue(turnResponse({ difficultyChange: held() }));
    renderWorkspace();
    await screen.findByText(QUESTION_ONE);
    await submitAnswer();

    await screen.findByText(QUESTION_TWO);
    expect(screen.queryByText('难度提升')).toBeNull();
    expect(screen.queryByText('难度下降')).toBeNull();
    expect(document.querySelector('[data-difficulty-notice]')).toBeNull();
    // The API's own "no change" sentence is still shown, so the silence is explained.
    expect(screen.getByText(/难度保持/)).toBeInTheDocument();
    expect(screen.getByText(/回答得分 69，保持当前难度/)).toBeInTheDocument();
  });

  it('renders a demotion with the API reason', async () => {
    mocked.answer.mockResolvedValue(turnResponse({ difficultyChange: demoted() }));
    renderWorkspace();
    await screen.findByText(QUESTION_ONE);
    await submitAnswer();

    expect(await screen.findByText('难度下降')).toBeInTheDocument();
    expect(screen.getByText(/退回上一层确认基础/)).toBeInTheDocument();
  });

  it('submits the skip marker through the real endpoint (there is no skip route)', async () => {
    mocked.answer.mockResolvedValue(turnResponse());
    renderWorkspace();
    await screen.findByText(QUESTION_ONE);

    await userEvent.click(screen.getByRole('button', { name: /跳过/ }));

    await waitFor(() =>
      expect(mocked.answer).toHaveBeenCalledWith(SESSION_ID, '（未作答，跳过本题）'),
    );
    expect(await screen.findByText(QUESTION_TWO)).toBeInTheDocument();
  });

  it('ends the interview through finish and shows the scorecard', async () => {
    mocked.finish.mockResolvedValue(session({ status: 'completed', scorecard: scorecard() }));
    renderWorkspace();
    await screen.findByText(QUESTION_ONE);

    await userEvent.click(screen.getByRole('button', { name: /结束面试/ }));

    await waitFor(() => expect(mocked.finish).toHaveBeenCalledWith(SESSION_ID));
    expect(await screen.findByText('评分卡')).toBeInTheDocument();
  });
});

describe('a failed turn', () => {
  const failure = new ApiError({
    code: 'NETWORK_ERROR',
    message: '无法连接到后端服务，请确认 API 已启动',
    requestId: 'req_turn_failed',
    status: 0,
    isNetworkError: true,
  });

  it('keeps the session and the typed answer, and reports the code and request id', async () => {
    mocked.answer.mockRejectedValue(failure);
    renderWorkspace();

    const box = await submitAnswer();

    const alert = await screen.findByRole('alert');
    expect(within(alert).getByText('本轮回答没有提交成功')).toBeInTheDocument();
    expect(within(alert).getByText('NETWORK_ERROR')).toBeInTheDocument();
    expect(within(alert).getByText('req_turn_failed')).toBeInTheDocument();
    expect(within(alert).getByText(/会话没有丢失/)).toBeInTheDocument();
    // The session is still on screen, and the answer is still in the box.
    expect(screen.getByText(QUESTION_ONE)).toBeInTheDocument();
    expect(box).toHaveValue(ANSWER);
  });

  it('re-reads before resubmitting, and does not double-post an answer that already landed', async () => {
    mocked.answer.mockRejectedValue(failure);
    renderWorkspace();
    await submitAnswer();
    await screen.findByRole('alert');

    // The re-read shows the answer *did* reach the backend, so the retry must not post it again.
    mocked.session.mockResolvedValue(
      session({
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
            content: ANSWER,
            topic: 'python',
            level: null,
            score: 68.58,
          },
          {
            turnIndex: 2,
            role: 'interviewer',
            content: QUESTION_TWO,
            topic: 'fastapi',
            level: 'concept',
            score: null,
          },
        ],
      }),
    );

    await userEvent.click(screen.getByRole('button', { name: /重试这一轮/ }));

    await waitFor(() => expect(mocked.session).toHaveBeenCalledWith(SESSION_ID));
    expect(mocked.answer).toHaveBeenCalledTimes(1);
    expect(await screen.findByText(QUESTION_TWO)).toBeInTheDocument();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('resubmits the same text when the answer never arrived', async () => {
    mocked.answer.mockRejectedValueOnce(failure).mockResolvedValue(turnResponse());
    renderWorkspace();
    await submitAnswer();
    await screen.findByRole('alert');

    mocked.session.mockResolvedValue(session());
    await userEvent.click(screen.getByRole('button', { name: /重试这一轮/ }));

    await waitFor(() => expect(mocked.answer).toHaveBeenCalledTimes(2));
    expect(mocked.answer).toHaveBeenLastCalledWith(SESSION_ID, ANSWER);
    expect(await screen.findByText(QUESTION_TWO)).toBeInTheDocument();
  });
});
