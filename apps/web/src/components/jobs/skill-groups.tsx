'use client';

import { Badge, Card, CardContent, CardHeader, CardTitle } from '@careerforge/ui';
import { ChevronRight, ListTree } from 'lucide-react';
import { useId, useState } from 'react';

import type { JobMatch } from '@/lib/jobs-api';
import {
  ENGINE_EVIDENCE_SATURATION,
  VERDICT_LABELS,
  VERDICT_MEANINGS,
  VERDICT_TONES,
  evidenceGraphHref,
  formatEvidenceCount,
  type SkillGroups,
  type SkillRow,
  type SkillVerdict,
} from '@/components/jobs/job-match-view';

export interface SkillGroupsPanelProps {
  groups: SkillGroups;
  /** `null` while no match has been computed — rows then read "Awaiting match". */
  match: JobMatch | null;
}

/** The order the states are explained in, and the order the per-group counts are listed. */
const LEGEND_ORDER: SkillVerdict[] = [
  'matched',
  'partial',
  'missing',
  'unknown',
  'unreported',
  'unnormalised',
];

interface GroupSpec {
  key: 'required' | 'preferred' | 'bonus';
  title: string;
  /** The engine's own vocabulary for this level (`RequirementLevel`). */
  level: string;
  hint: string;
}

const GROUP_SPECS: GroupSpec[] = [
  {
    key: 'required',
    title: 'Required skills',
    level: 'required',
    hint: '任职要求 — 权重 1.0：缺失时证据强度维度会相应扣分。',
  },
  {
    key: 'preferred',
    title: 'Preferred skills',
    level: 'preferred',
    hint: '优先条件 — 权重 0.6。',
  },
  {
    key: 'bonus',
    title: 'Bonus skills',
    level: 'bonus',
    hint: '加分项 — 权重 0.3。',
  },
];

/**
 * The three-level skill tree (docs/UI.md §5.8), with the engine's verdict on every requirement.
 *
 * The states are the engine's, not ours (see `job-match-view.ts`): a row is **Matched** because
 * the requirement is in the match payload's `strengths`, **Missing** because it is in `gaps`,
 * **Unknown** because it is in `unknowns`. Two further states exist because pretending
 * otherwise would be worse than saying so: **Not in result** for a requirement the payload does
 * not mention at all, and **Not normalised** for one the taxonomy could not resolve (the engine
 * excludes those from scoring rather than counting them as misses).
 *
 * **Unknown is not Missing and is never merged with it.** "The engine has nothing either way,
 * so it asks" and "the engine has a reason to believe it is absent" are different facts, and a
 * page that renders them with the same badge teaches the reader the wrong thing.
 *
 * A skill with a canonical id links into the evidence graph (`?skill=<canonicalId>`), which is
 * where the reader can check what is actually behind the verdict.
 */
export function SkillGroupsPanel({ groups, match }: SkillGroupsPanelProps) {
  return (
    <Card className="min-w-0">
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle className="flex items-center gap-1.5">
          <ListTree className="size-3.5" aria-hidden="true" />
          JD Skill Tree
        </CardTitle>
        <span className="text-tertiary font-mono text-[11px] tabular-nums">
          {`${groups.total} 项要求 · GET /jobs/{id}/skill-tree`}
        </span>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <VerdictLegend counts={groups.counts} unreported={groups.unreported} />

        {groups.total === 0 ? (
          <p className="text-secondary text-xs leading-relaxed">
            这版解析没有产出任何技能要求。这通常意味着 JD 文本里没有可识别的技术名词，
            而不代表岗位没有要求——请检查文本是否完整，或改用更完整的岗位描述。
          </p>
        ) : null}

        {GROUP_SPECS.map((spec) => (
          <SkillGroup key={spec.key} spec={spec} rows={groups[spec.key]} match={match} />
        ))}
      </CardContent>
    </Card>
  );
}

function countByVerdict(rows: SkillRow[]): Partial<Record<SkillVerdict, number>> {
  const counts: Partial<Record<SkillVerdict, number>> = {};
  for (const row of rows) counts[row.verdict] = (counts[row.verdict] ?? 0) + 1;
  return counts;
}

function SkillGroup({
  spec,
  rows,
  match,
}: {
  spec: GroupSpec;
  rows: SkillRow[];
  match: JobMatch | null;
}) {
  const headingId = useId();
  const counts = countByVerdict(rows);

  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <h3 id={headingId} className="text-primary text-xs font-semibold">
          {spec.title}
        </h3>
        <span className="text-tertiary font-mono text-[11px]">{spec.level}</span>
        <span className="text-tertiary text-[11px]">{rows.length} 项</span>
        {LEGEND_ORDER.filter((verdict) => counts[verdict]).map((verdict) => (
          <Badge key={verdict} variant={VERDICT_TONES[verdict]}>
            {VERDICT_LABELS[verdict]} {counts[verdict]}
          </Badge>
        ))}
      </div>
      <p className="text-tertiary text-[11px] leading-relaxed">{spec.hint}</p>

      {rows.length === 0 ? (
        <p className="text-tertiary text-[11px]">
          该层级没有要求——这版解析没有把任何技能归到 {spec.level}。
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {rows.map((row) => (
            <SkillRowItem key={row.key} row={row} />
          ))}
        </ul>
      )}

      {match === null && rows.length > 0 ? (
        <p className="text-tertiary text-[11px]">尚未计算匹配，因此这些要求暂无判定。</p>
      ) : null}
    </section>
  );
}

