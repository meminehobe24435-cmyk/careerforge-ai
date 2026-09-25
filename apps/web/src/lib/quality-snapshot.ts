/**
 * Evaluation snapshot — **generated, do not edit by hand**.
 *
 * Produced by `python scripts/export_quality_snapshot.py` from the committed reports, so every
 * number on the quality surface is traceable to an artefact in this repository. If a value is
 * missing from the report the generator fails instead of writing a default: a quality page that
 * shows a placeholder is worse than one that shows nothing.
 *
 * The commit is part of the data on purpose. These are *not* live production metrics, and the UI
 * must say so — they describe the evaluated commit, on the zero-key deterministic provider.
 */

export interface QualityMetric {
  label: string;
  value: number;
  /** `ratio` renders as a percentage; kept explicit so a future `count` cannot be mis-formatted. */
  kind: 'ratio';
  /** Which way is healthy. `unsafe_support_rate` is good when it is low. */
  direction: 'higher' | 'lower';
  suite: string;
  metric: string;
}

export interface QualitySnapshot {
  commit: string;
  generatedAt: string;
  provider: string;
  providerChain: readonly string[];
  gitDirty: boolean;
  cases: number;
  suites: number;
  metrics: QualityMetric[];
  calibration: { ece: number; brier: number; cases: number };
  coverage: { percent: number; covered: number; statements: number };
}

export const qualitySnapshot: QualitySnapshot = {
  commit: 'c147180',
  generatedAt: '2026-09-25T11:37:14.132563+00:00',
  provider: 'heuristic',
  providerChain: ['heuristic'],
  gitDirty: true,
  cases: 242,
  suites: 4,
  metrics: [
    {
      label: 'JD extraction · required-skill F1',
      value: 0.8832,
      kind: 'ratio',
      direction: 'higher',
      suite: 'jd_extraction',
      metric: 'jd.required_skill_f1',
    },
    {
      label: 'Evidence validation · macro F1',
      value: 0.8306,
      kind: 'ratio',
      direction: 'higher',
      suite: 'evidence_validation',
      metric: 'evidence.macro_f1',
    },
    {
      label: 'Unsafe support rate',
      value: 0.05,
      kind: 'ratio',
      direction: 'lower',
      suite: 'evidence_validation',
      metric: 'evidence.unsafe_support_rate',
    },
    {
      label: 'RAG retrieval · Hit@5',
      value: 0.9661,
      kind: 'ratio',
      direction: 'higher',
      suite: 'rag_retrieval',
      metric: 'retrieval.hit_at_5',
    },
    {
      label: 'RAG retrieval · MRR',
      value: 0.9011,
      kind: 'ratio',
      direction: 'higher',
      suite: 'rag_retrieval',
      metric: 'retrieval.mrr',
    },
    {
      label: 'Interview · required-skill coverage',
      value: 0.8333,
      kind: 'ratio',
      direction: 'higher',
      suite: 'interview_relevance',
      metric: 'interview.required_skill_coverage',
    },
  ],
  calibration: {
    ece: 0.0166,
    brier: 0.1034,
    cases: 60,
  },
  coverage: { percent: 91.9, covered: 1516, statements: 1649 },
};
