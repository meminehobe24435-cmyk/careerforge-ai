'use client';

import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Separator,
} from '@careerforge/ui';
import { Info, TriangleAlert } from 'lucide-react';

import {
  DIMENSION_KEYS,
  formatScore,
  levelLabel,
  severityLabel,
  verdictFor,
} from '@/components/interview/interview-labels';
import { API_BASE_URL } from '@/lib/api';
import type { InterviewScorecard } from '@/lib/interview-api';

/**
 * The scorecard: the analysis, not a verdict on the person.
 *
 * Three rules are enforced here and they all come from the same principle — a number on screen has
 * to be checkable:
 *
 * * the seven dimensions are rendered **from `dimensions[]`**, in the order the API sends them. A
 *   key the payload does not contain is not invented, and a payload that is short is reported as
 *   short rather than padded with zeros;
 * * `duration_seconds` is hard-coded to `0` by `_scorecard`, so it is shown as 不可用 with the
 *   reason, not as "0s";
 * * a question with no answer gets 未作答 while the API's raw `verdict` stays visible in mono —
 *   `_scorecard` marks the unanswered final question `mixed`, and quietly repeating that would
 *   read as "this answer was mediocre" when there was no answer at all.
 */

export interface InterviewScorecardViewProps {
  scorecard: InterviewScorecard;
  sessionId: string;
  isDemo: boolean;
  onNewSession: () => void;
}

