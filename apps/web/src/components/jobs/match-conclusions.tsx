'use client';

import { Badge, Card, CardContent, CardHeader, CardTitle } from '@careerforge/ui';
import { ArrowRight, CircleHelp, TriangleAlert } from 'lucide-react';

import type { JobMatch } from '@/lib/jobs-api';
import { evidenceGraphHref } from '@/components/jobs/job-match-view';

export interface MatchConclusionsProps {
  match: JobMatch;
}

/** The engine's own caps (`match.py`): strengths are sliced to six, gaps to eight. */
export const STRENGTHS_CAP = 6;
export const GAPS_CAP = 8;

/** The page shows five of whatever the engine reported, and says how many it left out. */
const SHOWN = 5;

/**
 * Strengths / Gaps / Unknowns — three separate lists, never merged.
 *
 * Four decisions are load-bearing:
 *
 * 1. **Unknown is its own card, never folded into Gaps.** "Nothing points either way, so the
 *    engine asks" and "there is a reason to believe it is absent" are different facts; a page
 *    that renders them together teaches the reader the wrong one.
 * 2. **The engine's caps are printed when they bite.** A list that silently stops at six reads
 *    as "that is everything", and a truncated gap list is exactly what a reader would act on.
 * 3. **An empty strengths list explains itself.** With an imported résumé every declared skill
 *    is `moderate`, and the engine only advertises a requirement when its effective level
 *    clears 0.5 — so strengths can legitimately be empty while twelve requirements are met.
 *    Saying that is better than letting an empty card look broken.
 * 4. **Every skill links into the evidence graph**, which is where the verdict can be checked.
 */
