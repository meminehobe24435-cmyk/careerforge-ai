'use client';

import { Badge, Card, CardContent, CardHeader, CardTitle } from '@careerforge/ui';
import type { SkillCorrelation } from '@careerforge/shared';

import { correlationVerdict, formatLift, formatRate } from '@/lib/analytics-format';

interface CorrelationTableProps {
  rows: SkillCorrelation[];
}

const VERDICT: Record<
  ReturnType<typeof correlationVerdict>,
  { label: string; variant: 'signal' | 'outline' | 'danger' }
> = {
  notable: { label: '值得注意', variant: 'signal' },
  flat: { label: '无显著差异', variant: 'outline' },
  insufficient: { label: '样本不足', variant: 'danger' },
};

/**
 * "Which skills did the interviews actually happen with?" (FR-14.3)
 *
 * The comparison group is always shown. A skill with a high interview rate that every posting
 * asked for tells you nothing — and the table would look identical either way if only the
 * "with" column were rendered, which is exactly the trap. `notable` is only true when both
 * groups clear the sample minimum and their 95% intervals do not overlap.
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

  return (
    <Card className="min-w-0">
      <CardHeader>
        <CardTitle>技能与面试成功率</CardTitle>
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
              {rows.map((row) => {
                const verdict = VERDICT[correlationVerdict(row)];
                return (
                  <tr key={row.skillId} className="border-subtle border-t align-top">
                    <td className="text-primary py-2 pr-3 font-medium">{row.displayName}</td>
                    <td className="text-secondary py-2 pr-3 font-mono tabular-nums">
                      {formatRate(row.withSkillRate, 0)} ({row.withSkillSuccesses}/
                      {row.withSkillTotal})
                    </td>
                    <td className="text-secondary py-2 pr-3 font-mono tabular-nums">
                      {formatRate(row.withoutSkillRate, 0)} ({row.withoutSkillSuccesses}/
                      {row.withoutSkillTotal})
                    </td>
                    <td className="text-secondary py-2 pr-3 font-mono tabular-nums">
                      {formatLift(row.lift)}
                    </td>
                    <td className="py-2">
                      <Badge variant={verdict.variant}>{verdict.label}</Badge>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
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