export function InterviewScorecardView({
  scorecard,
  sessionId,
  isDemo,
  onNewSession,
}: InterviewScorecardViewProps) {
  const missingKeys = DIMENSION_KEYS.filter(
    (key) => !scorecard.dimensions.some((dimension) => dimension.key === key),
  );
  const answered = scorecard.perQuestion.filter((review) => review.answer.trim());
  const unanswered = scorecard.perQuestion.length - answered.length;

  return (
    <div className="flex flex-col gap-4" data-scorecard="">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <h1 className="text-primary flex flex-wrap items-center gap-2 text-lg font-semibold tracking-tight">
            评分卡
            <Badge variant="outline">mode={scorecard.mode}</Badge>
            <Badge variant="outline">{scorecard.algorithmVersion}</Badge>
            {isDemo ? <Badge variant="weak">Demo session</Badge> : null}
          </h1>
          <p className="text-tertiary truncate font-mono text-[11px]" title={sessionId}>
            GET {API_BASE_URL}/ai/interview/{sessionId} · scorecard
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={onNewSession}>
          开始新的会话
        </Button>
      </header>

      <Card className="min-w-0">
        <CardHeader>
          <CardTitle>总分</CardTitle>
          <CardDescription>
            七维均值的算术平均，由后端计算。这是分析工具的输出，不是录用结论。
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="text-primary font-mono text-3xl tabular-nums">
              {formatScore(scorecard.overallScore)}
            </span>
            <span className="text-tertiary text-xs">
              / 100 · {scorecard.dimensions.length} 个维度 · 已回答 {answered.length} 题
              {unanswered > 0 ? ` · 未作答 ${unanswered} 题` : ''}
            </span>
          </div>
          <dl className="text-tertiary flex flex-wrap gap-x-4 gap-y-1 font-mono text-[11px]">
            <div className="flex items-baseline gap-1">
              <dt>起始难度</dt>
              <dd className="text-secondary">{levelLabel(scorecard.difficultyStart)}</dd>
            </div>
            <div className="flex items-baseline gap-1">
              <dt>结束难度</dt>
              <dd className="text-secondary">{levelLabel(scorecard.difficultyEnd)}</dd>
            </div>
            <div className="flex items-baseline gap-1">
              <dt>用时</dt>
              <dd className="text-secondary">
                {scorecard.durationSeconds ? `${scorecard.durationSeconds}s` : '不可用'}
              </dd>
            </div>
          </dl>
          {!scorecard.durationSeconds ? (
            <p className="text-tertiary text-[11px] leading-relaxed">
              用时不可用：后端 <span className="font-mono">_scorecard</span> 固定写入{' '}
              <span className="font-mono">duration_seconds = 0</span>，这不是「耗时 0 秒」的测量值。
            </p>
          ) : null}
        </CardContent>
      </Card>

      {missingKeys.length > 0 ? (
        <p className="border-weak/40 bg-weak/10 text-secondary flex items-start gap-2 rounded-md border px-3 py-2 text-[11px] leading-relaxed">
          <TriangleAlert className="text-weak mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          <span>
            后端返回了 {scorecard.dimensions.length} 个维度，缺少{' '}
            <span className="font-mono">{missingKeys.join(' / ')}</span>
            。缺少的维度按「不可用」处理， 不补 0。
          </span>
        </p>
      ) : null}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Card className="min-w-0">
          <CardHeader>
            <CardTitle>七个维度</CardTitle>
            <CardDescription>
              每项是各轮评价的均值；evidence_consistency 由冲突检测给出。
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            <ul className="flex flex-col gap-2">
              {scorecard.dimensions.map((dimension) => (
                <li key={dimension.key} className="flex flex-col gap-1">
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="text-primary text-xs">
                      {dimension.label || dimension.key}
                      <span className="text-tertiary ml-2 font-mono text-[11px]">
                        {dimension.key}
                      </span>
                    </span>
                    <span className="text-primary font-mono text-sm tabular-nums">
                      {formatScore(dimension.score)}
                    </span>
                  </div>
                  <div className="bg-elevated h-1.5 w-full overflow-hidden rounded-full">
                    <div
                      className="bg-signal h-full rounded-full"
                      style={{ width: `${Math.max(0, Math.min(100, dimension.score))}%` }}
                      aria-hidden="true"
                    />
                  </div>
                  {dimension.comment ? (
                    <p className="text-tertiary text-[11px]">{dimension.comment}</p>
                  ) : null}
                </li>
              ))}
            </ul>
            {scorecard.dimensions.length === 0 ? (
              <p className="text-tertiary text-[11px]">
                后端未返回任何维度 —— 本次会话没有可评分的回答。
              </p>
            ) : null}
          </CardContent>
        </Card>

        <div className="flex min-w-0 flex-col gap-4">
          <Card className="min-w-0">
            <CardHeader>
              <CardTitle>强项与不足</CardTitle>
              <CardDescription>
                来自各轮评价的 strong_points 与低于阈值轮次的反馈原文。
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-3 text-xs">
              <ListBlock
                title="强项"
                items={scorecard.strengths}
                empty="尚无 —— 各轮评价没有给出 strong_points"
              />
              <Separator />
              <ListBlock
                title="不足"
                items={scorecard.weaknesses}
                empty="尚无 —— 没有低于 45 分的轮次"
              />
              <Separator />
              <ListBlock
                title="缺失知识点"
                items={scorecard.missingKnowledge}
                empty="尚无 —— 各轮评价未报告缺失要点"
              />
              <Separator />
              <ListBlock
                title="建议追问方向"
                items={scorecard.followUpTopics}
                empty="尚无 —— 各轮评价没有给出追问方向"
              />
            </CardContent>
          </Card>

          <Card className="min-w-0">
            <CardHeader>
              <CardTitle>证据一致性</CardTitle>
              <CardDescription>
                口述内容与证据图谱的交叉核对（确定性规则，不由模型判断）。
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              {scorecard.evidenceConflicts.length === 0 ? (
                <p className="text-secondary text-xs">
                  无冲突记录。这一次会话没有出现「提到但无证据支撑」的技术项。
                </p>
              ) : (
                <ul className="flex flex-col gap-3">
                  {scorecard.evidenceConflicts.map((conflict, index) => (
                    <li
                      key={`${index}-${conflict.statement.slice(0, 24)}`}
                      className="flex flex-col gap-1"
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant={conflict.severity === 'high' ? 'danger' : 'weak'}>
                          severity={conflict.severity}（{severityLabel(conflict.severity)}）
                        </Badge>
                      </div>
                      <p className="text-secondary text-xs leading-relaxed">
                        「{conflict.statement}」
                      </p>
                      <p className="text-tertiary text-[11px] leading-relaxed">
                        {conflict.evidenceState}
                      </p>
                      {conflict.advice ? (
                        <p className="text-tertiary text-[11px] leading-relaxed">
                          建议：{conflict.advice}
                        </p>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      <Card className="min-w-0">
        <CardHeader>
          <CardTitle>逐题复盘</CardTitle>
          <CardDescription>
            每题的问题、回答、判定与建议答案。后端对最后一题（没有人回答）依然返回 verdict=mixed，
            这里按「未作答」显示，同时保留原始值。
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          {scorecard.perQuestion.length === 0 ? (
            <p className="text-tertiary text-xs">尚无逐题记录。</p>
          ) : (
            scorecard.perQuestion.map((review, index) => {
              const verdict = verdictFor(review.verdict, review.answer);
              return (
                <details
                  key={review.turnIndex}
                  className="border-subtle bg-base rounded-md border"
                  open={index === 0}
                >
                  <summary className="flex cursor-pointer flex-wrap items-center gap-2 px-3 py-2 text-xs">
                    <span className="text-tertiary font-mono">#{index + 1}</span>
                    <Badge variant={verdict.tone}>{verdict.label}</Badge>
                    {review.topic ? <Badge variant="outline">{review.topic}</Badge> : null}
                    {review.level ? (
                      <span className="text-tertiary font-mono text-[11px]">
                        {levelLabel(review.level)}
                      </span>
                    ) : null}
                    <span className="text-tertiary truncate font-mono text-[11px]">
                      turn_index={review.turnIndex}
                    </span>
                    <span className="text-secondary min-w-0 flex-1 truncate">
                      {review.question || '（无题面）'}
                    </span>
                  </summary>
                  <div className="flex flex-col gap-2 px-3 pb-3 text-xs">
                    {/* The raw verdict and index live here as well as in the summary: at 375 px the
                        summary row has no room for them, and the raw value is not optional. */}
                    <p className="text-tertiary font-mono text-[11px]">
                      turn_index={review.turnIndex} · verdict={review.verdict} · 后端判定
                    </p>
                    <div className="flex flex-col gap-1">
                      <p className="text-tertiary text-[11px]">题面</p>
                      <p className="text-primary leading-relaxed">{review.question || '—'}</p>
                    </div>
                    <div className="flex flex-col gap-1">
                      <p className="text-tertiary text-[11px]">你的回答</p>
                      <p className="text-secondary leading-relaxed">
                        {review.answer || '本次会话没有这道题的回答记录'}
                      </p>
                    </div>
                    {review.suggestedAnswer ? (
                      <div className="flex flex-col gap-1">
                        <p className="text-tertiary text-[11px]">建议答案（后端给出）</p>
                        <p className="text-secondary leading-relaxed">{review.suggestedAnswer}</p>
                      </div>
                    ) : (
                      <p className="text-tertiary text-[11px]">
                        建议答案：后端本次未提供（suggested_answer 为空）
                      </p>
                    )}
                    {review.missingKnowledge.length > 0 ? (
                      <p className="text-tertiary flex flex-wrap items-center gap-1.5 text-[11px]">
                        缺失
                        {review.missingKnowledge.slice(0, 5).map((item) => (
                          <Badge key={item} variant="weak">
                            {item}
                          </Badge>
                        ))}
                      </p>
                    ) : null}
                    {review.followUpTopics.length > 0 ? (
                      <p className="text-tertiary font-mono text-[11px]">
                        follow_up: {review.followUpTopics.join(' · ')}
                      </p>
                    ) : null}
                  </div>
                </details>
              );
            })
          )}
        </CardContent>
      </Card>

      <p className="text-tertiary flex items-start gap-2 px-1 text-[11px] leading-relaxed">
        <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
        <span>
          本页所有数字都可以在 API 响应里对照：维度来自{' '}
          <span className="font-mono">scorecard.dimensions[]</span>，逐题来自{' '}
          <span className="font-mono">scorecard.per_question[]</span>
          。没有可用的指标一律显示「不可用」，不显示 0。
        </span>
      </p>
    </div>
  );
}

function ListBlock({ title, items, empty }: { title: string; items: string[]; empty: string }) {
  return (
    <div className="flex flex-col gap-1">
      <p className="text-secondary text-[11px] font-medium">{title}</p>
      {items.length === 0 ? (
        <p className="text-tertiary text-[11px] leading-relaxed">{empty}</p>
      ) : (
        <ul className="flex flex-col gap-1">
          {items.map((item, index) => (
            <li
              key={`${index}-${item.slice(0, 20)}`}
              className="text-secondary flex gap-2 leading-relaxed"
            >
              <span className="text-tertiary font-mono text-[11px]">·</span>
              <span>{item}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
