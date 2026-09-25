import type { DifficultyValue, InterviewModeValue } from '@/lib/interview-api';

/**
 * The interview vocabulary, in one place.
 *
 * Every label here is a *translation of a backend value*, never a separate source of truth:
 * the mode list is `InterviewMode`, the levels are `DifficultyLevel`, the plan sources are the
 * strings `_plan_topics` writes, and the verdicts are `_scorecard`'s. An unknown value is shown
 * raw rather than mapped to the nearest label — a new backend value should be visible, not
 * silently rounded into an old one.
 */

export const MODE_LABELS: Record<InterviewModeValue, { label: string; note: string }> = {
  technical: { label: 'Technical', note: '按岗位技能提问：概念 → 工程 → 排障' },
  project: { label: 'Project deep dive', note: '围绕项目经历逐层深挖' },
  behavioral: { label: 'Behavioral', note: '经历、协作与动机类问题' },
  system_design: { label: 'System design', note: '分层设计题，一次只问一层' },
  hr: { label: 'HR', note: '独立题库，与技术题不同' },
};

export const LEVEL_LABEL: Record<DifficultyValue, string> = {
  concept: 'L1 概念',
  engineering: 'L2 工程',
  debugging: 'L3 Debug',
};

export const LEVEL_DESCRIPTION: Record<DifficultyValue, string> = {
  concept: '定义、原因、机制',
  engineering: '设计、取舍、失败模式',
  debugging: '从现象出发定位与测量',
};

export const LEVEL_ORDER: DifficultyValue[] = ['concept', 'engineering', 'debugging'];

export function levelNumber(level: string | null | undefined): number | null {
  if (!level) return null;
  const index = LEVEL_ORDER.indexOf(level as DifficultyValue);
  return index >= 0 ? index + 1 : null;
}

/** `—` for "the API did not report a level", the raw string for a level we do not know. */
export function levelLabel(level: string | null | undefined): string {
  if (!level) return '—';
  return LEVEL_LABEL[level as DifficultyValue] ?? level;
}

export const STATUS_LABEL: Record<string, string> = {
  planned: '已计划',
  in_progress: '进行中',
  completed: '已完成',
  abandoned: '已放弃',
};

export function statusLabel(status: string): string {
  return STATUS_LABEL[status] ?? status;
}

/** `InterviewPlanItem.source` — why a topic is in the plan. */
export const SOURCE_LABEL: Record<string, string> = {
  evidence: '有证据支撑',
  gap: '岗位必备但无证据',
  jd_requirement: '岗位要求',
  resume: '简历经历',
};

export function sourceLabel(source: string): string {
  return SOURCE_LABEL[source] ?? source;
}

export type BadgeTone = 'default' | 'supported' | 'weak' | 'danger' | 'signal' | 'outline';

export function sourceTone(source: string): BadgeTone {
  if (source === 'evidence') return 'supported';
  if (source === 'gap') return 'danger';
  if (source === 'jd_requirement') return 'signal';
  return 'default';
}

/** `null` is not `0`: an unscored turn prints a dash, never `0`. */
export function formatScore(score: number | null | undefined, digits = 1): string {
  return typeof score === 'number' && Number.isFinite(score) ? score.toFixed(digits) : '—';
}

export const VERDICT_LABEL: Record<string, string> = {
  strong: '强',
  mixed: '中',
  weak: '弱',
};

export function verdictTone(verdict: string): BadgeTone {
  if (verdict === 'strong') return 'supported';
  if (verdict === 'weak') return 'weak';
  return 'signal';
}

/**
 * A per-question verdict, with the one case where the API's own value misleads.
 *
 * `_scorecard` sets `verdict = "mixed"` for every question that has no evaluation, which
 * includes the question the session ended on — a question nobody answered. The row is labelled
 * `未作答` and the raw value stays visible in mono, so nothing is hidden either way.
 */
export function verdictFor(verdict: string, answer: string): { label: string; tone: BadgeTone } {
  if (!answer.trim()) return { label: '未作答', tone: 'outline' };
  return { label: VERDICT_LABEL[verdict] ?? verdict, tone: verdictTone(verdict) };
}

export const SEVERITY_LABEL: Record<string, string> = {
  low: '低',
  medium: '中',
  high: '高',
};

export function severityLabel(severity: string): string {
  return SEVERITY_LABEL[severity] ?? severity;
}

/** The seven dimension keys the scorecard is built from (`InterviewScorecard.DIMENSION_KEYS`). */
export const DIMENSION_KEYS = [
  'technical_accuracy',
  'communication',
  'depth',
  'problem_solving',
  'engineering_thinking',
  'confidence',
  'evidence_consistency',
] as const;

/** The marker the Skip button submits. There is no skip endpoint; see the workspace. */
export const SKIP_ANSWER = '（未作答，跳过本题）';
