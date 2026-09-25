'use client';

import { Badge, Card, CardContent, CardHeader, CardTitle } from '@careerforge/ui';
import { ChevronDown, Equal, Scaling } from 'lucide-react';

import type { JobMatch } from '@/lib/jobs-api';
import {
  buildDimensionRows,
  dimensionWeightedSum,
  formatPoints,
  formatWeightPercent,
} from '@/components/jobs/job-match-view';

export interface MatchWhyControlProps {
  /** The score the breakdown explains, printed exactly as the API reported it. */
  score: number;
  open: boolean;
  onToggle: () => void;
  /** Id of the breakdown element, so the control can point at it with `aria-controls`. */
  panelId: string;
}

/**
 * `Why N%?` — the control.
 *
 * A `<button>` (keyboard reachable, `aria-expanded` + `aria-controls`) rather than a hover card,
 * because the number it explains is the page's headline claim.
 *
 * The control and the breakdown are two components on purpose: the control belongs beside the
 * score in the result header, and the breakdown is a six-column table that needs the full width
 * of the result column. Rendering the panel inside the header's fixed-width column was measured
 * at 1773 px of content in a 1440 px viewport — the panel pushed the page sideways instead of
 * scrolling inside itself.
 */
export function MatchWhyControl({ score, open, onToggle, panelId }: MatchWhyControlProps) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={open}
      // Only pointed at the breakdown while it exists: `aria-controls` naming an element that is
      // not in the DOM is a dangling reference, and the breakdown is rendered on demand.
      aria-controls={open ? panelId : undefined}
      className="border-default bg-elevated hover:border-strong focus-visible:outline-brand inline-flex items-center gap-2 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2"
    >
      <Scaling className="text-signal size-3.5" aria-hidden="true" />
      <span className="text-primary">
        Why <span className="font-mono tabular-nums">{`${formatPoints(score)}%`}</span>?
      </span>
      <ChevronDown
        aria-hidden="true"
        className={
          open ? 'size-3.5 rotate-180 transition-transform' : 'size-3.5 transition-transform'
        }
      />
    </button>
  );
}

export interface MatchWhyBreakdownProps {
  match: JobMatch;
  panelId: string;
}

/**
 * The breakdown behind the score, which has to add up.
 *
 * What it shows is what the API sent, in the API's own arithmetic: each dimension's `score`, its
 * `weight` and its `weighted` contribution, plus the engine's formula and notes. The last line
 * prints **the sum of those five contributions next to the reported score** — when they agree it
 * says so, and when they do not it prints both numbers and the difference. A breakdown that
 * quietly reconciled a mismatch would be the failure this panel exists to prevent.
 *
 * Below `lg` the six-column table becomes a card list: at 375 px a table of
 * Dimension/Weight/Score/Contribution/Formula/Evidence pushes the contribution — the number the
 * reader came for — off-screen.
 */
export function MatchWhyBreakdown({ match, panelId }: MatchWhyBreakdownProps) {
  const rows = buildDimensionRows(match);
  const sum = dimensionWeightedSum(rows);
  const agrees = Math.abs(sum - match.score) < 0.005;

  return (
    <Card id={panelId}>
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle>Score breakdown</CardTitle>
        <span className="text-tertiary font-mono text-[11px]">{match.why.algorithmVersion}</span>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {match.why.explanation ? (
          <p className="text-secondary text-xs leading-relaxed">{match.why.explanation}</p>
        ) : null}

        <p className="text-tertiary font-mono text-[11px] leading-relaxed">
          {match.why.formula || '—'}
        </p>

        <DimensionTable rows={rows} sum={sum} score={match.score} agrees={agrees} />
        <DimensionCards rows={rows} />

        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={agrees ? 'supported' : 'danger'}>
            <Equal className="size-3" aria-hidden="true" />
            {`Σ 加权 ${formatPoints(sum)} / 报告分数 ${formatPoints(match.score)}`}
            {agrees ? '' : `（差 ${formatPoints(Math.round((sum - match.score) * 100) / 100)}）`}
          </Badge>
          <span className="text-tertiary text-[11px]">
            引用证据 <span className="font-mono tabular-nums">{match.why.evidenceUsed.length}</span>{' '}
            条
            {match.why.computedAt ? (
              <>
                {' · 计算于 '}
                <span className="font-mono tabular-nums">{match.why.computedAt}</span>
              </>
            ) : null}
          </span>
        </div>

        {match.why.notes.length > 0 ? (
          <ul className="flex flex-col gap-1">
            {match.why.notes.map((note, index) => (
              <li key={`${index}-${note}`} className="text-tertiary text-[11px] leading-relaxed">
                · {note}
              </li>
            ))}
          </ul>
        ) : null}
      </CardContent>
    </Card>
  );
}

