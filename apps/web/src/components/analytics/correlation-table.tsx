'use client';

import { Badge, Card, CardContent, CardHeader, CardTitle } from '@careerforge/ui';
import type { SkillCorrelation } from '@careerforge/shared';

import { correlationReading, formatRate } from '@/lib/analytics-format';

interface CorrelationTableProps {
  rows: SkillCorrelation[];
}

/**
 * "Which skills did the interviews actually happen with?" (FR-14.3)
 *
 * The comparison group is always shown. A skill with a high interview rate that every posting
 * asked for tells you nothing — and the table would look identical either way if only the
 * "with" column were rendered, which is exactly the trap. `notable` is only true when both
 * groups clear the sample minimum and their 95% intervals do not overlap.
 *
 * **What changed, and why.** The verdict badge used to be the `danger` variant and the 差值 column
 * printed a signed number for every row, so a table of two-application samples read as a wall of
 * red `-100pt` declines — while the footnote underneath said the sample was insufficient. The
 * visual was making a claim the text denied, and it was the wrong claim: too little data is not a
 * decline, and a candidate should not be shown a downward trend they do not have. So the render is
 * derived from {@link correlationReading}:
 *
 * * the only `signal`-toned row is a difference that cleared the sample minimum;
 * * an insufficient row prints its (real, API-supplied) difference in muted text with **no sign
 *   emphasis**, labelled `Insufficient sample`, and says in words that it is not a conclusion;
 * * no row on this page is red. Danger is reserved for a *measured* decline, and this page cannot
 *   measure one from a sample below the minimum.
 */
export function CorrelationTable({ rows }: CorrelationTableProps) {
  if (rows.length === 0) {
    return (
      <Card className="min-w-0">
        <CardHeader>
          <CardTitle>技能与面试成功率</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-secondary text-xs leading-relaxed">
            还没有可以对比的数据。要得到相关性，需要同一批投递里既有「岗位要求这个技能」也有
            「不要求」的样本 —— 只有一边有数据时，任何比例都不构成对比。
          </p>
        </CardContent>
      </Card>
    );
  }

  const readings = rows.map((row) => ({ row, reading: correlationReading(row) }));
  const insufficient = readings.filter((entry) => !entry.reading.actionable);
  const notes = [...new Set(readings.map((entry) => entry.reading.note).filter(Boolean))];

  return (
    <Card className="min-w-0">
      <CardHeader className="flex-row items-center justify-between gap-2">
        <CardTitle>技能与面试成功率</CardTitle>
        {insufficient.length > 0 ? (
          <Badge variant="outline" data-testid="insufficient-rows">
            {insufficient.length} 行样本不足
          </Badge>
        ) : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <caption className="sr-only">技能与面试成功率的相关性，含两组样本量</caption>
            <thead className="text-tertiary">
              <tr>
                <th scope="col" className="py-1 pr-3 font-medium">
                  技能
                </th>
                <th scope="col" className="py-1 pr-3 font-medium">
                  要求它的岗位
                </th>
                <th scope="col" className="py-1 pr-3 font-medium">
                  未要求的岗位
                </th>
                <th scope="col" className="py-1 pr-3 font-medium">
                  差值
                </th>
                <th scope="col" className="py-1 font-medium">
                  结论
                </th>
              </tr>
            </thead>
            <tbody>
              {readings.map(({ row, reading }) => (
                <tr
                  key={row.skillId}
                  data-correlation={row.skillId}
                  data-actionable={reading.actionable ? 'true' : 'false'}
                  className="border-subtle border-t align-top"
                >
                  <td className="text-primary py-2 pr-3 font-medium">{row.displayName}</td>
                  <td className="text-secondary py-2 pr-3 font-mono tabular-nums">
                    {formatRate(row.withSkillRate, 0)} ({row.withSkillSuccesses}/
                    {row.withSkillTotal})
                  </td>
                  <td className="text-secondary py-2 pr-3 font-mono tabular-nums">
                    {formatRate(row.withoutSkillRate, 0)} ({row.withoutSkillSuccesses}/
                    {row.withoutSkillTotal})
                  </td>
                  {/*
                    An unmeasured difference is printed in tertiary text and without the sign
                    emphasis `formatLift` gives it elsewhere: the number is the API's, but it is
                    not a trend, and a bold `-100pt` is how a trend reads.
                  */}
                  <td
                    className={
                      reading.lift.measured
                        ? 'text-secondary py-2 pr-3 font-mono tabular-nums'
                        : 'text-tertiary py-2 pr-3 font-mono tabular-nums'
                    }
                    data-lift-measured={reading.lift.measured ? 'true' : 'false'}
                  >
                    {reading.lift.text}
                  </td>
                  <td className="py-2">
                    <Badge variant={reading.tone}>{reading.label}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {notes.map((note) => (
          <p key={note} className="text-secondary text-[11px] leading-relaxed" data-sample-note>
            {note}
          </p>
        ))}

        {rows[0]?.note ? (
          <p className="text-tertiary text-[11px] leading-relaxed">
            判定说明：{rows[0].note}。相关不等于因果 —— 技能与面试率同时变化，也可能是因为
            你投的是同一类岗位、或那段时间准备得更充分。
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
