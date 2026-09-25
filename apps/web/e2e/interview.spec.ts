import { INTERVIEW_ANSWER } from './helpers/dataset';
import { expect, test } from './helpers/fixtures';
import { apiFromPage } from './helpers/session';
import type { InterviewSession, InterviewTurnResult } from './helpers/api';

/**
 * E2E 5 · Interview simulator — three turns, deterministic and free.
 *
 * **There is no interview UI.** `nav-config.ts` badges `/app/interview` `PHASE 8` and renders it as
 * a non-clickable item, and the command palette's `start-interview` entry is a navigation stub, so
 * there is no screen to type an answer into. The session is driven through the documented endpoints
 * (`docs/API.md` §2.8), called **from the page** with the browser's own session, which keeps the
 * test honest about the transport the future UI will use.
 *
 * The provider is the zero-key heuristic one, so this costs nothing and is deterministic — but
 * "deterministic" is not the same as "informative": the heuristic question generator repeats the
 * same prompt across turns (it has no model to vary it with). The assertions therefore do not
 * require the question *text* to change; they require the **session state** to advance, which is
 * what the API actually promises: the turn index grows, the evaluation lands with a score, the
 * difficulty decision is recorded, and the persisted session gains the candidate's turn.
 */
test.describe('Interview', () => {
  test('a technical interview loads a question and advances one turn at a time', async ({
    signedInPage: page,
  }) => {
    await page.goto('/app/dashboard');

    const start = await apiFromPage<InterviewSession>(page, '/ai/interview/start', {
      method: 'POST',
      body: { mode: 'technical', difficulty: 1 },
    });
    expect(start.status).toBe(200);
    const started = start.data;
    expect(started.session_id.length).toBeGreaterThan(0);
    expect(started.mode).toBe('technical');
    expect(started.status).toBe('in_progress');
    expect(started.current_level.length).toBeGreaterThan(0);
    expect(
      started.plan.length,
      'the session must have a plan before it asks anything',
    ).toBeGreaterThan(0);
    expect(started.turns).toHaveLength(1);

    // The first question is on screen (in the payload) before anything is answered.
    const firstQuestion = started.turns[0];
    if (!firstQuestion) throw new Error('POST /ai/interview/start returned no turn');
    expect(firstQuestion.role).toBe('interviewer');
    expect(firstQuestion.content.trim().length).toBeGreaterThan(0);

    const answer = async (): Promise<InterviewTurnResult> => {
      const call = await apiFromPage<InterviewTurnResult>(
        page,
        `/ai/interview/${started.session_id}/answer`,
        { method: 'POST', body: { answer: INTERVIEW_ANSWER } },
      );
      expect(call.status).toBe(200);
      return call.data;
    };

    // ── turn 1 ───────────────────────────────────────────────────────────────────────────────
    const afterFirst = await answer();
    expect(afterFirst.status).toBe('in_progress');
    const firstEvaluation = afterFirst.evaluation;
    if (!firstEvaluation) throw new Error('answering produced no evaluation');
    expect(firstEvaluation.score).toBeGreaterThan(0);
    expect(firstEvaluation.feedback.trim().length).toBeGreaterThan(0);
    // A score nobody can decompose is not feedback: the dimensions are the explanation.
    expect(firstEvaluation.technical_accuracy).toBeGreaterThanOrEqual(0);
    expect(firstEvaluation.depth).toBeGreaterThanOrEqual(0);
    expect(afterFirst.difficulty_change?.reason.trim().length).toBeGreaterThan(0);

    const secondQuestion = afterFirst.next_question;
    if (!secondQuestion) throw new Error('no next question after the first answer');
    expect(secondQuestion.turn_index, 'the session must advance past turn 0').toBeGreaterThan(
      firstQuestion.turn_index,
    );
    expect(secondQuestion.content.trim().length).toBeGreaterThan(0);

    // ── turn 2 (kept to three turns: the flow is what is under test, not the stamina) ─────────
    const afterSecond = await answer();
    expect(afterSecond.status).toBe('in_progress');
    expect(afterSecond.evaluation?.score).toBeGreaterThan(0);
    const thirdQuestion = afterSecond.next_question;
    if (!thirdQuestion) throw new Error('no question after the second answer');
    expect(thirdQuestion.turn_index).toBeGreaterThan(secondQuestion.turn_index);

    // ── the session state itself advanced, not just the response ─────────────────────────────
    const read = await apiFromPage<InterviewSession>(page, `/ai/interview/${started.session_id}`);
    expect(read.status).toBe(200);
    const persisted = read.data;
    expect(persisted.session_id).toBe(started.session_id);
    expect(persisted.status).toBe('in_progress');
    // Start (1 turn) + 2 × (candidate answer + interviewer question) = 5.
    expect(persisted.turns).toHaveLength(5);
    expect(persisted.turns.filter((turn) => turn.role === 'candidate')).toHaveLength(2);
    expect(persisted.turns.filter((turn) => turn.role === 'interviewer')).toHaveLength(3);
    const indices = persisted.turns.map((turn) => turn.turn_index);
    expect(indices).toEqual([0, 1, 2, 3, 4]);
    // The plan is the session's contract with the candidate and is built once, up front.
    expect(persisted.plan).toHaveLength(started.plan.length);
    expect(persisted.plan.every((topic) => topic.topic.length > 0)).toBe(true);
  });
});
