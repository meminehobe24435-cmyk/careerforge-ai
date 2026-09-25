'use client';

import { Badge, Card, CardContent, CardHeader, CardTitle } from '@careerforge/ui';
import { ShieldAlert } from 'lucide-react';

import type { JobMatch } from '@/lib/jobs-api';
import {
  EVIDENCE_COVERAGE_DEFINITION,
  buildMatchFigures,
  formatRatioAsPercent,
  type MatchSource,
} from '@/components/jobs/job-match-view';

export interface MatchFiguresPanelProps {
  match: JobMatch;
  /** `computed` = this page ran the match; `stored` = read back from the database. */
  source: MatchSource;
  /** Warnings `POST /jobs/analyze` attached to its response (a re-read has none). */
  analyzeWarnings: string[];
}

/**
 * The two figures behind the score, each printed with the definition it came from.
 *
 * The definitions are not decoration: "Evidence Coverage 100%" is meaningless without knowing
 * that the API measures it over the requirements it classified as **met** (`match.py`,
 * `_evidence_dimension`), and "confidence" is the mean evidence confidence of the requirements
 * it listed as strengths — not a confidence about the score as a whole.
 *
 * The stored-match path is the reason this panel distinguishes `null` from `0`: `GET
 * /jobs/{id}/match` constructs its response without these fields, so what arrives is the
 * model's default. Printing "0%" for a coverage the live endpoint reports as 100% would be a
 * fabricated measurement, so the panel prints `—` and names the endpoint that does report it.
 */
export function MatchFiguresPanel({ match, source, analyzeWarnings }: MatchFiguresPanelProps) {
  const figures = buildMatchFigures(match, source);
  const warnings = [...analyzeWarnings, ...figures.warnings];

  return (
    <Card className="min-w-0">
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle>Match figures</CardTitle>
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge variant={source === 'computed' ? 'signal' : 'outline'}>
            {source === 'computed' ? 'POST /jobs/{id}/match' : 'GET /jobs/{id}/match'}
          </Badge>
          {figures.degraded === true ? <Badge variant="weak">degraded</Badge> : null}
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Figure
            label="Evidence Coverage"
            value={formatRatioAsPercent(figures.evidenceCoverage)}
            definition={EVIDENCE_COVERAGE_DEFINITION}
            missing={
              figures.evidenceCoverage === null
                ? 'GET /jobs/{id}/match 不返回该字段（服务端返回的是模型默认值，无法与真实的 0 区分），重新计算匹配即可看到。'
                : null
            }
          />
          <Figure
            label="Match confidence"
            value={formatRatioAsPercent(figures.confidence)}
            definition="已列入 strengths 的命中要求的平均证据置信度（match.py：compute_job_match 对 matched 列表取均值）；一条 strength 都没有时报告为 0，而不是「不可用」。"
            missing={
              figures.confidence === null
                ? 'GET /jobs/{id}/match 不返回该字段，重新计算匹配即可看到。'
                : null
            }
          />
        </dl>

        {figures.degraded === true ? (
          <p className="text-weak flex items-start gap-1.5 text-[11px] leading-relaxed">
            <ShieldAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
            <span>
              这次结果是降级的：条目由本地规则或降级 provider 产出，`degraded` 为 true。
              降级不影响算术本身，但会影响解析质量，详见下面的告警。
            </span>
          </p>
        ) : null}

        {warnings.length > 0 ? (
          <div className="flex flex-col gap-1">
            <p className="text-tertiary text-[11px] font-medium">Warnings</p>
            <ul className="flex flex-col gap-1">
              {warnings.map((warning, index) => (
                <li
                  key={`${index}-${warning}`}
                  className="text-secondary font-mono text-[11px] leading-relaxed"
                >
                  · {warning}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function Figure({
  label,
  value,
  definition,
  missing,
}: {
  label: string;
  value: string;
  definition: string;
  missing: string | null;
}) {
  return (
    <div className="border-subtle bg-base flex flex-col gap-1 rounded-md border p-3">
      <dt className="text-tertiary text-[11px]">{label}</dt>
      <dd className="text-primary font-mono text-xl tabular-nums">{value}</dd>
      <dd className="text-tertiary text-[11px] leading-relaxed">{definition}</dd>
      {missing ? <dd className="text-weak text-[11px] leading-relaxed">{missing}</dd> : null}
    </div>
  );
}
