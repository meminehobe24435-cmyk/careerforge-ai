'use client';

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';

import { interviewApi } from '@/lib/interview-api';
import type {
  InterviewModeValue,
  InterviewSession,
  InterviewTurnResponse,
  SessionTurn,
} from '@/lib/interview-api';
import { interviewTargetApi } from '@/lib/interview-target-api';
import { queryKeys } from '@/lib/query-keys';

import { forgetTarget, markDemoSession, rememberTarget } from './use-interview-setup';

/**
 * `/app/interview` session state.
 *
 * Three things live here rather than in the components, because each of them is a promise the
 * page makes to the reader:
 *
 * 1. **The session id is in the URL.** `?session=<id>` is written with `history.replaceState`,
 *    so a refresh re-reads it and `GET /ai/interview/{id}` rehydrates the transcript. Reading
 *    `window.location` directly (instead of Next's `useSearchParams`) keeps the page free of a
 *    `Suspense` requirement and lets the tests exercise the URL behaviour in jsdom.
 * 2. **A failed turn keeps the session.** A failed `answer` POST parks the answer text in
 *    `pendingAnswer` instead of clearing the form, and `retryTurn` re-reads the session first —
 *    a timed-out POST may have been processed, and re-posting would put the same answer in the
 *    transcript twice.
 * 3. **The demo is the real state machine.** `runDemo` analyses a sample posting, starts a
 *    session and submits three scripted answers through the same endpoints the manual path uses.
 *    It is a fast path, not a mock.
 */

export const SESSION_PARAM = 'session';
/** Pause between demo turns, so a viewer can follow question → answer → adaptation. */
export const DEMO_STEP_PAUSE_MS = 1200;

/* ── URL ───────────────────────────────────────────────────────────────────── */

export function readSessionParam(): string | null {
  if (typeof window === 'undefined') return null;
  const value = new URLSearchParams(window.location.search).get(SESSION_PARAM);
  return value && value.trim() ? value.trim() : null;
}

export function writeSessionParam(sessionId: string | null): void {
  if (typeof window === 'undefined') return;
  const url = new URL(window.location.href);
  if (sessionId) url.searchParams.set(SESSION_PARAM, sessionId);
  else url.searchParams.delete(SESSION_PARAM);
  window.history.replaceState(window.history.state, '', `${url.pathname}${url.search}`);
}