function SkillRowItem({ row }: { row: SkillRow }) {
  const tone = VERDICT_TONES[row.verdict];
  return (
    <li
      data-skill={row.canonicalId ?? row.rawText}
      data-verdict={row.verdict}
      className="border-subtle bg-base flex flex-col gap-1.5 rounded-md border p-2.5 lg:flex-row lg:items-start lg:justify-between lg:gap-3"
    >
      <div className="flex min-w-0 flex-col gap-1">
        <div className="flex flex-wrap items-center gap-2">
          {row.canonicalId ? (
            <a
              href={evidenceGraphHref(row.canonicalId)}
              className="text-primary focus-visible:outline-brand rounded-sm text-xs font-medium underline decoration-dotted underline-offset-4 hover:decoration-solid focus-visible:outline-2 focus-visible:outline-offset-2"
              aria-label={`在证据图谱中查看 ${row.rawText} 的证据`}
            >
              {row.rawText}
            </a>
          ) : (
            <span className="text-primary text-xs font-medium">{row.rawText}</span>
          )}
          <span className="text-tertiary font-mono text-[11px]">
            {row.canonicalId ?? 'canonicalId: null'}
          </span>
          {row.jdEvidence ? (
            <span className="text-tertiary text-[11px] leading-relaxed">{row.jdEvidence}</span>
          ) : null}
        </div>
        {row.note && row.note !== row.jdEvidence ? (
          <p className="text-secondary text-[11px] leading-relaxed">{row.note}</p>
        ) : null}
        {row.askUser ? (
          <p className="text-signal text-[11px] leading-relaxed">{row.askUser}</p>
        ) : null}
      </div>

      {/* No `shrink-0` here: the badge group has to be allowed to shrink and wrap, or its
          min-content width (the widest badge plus the widest mono figure) pushes the row past
          the viewport — measured at 1024 px, where the row's `lg:` layout is already active. */}
      <div className="flex min-w-0 flex-wrap items-center gap-1.5 lg:justify-end">
        <Badge variant={tone}>{VERDICT_LABELS[row.verdict]}</Badge>
        {row.severity ? <Badge variant="outline">severity {row.severity}</Badge> : null}
        {row.userLevel ? <Badge variant="outline">level {row.userLevel}</Badge> : null}
        <span
          className="text-tertiary font-mono text-[11px] tabular-nums"
          title="该技能的证据条数（匹配结果里未报告时为 —）"
        >
          evidence {formatEvidenceCount(row.evidenceCount)}
        </span>
        {row.confidence !== null ? (
          <span className="text-tertiary font-mono text-[11px] tabular-nums">
            conf {row.confidence.toFixed(2)}
          </span>
        ) : null}
        <span className="text-tertiary font-mono text-[11px] tabular-nums">w {row.weight}</span>
      </div>
    </li>
  );
}

function VerdictLegend({
  counts,
  unreported,
}: {
  counts: Record<SkillVerdict, number>;
  unreported: number;
}) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  return (
    <div className="border-subtle bg-base flex flex-col gap-2 rounded-md border p-3">
      <div className="flex flex-wrap items-center gap-2">
        {LEGEND_ORDER.map((verdict) => (
          <Badge key={verdict} variant={VERDICT_TONES[verdict]}>
            {VERDICT_LABELS[verdict]} {counts[verdict] ?? 0}
          </Badge>
        ))}
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          // Only pointed at the panel while it is rendered (see the same note in `match-why.tsx`).
          aria-controls={open ? panelId : undefined}
          className="text-secondary hover:text-primary focus-visible:outline-brand ml-auto inline-flex items-center gap-1 rounded-sm text-[11px] focus-visible:outline-2 focus-visible:outline-offset-2"
        >
          <ChevronRight className={open ? 'size-3 rotate-90' : 'size-3'} aria-hidden="true" />
          这些标签是什么意思
        </button>
      </div>

      {unreported > 0 ? (
        <p className="text-tertiary text-[11px] leading-relaxed">
          <span className="text-secondary font-mono tabular-nums">{unreported}</span>{' '}
          项要求没有出现在匹配结果的任何列表里。 引擎只列出最多 6 条 strengths 与 8 条
          gaps，以及全部 unknowns； 被它算作“已具备”但没有进入 strengths
          的要求，在返回体里就没有对应字段。 这里如实标为{' '}
          <b className="font-medium">Not in result</b>，而不是猜成 Missing。
        </p>
      ) : null}

      {open ? (
        <dl id={panelId} className="flex flex-col gap-2">
          {LEGEND_ORDER.map((verdict) => (
            <div key={verdict} className="flex flex-col gap-0.5">
              <dt className="flex items-center gap-2">
                <Badge variant={VERDICT_TONES[verdict]}>{VERDICT_LABELS[verdict]}</Badge>
              </dt>
              <dd className="text-tertiary text-[11px] leading-relaxed">
                {VERDICT_MEANINGS[verdict]}
              </dd>
            </div>
          ))}
          <div className="flex flex-col gap-0.5">
            <dt className="text-secondary text-[11px] font-medium">判定来源</dt>
            <dd className="text-tertiary text-[11px] leading-relaxed">
              判定完全来自匹配接口的 strengths / gaps / unknowns 三个列表；
              页面不重新计算分数。Matched 与 Partial 的分界是引擎自己的证据饱和点
              （match.py：_EVIDENCE_SATURATION = {ENGINE_EVIDENCE_SATURATION}， 证据因子 0.60 + 0.40
              × min(1, 条数 / {ENGINE_EVIDENCE_SATURATION})）。
            </dd>
          </div>
        </dl>
      ) : null}
    </div>
  );
}
