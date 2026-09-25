'use client';

import {
  Badge,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Separator,
} from '@careerforge/ui';
import { CircleDot } from 'lucide-react';

import {
  LEVEL_DESCRIPTION,
  LEVEL_LABEL,
  LEVEL_ORDER,
  levelLabel,
  levelNumber,
  sourceLabel,
  sourceTone,
  statusLabel,
} from '@/components/interview/interview-labels';
import type { RecordedTarget } from '@/hooks/use-interview-setup';
import type { InterviewSession } from '@/lib/interview-api';

/**
 * The session column: what this interview is, and what it is drawing on.
 *
 * Every line here is either a field of `GET /ai/interview/{id}` or a count derived from those
 * fields — no inference. Two of the derivations are worth naming, because the API's own fields do
 * not do the job:
 *
 * * *topics covered* is derived from the interviewer turns, not from `plan[].covered`: that flag
 *   exists on `InterviewPlanItem` but nothing ever writes it (`_plan_topics` leaves it `false` and
 *   `_adapt` computes coverage locally), so trusting it would show "0 covered" forever.
 * * *the evidence in play* is `plan[].source` plus `plan[].source_ids`. When every `source_ids` is
 *   empty, the column says exactly that instead of implying evidence it does not have.
 */

export interface SessionContextProps {
  session: InterviewSession;
  target: RecordedTarget | null;
}

function countBy(values: string[]): Array<[string, number]> {
  const counts = new Map<string, number>();
  for (const value of values) counts.set(value, (counts.get(value) ?? 0) + 1);
  return [...counts.entries()];
}