export function MatchConclusions({ match }: MatchConclusionsProps) {
  const strengths = match.strengths.slice(0, SHOWN);
  const gaps = match.gaps.slice(0, SHOWN);

  return (
    <div className="flex flex-col gap-3" data-conclusions>
      <Card className="min-w-0">
        <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
          <CardTitle>Strengths</CardTitle>
          <span className="text-tertiary font-mono text-[11px] tabular-nums">
            {strengths.length}/{match.strengths.length} 条
            {match.strengths.length >= STRENGTHS_CAP ? ` · 引擎上限 ${STRENGTHS_CAP}` : ''}
          </span>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          {match.strengths.length === 0 ? (
            <p className="text-secondary text-xs leading-relaxed">
              匹配结果没有列出任何 strengths。引擎只列出达到其“可宣传”门槛的要求 （有效水平 ≥
              0.5＝已声明等级 × 证据因子），这不等于你没有满足任何要求： 声明为 moderate 且证据不足
              3 条时就会低于该门槛。逐项判定见上面的 JD Skill Tree， 其中的{' '}
              <b className="font-medium">Not in result</b> 正是这类情况。
            </p>
          ) : (
            <ul className="flex flex-col gap-2">
              {strengths.map((item) => (
                <li
                  key={`${item.canonicalId}-${item.requirement}`}
                  data-strength={item.canonicalId}
                  className="border-subtle bg-base flex flex-col gap-1 rounded-md border p-2.5"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <a
                      href={evidenceGraphHref(item.canonicalId)}
                      className="text-primary focus-visible:outline-brand rounded-sm text-xs font-medium underline decoration-dotted underline-offset-4 hover:decoration-solid focus-visible:outline-2 focus-visible:outline-offset-2"
                      aria-label={`在证据图谱中查看 ${item.displayName} 的证据`}
                    >
                      {item.displayName}
                    </a>
                    <span className="text-tertiary font-mono text-[11px]">{item.canonicalId}</span>
                    <Badge variant="outline">level {item.userLevel}</Badge>
                    <span className="text-tertiary font-mono text-[11px] tabular-nums">
                      evidence {item.evidenceCount} · conf {item.confidence.toFixed(2)}
                    </span>
                  </div>
                  <p className="text-secondary text-[11px] leading-relaxed">{item.reason}</p>
                </li>
              ))}
            </ul>
          )}
          {match.strengths.length > SHOWN ? (
            <p className="text-tertiary text-[11px]">
              只显示前 {SHOWN} 条，接口本次返回 {match.strengths.length} 条。
            </p>
          ) : null}
        </CardContent>
      </Card>

      <Card className="min-w-0">
        <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-1.5">
            <TriangleAlert className="text-danger size-3.5" aria-hidden="true" />
            Gaps
          </CardTitle>
          <span className="text-tertiary font-mono text-[11px] tabular-nums">
            {gaps.length}/{match.gaps.length} 条
            {match.gaps.length >= GAPS_CAP ? ` · 引擎上限 ${GAPS_CAP}` : ''}
          </span>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          {match.gaps.length === 0 ? (
            <p className="text-secondary text-xs leading-relaxed">
              没有缺口：引擎在这版匹配里没有找到“有理由认为缺失”的要求。
            </p>
          ) : (
            <ul className="flex flex-col gap-2">
              {gaps.map((gap) => (
                <li
                  key={`${gap.canonicalId}-${gap.requirement}`}
                  data-gap={gap.canonicalId}
                  className="border-subtle bg-base flex flex-col gap-1 rounded-md border p-2.5"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <a
                      href={evidenceGraphHref(gap.canonicalId)}
                      className="text-primary focus-visible:outline-brand rounded-sm text-xs font-medium underline decoration-dotted underline-offset-4 hover:decoration-solid focus-visible:outline-2 focus-visible:outline-offset-2"
                      aria-label={`在证据图谱中查看 ${gap.displayName} 的证据`}
                    >
                      {gap.displayName}
                    </a>
                    <span className="text-tertiary font-mono text-[11px]">{gap.canonicalId}</span>
                    <Badge variant="danger">severity {gap.severity}</Badge>
                    <span className="text-tertiary font-mono text-[11px]">{gap.requirement}</span>
                  </div>
                  {gap.jdEvidence ? (
                    <p className="text-tertiary text-[11px] leading-relaxed">{gap.jdEvidence}</p>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
          <p className="text-tertiary text-[11px] leading-relaxed">
            gap 是「有理由认为缺失」：未提供的证据、明确记录的 none
            等级，或同类技能已有证据而这一项没有。 它不是「简历没写」——那些在下一张卡里。
          </p>
        </CardContent>
      </Card>

      <Card className="min-w-0">
        <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-1.5">
            <CircleHelp className="text-signal size-3.5" aria-hidden="true" />
            Unknowns
          </CardTitle>
          <span className="text-tertiary font-mono text-[11px] tabular-nums">
            {match.unknowns.length} 条
          </span>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          {match.unknowns.length === 0 ? (
            <p className="text-secondary text-xs leading-relaxed">
              没有待确认项：引擎对每一条要求都给出了明确判断。
            </p>
          ) : (
            <ul className="flex flex-col gap-2">
              {match.unknowns.map((item) => (
                <li
                  key={`${item.canonicalId}-${item.requirement}`}
                  data-unknown={item.canonicalId}
                  className="border-signal/30 bg-base flex flex-col gap-1 rounded-md border p-2.5"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-primary text-xs font-medium">{item.displayName}</span>
                    <span className="text-tertiary font-mono text-[11px]">{item.canonicalId}</span>
                    <span className="text-tertiary font-mono text-[11px]">{item.requirement}</span>
                  </div>
                  <p className="text-secondary text-[11px] leading-relaxed">{item.reason}</p>
                  {item.askUser ? (
                    <p className="text-signal flex items-start gap-1.5 text-[11px] leading-relaxed">
                      <ArrowRight className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
                      {item.askUser}
                    </p>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
          <p className="text-tertiary text-[11px] leading-relaxed">
            待确认 ≠ 缺口：这些要求既没有支持证据，也没有反对证据，因此系统提问而不是替你判定。
            补充证据后重新匹配，它们会落到 Matched 或 Missing。
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