/** The session id as the URL has it, kept in sync with back/forward navigation. */
export function useSessionParam(): [string | null, (id: string | null) => void] {
  const [sessionId, setId] = useState<string | null>(() => readSessionParam());

  useEffect(() => {
    const onPopState = () => setId(readSessionParam());
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  const setSessionId = useCallback((id: string | null) => {
    writeSessionParam(id);
    setId(id);
  }, []);

  return [sessionId, setSessionId];
}

/* ── turn merging ──────────────────────────────────────────────────────────── */

/**
 * Fold a turn response into the cached session.
 *
 * `POST .../answer` returns the evaluation, the difficulty change and the next question, not a
 * session, so the transcript is rebuilt here exactly as the server builds it: the candidate turn
 * follows the question and carries the evaluation, and the next question carries its own index.
 */
export function applyTurn(
  session: InterviewSession,
  answer: string,
  response: InterviewTurnResponse,
): InterviewSession {
  const turns: SessionTurn[] = [...session.turns];
  const lastIndex = turns.reduce((max, turn) => Math.max(max, turn.turnIndex), -1);
  const question = [...turns].reverse().find((turn) => turn.role === 'interviewer');
  turns.push({
    turnIndex: lastIndex + 1,
    role: 'candidate',
    content: answer,
    topic: question?.topic ?? null,
    level: null,
    score: response.evaluation?.score ?? null,
    evaluation: response.evaluation,
    difficultyChange: response.difficultyChange,
  });
  if (response.nextQuestion) {
    turns.push({
      turnIndex: response.nextQuestion.turnIndex,
      role: 'interviewer',
      content: response.nextQuestion.content,
      topic: response.nextQuestion.topic,
      level: response.nextQuestion.level,
      score: null,
    });
  }
  return {
    ...session,
    status: response.status,
    currentLevel: response.currentLevel,
    turns,
  };
}

/* ── the controller ────────────────────────────────────────────────────────── */

export type InterviewBusy = 'start' | 'answer' | 'finish' | 'demo' | null;

export interface StartInput {
  jobId: string;
  mode: InterviewModeValue;
  /** 1–3 — `StartInterviewRequest.difficulty`. */
  difficulty: number;
}

/** The demo runner's input: where the answers come from, and how many turns to run. */
export interface DemoRunScript {
  jobText: string;
  answerFor: (step: number, topic: string | null) => string;
  steps: number;
  /** Overridable so a test does not have to wait 1.2 seconds per turn to watch it work. */
  stepPauseMs?: number;
}

export function useInterviewController(
  sessionId: string | null,
  setSessionId: (id: string | null) => void,
) {
  const queryClient = useQueryClient();
  const cacheKey = queryKeys.interview.session(sessionId ?? 'none');

  const [busy, setBusy] = useState<InterviewBusy>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  /** The answer whose POST failed — kept so the retry button resubmits *that* text. */
  const [pendingAnswer, setPendingAnswer] = useState<string | null>(null);
  const [demoRunning, setDemoRunning] = useState(false);
  const cancelled = useRef(false);

  const query = useQuery({
    queryKey: cacheKey,
    queryFn: () => interviewApi.session(sessionId as string),
    enabled: Boolean(sessionId),
    retry: 1,
  });

  const setCache = useCallback(
    (session: InterviewSession) => {
      queryClient.setQueryData(queryKeys.interview.session(session.sessionId), session);
    },
    [queryClient],
  );

  const start = useCallback(
    async ({ jobId, mode, difficulty }: StartInput) => {
      setBusy('start');
      setActionError(null);
      try {
        // Read the *stored* analysis: the `POST /jobs/analyze` response injects a `warnings`
        // key that `JDAnalysis` (extra="forbid") would reject on the way back in.
        const detail = await interviewTargetApi.jobDetail(jobId);
        const session = await interviewApi.startSession({ mode, job: detail.analysis, difficulty });
        rememberTarget({
          sessionId: session.sessionId,
          jobId: detail.id,
          role: detail.role,
          company: detail.company,
          mode: session.mode,
        });
        setCache(session);
        setSessionId(session.sessionId);
        return session;
      } catch (error) {
        setActionError(error);
        return null;
      } finally {
        setBusy(null);
      }
    },
    [setCache, setSessionId],
  );

  const submitAnswer = useCallback(
    async (answer: string): Promise<boolean> => {
      if (!sessionId) return false;
      setBusy('answer');
      setActionError(null);
      try {
        const response = await interviewApi.answer(sessionId, answer);
        const current = queryClient.getQueryData<InterviewSession>(cacheKey);
        setCache(
          current ? applyTurn(current, answer, response) : await interviewApi.session(sessionId),
        );
        setPendingAnswer(null);
        return true;
      } catch (error) {
        // The session is *not* discarded: the transcript on screen is still the last good state.
        setPendingAnswer(answer);
        setActionError(error);
        return false;
      } finally {
        setBusy(null);
      }
    },
    [cacheKey, queryClient, sessionId, setCache],
  );

  /**
   * Retry the failed turn.
   *
   * Re-read first: a POST that timed out may have been processed, and re-posting would duplicate
   * the answer in the transcript (and in the scorecard's per-question list).
   */
  const retryTurn = useCallback(async () => {
    if (!sessionId || !pendingAnswer) return;
    setBusy('answer');
    try {
      const fresh = await interviewApi.session(sessionId);
      setCache(fresh);
      const landed = fresh.turns.some(
        (turn) => turn.role === 'candidate' && turn.content === pendingAnswer,
      );
      if (landed) {
        setPendingAnswer(null);
        setActionError(null);
        setBusy(null);
        return;
      }
    } catch {
      /* the re-read failed as well — fall through and try the POST */
    }
    setBusy(null);
    await submitAnswer(pendingAnswer);
  }, [pendingAnswer, sessionId, setCache, submitAnswer]);

  const finish = useCallback(async () => {
    if (!sessionId) return;
    setBusy('finish');
    setActionError(null);
    try {
      setCache(await interviewApi.finish(sessionId));
    } catch (error) {
      setActionError(error);
    } finally {
      setBusy(null);
    }
  }, [sessionId, setCache]);

  const abandon = useCallback(async () => {
    if (!sessionId) return;
    setBusy('finish');
    try {
      await interviewApi.abandon(sessionId);
    } catch (error) {
      setActionError(error);
    } finally {
      queryClient.removeQueries({ queryKey: queryKeys.interview.session(sessionId) });
      forgetTarget(sessionId);
      setPendingAnswer(null);
      setSessionId(null);
      setBusy(null);
    }
  }, [queryClient, sessionId, setSessionId]);

  /**
   * Demo session: the real endpoints, scripted answers.
   *
   * Each answer goes to `POST /ai/interview/{id}/answer`, so the evaluation, the difficulty
   * transition and the scorecard are produced by the backend — the script only supplies text.
   * The pause is there so the adaptation is visible while it happens.
   */
  const runDemo = useCallback(
    async (script: DemoRunScript) => {
      setBusy('demo');
      setDemoRunning(true);
      setActionError(null);
      cancelled.current = false;
      try {
        const created = await interviewTargetApi.analyseJob(script.jobText);
        const detail = await interviewTargetApi.jobDetail(created.id);
        const session = await interviewApi.startSession({
          mode: 'technical',
          job: detail.analysis,
          difficulty: 1,
        });
        rememberTarget({
          sessionId: session.sessionId,
          jobId: detail.id,
          role: detail.role,
          company: detail.company,
          mode: session.mode,
        });
        markDemoSession(session.sessionId);
        setCache(session);
        setSessionId(session.sessionId);

        let current = session;
        for (let step = 0; step < script.steps; step += 1) {
          if (cancelled.current) break;
          await new Promise((resolve) =>
            setTimeout(resolve, script.stepPauseMs ?? DEMO_STEP_PAUSE_MS),
          );
          if (cancelled.current) break;
          const question = [...current.turns].reverse().find((turn) => turn.role === 'interviewer');
          const answer = script.answerFor(step, question?.topic ?? null);
          const response = await interviewApi.answer(session.sessionId, answer);
          current = applyTurn(current, answer, response);
          setCache(current);
        }

        if (!cancelled.current) {
          setCache(await interviewApi.finish(session.sessionId));
        }
        return current;
      } catch (error) {
        // A demo that dies half-way leaves a real, resumable session behind.
        setActionError(error);
        return null;
      } finally {
        setDemoRunning(false);
        setBusy(null);
      }
    },
    [setCache, setSessionId],
  );

  return {
    session: query.data ?? null,
    isPending: query.isPending && Boolean(sessionId),
    isFetching: query.isFetching,
    loadError: query.error,
    refetch: () => void query.refetch(),

    busy,
    actionError,
    pendingAnswer,
    demoRunning,
    clearActionError: () => setActionError(null),
    cancelDemo: () => {
      cancelled.current = true;
    },

    start,
    submitAnswer,
    retryTurn,
    finish,
    abandon,
    runDemo,
  };
}

export type InterviewController = ReturnType<typeof useInterviewController>;