interface DimensionRenderProps {
  rows: ReturnType<typeof buildDimensionRows>;
}

function DimensionTable({
  rows,
  sum,
  score,
  agrees,
}: DimensionRenderProps & {
  sum: number;
  score: number;
  agrees: boolean;
}) {
  return (
    // `min-w-0` is load-bearing: this element is a flex item, and a flex item's automatic minimum
    // size is its min-content width — the six-column table's. Without it the card refuses to
    // shrink, `overflow-x-auto` never engages, and the page itself scrolls sideways.
    <div className="border-subtle hidden min-w-0 overflow-x-auto rounded-md border lg:block">
      <table className="w-full text-left text-[11px]">
        <caption className="sr-only">
          {`五个维度的权重、原始分、加权贡献、公式与证据数量（Evidence 列为该维度 evidenceIds 去重后的条数，接口返回的列表允许重复）；Σ 加权 = ${formatPoints(sum)}，报告分数 = ${formatPoints(score)}${agrees ? '，两者一致' : '，两者不一致'}`}
        </caption>
        <thead className="text-tertiary bg-base">
          <tr>
            <th scope="col" className="px-3 py-2 font-medium">
              Dimension
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              Weight
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              Score
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              Contribution
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              Formula
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              Evidence
              <span className="text-tertiary ml-1 font-normal">unique</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key} className="border-subtle border-t align-top">
              <th scope="row" className="text-secondary px-3 py-2 font-medium">
                {row.label}
                <span className="text-tertiary ml-1 font-mono">{row.key}</span>
              </th>
              <td className="text-secondary px-3 py-2 font-mono tabular-nums">
                {formatWeightPercent(row.weight)}
              </td>
              <td className="text-secondary px-3 py-2 font-mono tabular-nums">
                {formatPoints(row.score)}
              </td>
              <td className="text-primary px-3 py-2 font-mono tabular-nums">
                {formatPoints(row.weighted)}
              </td>
              <td className="text-tertiary max-w-md px-3 py-2 font-mono">
                {row.formula || '—'}
                {/* The engine's own notes: the inputs behind the number, e.g. "要求年限 3，
                    候选人 0". Shown with the formula rather than only in the narrow layout. */}
                {row.notes.map((note, index) => (
                  <span key={`${index}-${note}`} className="mt-1 block">
                    · {note}
                  </span>
                ))}
              </td>
              <td className="text-tertiary px-3 py-2 font-mono tabular-nums">
                {row.evidenceCount}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** The same six facts as the table, in a shape that fits 375 px (docs/UI.md §10). */
function DimensionCards({ rows }: DimensionRenderProps) {
  return (
    <ul data-dimension-cards className="flex flex-col gap-2 lg:hidden">
      {rows.map((row) => (
        <li
          key={row.key}
          className="border-subtle bg-base flex flex-col gap-1 rounded-md border p-3"
        >
          <div className="flex items-baseline justify-between gap-2">
            <span className="text-secondary text-xs font-medium">{row.label}</span>
            <span className="text-primary font-mono text-xs tabular-nums">
              {formatPoints(row.weighted)}
            </span>
          </div>
          <p className="text-tertiary font-mono text-[11px] tabular-nums">
            {`${row.key} · 权重 ${formatWeightPercent(row.weight)} · 得分 ${formatPoints(row.score)} · 证据 ${row.evidenceCount}`}
          </p>
          {row.formula ? (
            <p className="text-tertiary font-mono text-[11px] leading-relaxed">{row.formula}</p>
          ) : null}
          {row.notes.length > 0 ? (
            <ul className="flex flex-col gap-0.5">
              {row.notes.map((note, index) => (
                <li key={`${index}-${note}`} className="text-tertiary text-[11px] leading-relaxed">
                  · {note}
                </li>
              ))}
            </ul>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
