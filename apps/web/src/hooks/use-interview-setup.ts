'use client';

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useState } from 'react';

import { interviewTargetApi } from '@/lib/interview-target-api';
import type { JobSummary } from '@/lib/interview-target-api';
import { queryKeys } from '@/lib/query-keys';

/**
 * The setup screen's reads, and the facts the page remembers between reloads.
 *
 * Split from `use-interview.ts` because it shares nothing with the session state machine: this
 * half only ever reads `/jobs`, `/jobs/{id}/skill-tree` and `/ai/capabilities`, and one of them
 * is a write (`POST /jobs/analyze`) that lands as a stored posting rather than as session state.
 */

const TARGETS_KEY = 'careerforge.interview.targets';
const DEMO_KEY = 'careerforge.interview.demo';

/* ── locally remembered facts about a session ──────────────────────────────── */

/**
 * `GET /ai/interview/{id}` does not carry the target job's title, so the page remembers what it
 * started the session with. It is a local record of a real selection, labelled as such on screen
 * — not a stand-in for a field the API is missing.
 */
export interface RecordedTarget {
  sessionId: string;
  jobId: string;
  role: string;
  company: string | null;
  mode: string;
}

function readJson<T>(key: string, fallback: T): T {
  if (typeof window === 'undefined') return fallback;
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function writeJson(key: string, value: unknown): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* a full or unavailable storage must not break the page */
  }
}

export function rememberTarget(entry: RecordedTarget): void {
  const all = readJson<Record<string, RecordedTarget>>(TARGETS_KEY, {});
  const next = { ...all, [entry.sessionId]: entry };
  const ids = Object.keys(next);
  for (const stale of ids.slice(0, Math.max(0, ids.length - 10))) delete next[stale];
  writeJson(TARGETS_KEY, next);
}

export function recallTarget(sessionId: string | null): RecordedTarget | null {
  if (!sessionId) return null;
  return readJson<Record<string, RecordedTarget>>(TARGETS_KEY, {})[sessionId] ?? null;
}

export function forgetTarget(sessionId: string): void {
  const all = readJson<Record<string, RecordedTarget>>(TARGETS_KEY, {});
  delete all[sessionId];
  writeJson(TARGETS_KEY, all);
}

/**
 * A demo session is still a real session, so the only thing recorded is *how* it was produced —
 * otherwise a reviewer reading the transcript after a reload would not know the answers were
 * scripted.
 */
export function markDemoSession(sessionId: string): void {
  const ids = readJson<string[]>(DEMO_KEY, []);
  if (!ids.includes(sessionId)) writeJson(DEMO_KEY, [...ids, sessionId].slice(-20));
}

export function isDemoSession(sessionId: string | null): boolean {
  if (!sessionId) return false;
  return readJson<string[]>(DEMO_KEY, []).includes(sessionId);
}

/* ── setup reads ───────────────────────────────────────────────────────────── */

export function useInterviewSetup() {
  const queryClient = useQueryClient();
  const [isAnalysing, setAnalysing] = useState(false);
  const [analyseError, setAnalyseError] = useState<unknown>(null);
  const [lastAnalysed, setLastAnalysed] = useState<JobSummary | null>(null);

  const jobs = useQuery({
    queryKey: queryKeys.interview.targetJobs(),
    queryFn: () => interviewTargetApi.targetJobs(),
    retry: 1,
    staleTime: 30_000,
  });

  const capabilities = useQuery({
    queryKey: queryKeys.interview.capabilities(),
    queryFn: () => interviewTargetApi.capabilities(),
    retry: 1,
    staleTime: 5 * 60_000,
  });

  /** `POST /jobs/analyze` — a pasted posting becomes a selectable target job. */
  const analyse = useCallback(
    async (text: string): Promise<JobSummary | null> => {
      setAnalysing(true);
      setAnalyseError(null);
      try {
        const job = await interviewTargetApi.analyseJob(text);
        setLastAnalysed(job);
        await queryClient.invalidateQueries({ queryKey: queryKeys.interview.targetJobs() });
        return job;
      } catch (error) {
        setAnalyseError(error);
        return null;
      } finally {
        setAnalysing(false);
      }
    },
    [queryClient],
  );

  return {
    jobs,
    capabilities,
    analyse,
    isAnalysing,
    analyseError,
    lastAnalysed,
    clearAnalyseError: () => setAnalyseError(null),
  };
}

/** `GET /jobs/{id}/skill-tree` — the requirements this session's questions are drawn from. */
export function useSkillTree(jobId: string | null) {
  return useQuery({
    queryKey: queryKeys.interview.skillTree(jobId ?? 'none'),
    queryFn: () => interviewTargetApi.skillTree(jobId as string),
    enabled: Boolean(jobId),
    retry: 1,
    staleTime: 60_000,
  });
}
