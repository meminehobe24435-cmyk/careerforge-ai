import { Badge, Card, CardContent, CardHeader, CardTitle, Tooltip } from '@careerforge/ui';

import { qualitySnapshot } from '@/lib/quality-snapshot';

/**
 * Evaluation snapshot (docs/QUALITY.md, `reports/README.md`).
 *
 * Three rules make this honest rather than decorative:
 *
 * 1. **The numbers are generated**, by `scripts/export_quality_snapshot.py`, from the committed
 *    reports — a hand-typed benchmark figure is a figure nobody can check, and this project has
 *    removed several of those already.
 * 2. **It is not a production SLA.** The panel says which commit it describes and which provider
 *    mode produced it. A visitor reading "Unsafe support rate 5.0%" must not think it was measured
 *    on their session.
 * 3. **The weak numbers are on screen.** `unsafe_support_rate` is the metric this project is least
 *    proud of and the one most worth showing: a quality surface that only displays the good rows is
 *    marketing, and an interviewer can tell the difference in about four seconds.
 */
export function QualitySnapshotPanel() {
  const snapshot = qualitySnapshot;

  return (
    <Card className="min-w-0" data-quality-snapshot>
      <CardHeader className="flex-col items-start gap-1.5 sm:flex-row sm:items-center sm:justify-between">
        <CardTitle className="flex items-center gap-2">
          评测快照
          <Badge variant="outline">Evaluation snapshot</Badge>
        </CardTitle>
        <p className="text-tertiary font-mono text-[11px]">
          commit {snapshot.commit}
          {snapshot.gitDirty ? ' (dirty)' : ''} · provider {snapshot.provider} · {snapshot.suites}{' '}
          suites / {snapshot.cases} cases
        </p>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {snapshot.metrics.map((metric) => (
            <div
              key={metric.metric}
              data-quality-metric={metric.metric}
              className="border-subtle bg-elevated flex flex-col gap-1 rounded-md border px-3 py-2.5"
            >
              <span className="text-tertiary text-[11px] leading-snug">{metric.label}</span>
              <span className="text-primary font-mono text-lg tabular-nums">
                {(metric.value * 100).toFixed(2)}%
              </span>
              <span className="text-tertiary font-mono text-[10px]">
                {metric.direction === 'lower' ? '越低越好' : '越高越好'}
              </span>
            </div>
          ))}
          <div
            data-quality-metric="coverage.core"
            className="border-subtle bg-elevated flex flex-col gap-1 rounded-md border px-3 py-2.5"
          >
            <span className="text-tertiary text-[11px] leading-snug">核心域行覆盖</span>
            <span className="text-primary font-mono text-lg tabular-nums">
              {snapshot.coverage.percent.toFixed(1)}%
            </span>
            <span className="text-tertiary font-mono text-[10px]">
              {snapshot.coverage.covered}/{snapshot.coverage.statements} statements
            </span>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-[11px]">
          <Tooltip
            content={
              <>
                置信度校准误差（Expected Calibration Error），{snapshot.calibration.cases}{' '}
                个断言用例。 越低表示「说 0.8 就真的有 80% 对」这件事越成立。
              </>
            }
          >
            <span className="text-secondary font-mono tabular-nums underline decoration-dotted underline-offset-4">
              ECE {snapshot.calibration.ece.toFixed(4)}
            </span>
          </Tooltip>
          <span className="text-tertiary font-mono tabular-nums">
            Brier {snapshot.calibration.brier.toFixed(4)}
          </span>
          <span className="text-tertiary">
            数据集：JD 抽取与检索为受控生成语料，Evidence 与面试为手写金标准
          </span>
        </div>

        <p className="text-secondary text-xs leading-relaxed">
          这些数字来自仓库内的评测报告（<span className="font-mono">reports/eval-report.json</span>
          、<span className="font-mono">confidence-calibration.json</span>、
          <span className="font-mono">coverage-summary.md</span>），由{' '}
          <span className="font-mono">python evals/run.py</span> 与{' '}
          <span className="font-mono">python scripts/coverage_report.py</span> 生成，标注了对应的
          commit。**它们描述的是被评测的那个提交在零 Key 确定性 provider
          下的行为，不是本页访问者的实时 SLA。** 其中最不体面的一项（unsafe support
          rate）刻意留在页面上：只展示好看的行，是营销而不是 评测。
        </p>
      </CardContent>
    </Card>
  );
}
