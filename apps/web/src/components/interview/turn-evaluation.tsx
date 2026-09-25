'use client';

import { Badge } from '@careerforge/ui';
import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react';

import { formatScore, levelLabel, levelNumber } from '@/components/interview/interview-labels';
import type { DifficultyChange, TurnEvaluation } from '@/lib/interview-api';

/**
 * The inline result of one answer, and the difficulty transition that followed it.
 *
 * Both are deliberately short. The API's evaluation carries five sub-scores, a feedback sentence,
 * a list of missing knowledge, strong points and follow-up topics; a wall of text between two
 * questions stops the interview from feeling like an interview. So the score line, the five
 * sub-scores in one mono row, one or two lines of feedback, and at most two missing items — the
 * rest stays available in the scorecard's per-question review.
 */

export interface TurnEvaluationPanelProps {
  evaluation: TurnEvaluation | null;
  change: DifficultyChange | null;
  /** From `GET /ai/interview/{id}` only the score survives a reload; the panel says so. */
  scoreOnly?: number | null;
  label?: string;
}

export function TurnEvaluationPanel({
  evaluation,
  change,
  scoreOnly,
  label = '本轮评价',
}: TurnEvaluationPanelProps) {
  if (!evaluation) {
    return (
      <div className="border-subtle bg-surface flex flex-col gap-1 rounded-lg border p-4">
        <p className="text-secondary text-xs">
          {label}
          {typeof scoreOnly === 'number' ? (
            <>
              ：得分 <span className="font-mono tabular-nums">{formatScore(scoreOnly)}</span>
            </>
          ) : (
            '：— 该轮没有评价记录'
          )}
        </p>
        <p className="text-tertiary text-[11px] leading-relaxed">
          会话载荷（GET /ai/interview/{'{id}'}）的每轮只带 score；完整评价来自当轮的 answer
          响应，刷新后不再保留。评分卡里的逐题复盘包含完整信息。
        </p>
      </div>
    );
  }

  const subScores: Array<[string, number]> = [
    ['技术', evaluation.technicalAccuracy],
    ['深度', evaluation.depth],
    ['表达', evaluation.communication],
    ['解题', evaluation.problemSolving],
    ['工程', evaluation.engineeringThinking],
    ['自信', evaluation.confidence],
  ];

  return (
    <div className="flex flex-col gap-3" data-evaluation="">
      <div className="border-subtle bg-surface flex flex-col gap-3 rounded-lg border p-4">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="text-secondary text-xs font-medium">{label}</span>
          <span className="text-primary font-mono text-lg tabular-nums">
            {formatScore(evaluation.score)}
          </span>
          <span className="text-tertiary text-[11px]">/ 100（后端按五项子分均值给出）</span>
        </div>

        <dl className="text-tertiary flex flex-wrap gap-x-3 gap-y-1 font-mono text-[11px]">
          {subScores.map(([name, value]) => (
            <div key={name} className="flex items-baseline gap-1">
              <dt>{name}</dt>
              <dd className="text-secondary tabular-nums">{formatScore(value * 100, 0)}</dd>
            </div>
          ))}
        </dl>

        {evaluation.feedback ? (
          <p className="text-secondary text-xs leading-relaxed">{evaluation.feedback}</p>
        ) : null}

        <div className="flex flex-col gap-1.5">
          {evaluation.missingKnowledge.length > 0 ? (
            <p className="text-secondary flex flex-wrap items-center gap-1.5 text-[11px]">
              <span className="text-tertiary">缺失要点</span>
              {evaluation.missingKnowledge.slice(0, 3).map((item) => (
                <Badge key={item} variant="weak">
                  {item}
                </Badge>
              ))}
              {evaluation.missingKnowledge.length > 3 ? (
                <span className="text-tertiary font-mono">
                  +{evaluation.missingKnowledge.length - 3}
                </span>
              ) : null}
            </p>
          ) : null}
          {evaluation.strongPoints.length > 0 ? (
            <p className="text-secondary flex flex-wrap items-center gap-1.5 text-[11px]">
              <span className="text-tertiary">已覆盖</span>
              {evaluation.strongPoints.slice(0, 2).map((item) => (
                <Badge key={item} variant="supported">
                  {item}
                </Badge>
              ))}
            </p>
          ) : null}
          {evaluation.followUpTopics.length > 0 ? (
            <p className="text-tertiary font-mono text-[11px]">
              follow_up: {evaluation.followUpTopics.slice(0, 3).join(' · ')}
            </p>
          ) : null}
        </div>
      </div>

      <DifficultyNotice change={change} />
    </div>
  );
}

/**
 * "Difficulty increased — reason: …", with the API's own reason text.
 *
 * `_adapt` reports a change on *every* turn, including the ones that stay on the same rung, and
 * says so in the reason ("保持当前难度"). Rendering that would make the notice meaningless — a
 * badge that is always there is not a signal — so the notice appears only when the level moved,
 * and an unchanged turn shows a one-line neutral confirmation instead.
 */
export function DifficultyNotice({ change }: { change: DifficultyChange | null }) {
  if (!change) return null;

  const from = levelNumber(change.fromLevel);
  const to = levelNumber(change.toLevel);
  const moved = change.fromLevel !== change.toLevel;

  if (!moved) {
    return (
      <p className="text-tertiary flex items-center gap-1.5 text-[11px]" data-difficulty-hold="">
        <Minus className="size-3" aria-hidden="true" />
        难度保持 {levelLabel(change.toLevel)} —— {change.reason}
      </p>
    );
  }

  const raised = (from ?? 0) < (to ?? 0);
  const Icon = raised ? ArrowUpRight : ArrowDownRight;

  return (
    <p
      role="status"
      data-difficulty-notice={raised ? 'up' : 'down'}
      className="border-l-signal bg-surface text-secondary flex flex-wrap items-center gap-x-2 gap-y-1 rounded-md border-l-2 px-3 py-2 text-[11px] leading-relaxed"
    >
      <Icon className="text-signal size-3.5 shrink-0" aria-hidden="true" />
      <span className="text-primary font-medium">{raised ? '难度提升' : '难度下降'}</span>
      <span className="font-mono tabular-nums">
        {levelLabel(change.fromLevel)} → {levelLabel(change.toLevel)}
      </span>
      <span className="text-tertiary">原因：{change.reason}</span>
    </p>
  );
}