export function SessionContext({ session, target }: SessionContextProps) {
  const questions = session.turns.filter((turn) => turn.role === 'interviewer');
  const covered = [...new Set(questions.map((turn) => turn.topic).filter(Boolean))] as string[];
  const current = levelNumber(session.currentLevel);
  const referenced = session.plan.reduce((total, item) => total + item.sourceIds.length, 0);
  const sourceCounts = countBy(session.plan.map((item) => item.source));

  return (
    <aside className="flex min-w-0 flex-col gap-4" data-session-context="">
      <Card className="min-w-0">
        <CardHeader>
          <CardTitle>会话</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          <dl className="flex flex-col gap-1 font-mono text-[11px]">
            <div className="flex items-baseline justify-between gap-2">
              <dt className="text-tertiary">session</dt>
              <dd className="text-secondary truncate" title={session.sessionId}>
                {session.sessionId}
              </dd>
            </div>
            <div className="flex items-baseline justify-between gap-2">
              <dt className="text-tertiary">mode</dt>
              <dd className="text-secondary">{session.mode}</dd>
            </div>
            <div className="flex items-baseline justify-between gap-2">
              <dt className="text-tertiary">status</dt>
              <dd className="text-secondary">{statusLabel(session.status)}</dd>
            </div>
            <div className="flex items-baseline justify-between gap-2">
              <dt className="text-tertiary">provider</dt>
              <dd className="text-secondary">{session.meta.provider}</dd>
            </div>
            <div className="flex items-baseline justify-between gap-2">
              <dt className="text-tertiary">degraded</dt>
              <dd className="text-secondary">
                {String(session.meta.degraded)}
                {session.meta.degradedReason ? ` (${session.meta.degradedReason})` : ''}
              </dd>
            </div>
          </dl>
          {session.meta.degraded ? (
            <p className="text-weak text-[11px] leading-relaxed">
              本次会话以降级方式运行：评分为规则引擎的要点覆盖度，不含技术正确性判断。
            </p>
          ) : null}
          {session.meta.warnings.length > 0 ? (
            <ul className="text-tertiary flex flex-col gap-1 text-[11px] leading-relaxed">
              {session.meta.warnings.map((warning) => (
                <li key={warning}>· {warning}</li>
              ))}
            </ul>
          ) : null}
        </CardContent>
      </Card>

      <Card className="min-w-0">
        <CardHeader>
          <CardTitle>目标岗位</CardTitle>
          <CardDescription>
            会话载荷不含岗位标题，这一项来自本机记录的选择（同一次会话 id）。
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-2 text-xs">
          {target ? (
            <>
              <p className="text-primary">{target.role}</p>
              <p className="text-secondary">{target.company ?? '公司未在 JD 中识别'}</p>
              <p className="text-tertiary font-mono text-[11px]">
                job {target.jobId} · mode {target.mode}
              </p>
            </>
          ) : (
            <p className="text-secondary leading-relaxed">
              不可用 ——
              本机没有这条会话的岗位记录（例如会话由别的标签页或别的设备开始）。这里不显示猜测值。
            </p>
          )}
        </CardContent>
      </Card>

      <Card className="min-w-0">
        <CardHeader>
          <CardTitle>当前难度</CardTitle>
          <CardDescription>
            {levelLabel(session.currentLevel)} · 后端每答完一题上下调整一层
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          <ol className="flex flex-col gap-1.5">
            {LEVEL_ORDER.map((level, index) => {
              const active = current === index + 1;
              return (
                <li
                  key={level}
                  aria-current={active ? 'step' : undefined}
                  className="flex items-center gap-2 text-[11px]"
                >
                  {active ? (
                    <CircleDot className="text-signal size-3.5 shrink-0" aria-hidden="true" />
                  ) : (
                    <span
                      className="border-strong size-2 shrink-0 rounded-full border"
                      aria-hidden="true"
                    />
                  )}
                  <span className={active ? 'text-primary' : 'text-tertiary'}>
                    {LEVEL_LABEL[level]}
                  </span>
                  <span className="text-tertiary truncate">{LEVEL_DESCRIPTION[level]}</span>
                </li>
              );
            })}
          </ol>
        </CardContent>
      </Card>

      <Card className="min-w-0">
        <CardHeader>
          <CardTitle>已覆盖主题</CardTitle>
          <CardDescription>
            从面试官提问的 topic 去重得到（plan[].covered 后端从不写，不作为依据）
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          <p className="text-secondary font-mono text-[11px] tabular-nums">
            {covered.length} / {session.plan.length} 个计划主题 · 已问 {questions.length} 题
          </p>
          {covered.length > 0 ? (
            <ul className="flex flex-wrap gap-1.5">
              {countBy(questions.map((turn) => turn.topic ?? '未标注').filter(Boolean)).map(
                ([topic, count]) => (
                  <li key={topic}>
                    <Badge variant="outline">
                      {topic}
                      {count > 1 ? ` ×${count}` : ''}
                    </Badge>
                  </li>
                ),
              )}
            </ul>
          ) : (
            <p className="text-tertiary text-[11px]">尚无</p>
          )}
        </CardContent>
      </Card>

      <Card className="min-w-0">
        <CardHeader>
          <CardTitle>题目依据</CardTitle>
          <CardDescription>
            后端按岗位技能生成的主题计划（plan），不是客户端筛选的结果。
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <p className="text-secondary font-mono text-[11px] tabular-nums">
            {sourceCounts.map(([source, count]) => `${source}:${count}`).join(' · ') || '—'} ·
            证据引用 {referenced} 条
          </p>
          {referenced === 0 ? (
            <p className="text-tertiary text-[11px] leading-relaxed">
              所有 plan[].source_ids 均为空，且 source 不是
              evidence：本会话按岗位要求出题，没有引用证据条目。
              界面据实显示，不把它当成「有证据」。
            </p>
          ) : null}
          <Separator />
          {/*
            A posting with a dozen skills produces a dozen plan rows. Capped and scrollable: the
            panel is context, and an uncapped list made the whole workspace twice the height of the
            answer flow at both widths.
          */}
          <ul className="flex max-h-80 flex-col gap-3 overflow-y-auto pr-1">
            {session.plan.map((item) => (
              <li key={`${item.topic}-${item.label}`} className="flex flex-col gap-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={sourceTone(item.source)}>{sourceLabel(item.source)}</Badge>
                  <span className="text-primary text-xs">{item.label || item.topic}</span>
                  <span className="text-tertiary font-mono text-[11px]">{item.topic}</span>
                  {item.targetLevel ? (
                    <span className="text-tertiary font-mono text-[11px]">
                      目标 {levelLabel(item.targetLevel)}
                    </span>
                  ) : null}
                </div>
                {item.reason ? (
                  <p className="text-tertiary text-[11px] leading-relaxed">{item.reason}</p>
                ) : null}
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </aside>
  );
}
