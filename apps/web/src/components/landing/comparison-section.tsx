import { Badge, Card, CardContent, CardHeader, CardTitle } from '@careerforge/ui';
import { Check, TriangleAlert, X } from 'lucide-react';

interface ComparisonRow {
  aspect: string;
  typical: string;
  forge: string;
}

/** Rows mirror the README comparison table (kept in sync manually until PHASE 14). */
const ROWS: ComparisonRow[] = [
  {
    aspect: '生成内容可溯源',
    typical: '没有任何来源，模型自由发挥',
    forge: 'claim → evidence provenance，每条断言都指向文件/提交/文档',
  },
  {
    aspect: '防伪造',
    typical: '「提升 50%」照样被写进简历',
    forge: 'claim validator + confidence gate，无证据的量化表述直接拒绝',
  },
  {
    aspect: '匹配分可解释',
    typical: '一个孤零零的百分比',
    forge: '5 维加权分数 + Why? 展开公式、权重与所用证据 id',
  },
  {
    aspect: '是否读真实代码',
    typical: '只能手动粘贴文本',
    forge: '文件级与 commit 级证据，精确到行号',
  },
  {
    aspect: '零 API Key 可用',
    typical: '没有 Key 就完全不可用',
    forge: '确定性 heuristic provider，全功能可运行',
  },
];

/**
 * "Why is this different" — the honest two-column comparison from docs/UI.md §5.1.
 * The failing example below is the documented example claim from docs/API.md §2.7, not a
 * fabricated screenshot; the screenshot slot is a labelled placeholder.
 */
export function ComparisonSection() {
  return (
    <section className="border-subtle border-b" aria-labelledby="comparison-heading">
      <div className="mx-auto w-full max-w-6xl px-4 py-14 sm:px-6 sm:py-20">
        <h2
          id="comparison-heading"
          className="text-primary text-xl font-semibold tracking-tight sm:text-2xl"
        >
          Typical AI resume tool vs CareerForge
        </h2>
        <p className="text-secondary mt-3 max-w-3xl text-sm leading-relaxed">
          大模型让「写得漂亮」变成免费。真正稀缺的是「能证明」。
        </p>

        <div className="border-default mt-8 overflow-hidden rounded-lg border">
          <table className="w-full border-collapse text-left text-sm">
            <caption className="sr-only">Typical AI resume tool 与 CareerForge 的能力对比</caption>
            <thead className="bg-surface">
              <tr className="border-default border-b">
                <th scope="col" className="text-tertiary px-4 py-3 text-xs font-medium">
                  对比项
                </th>
                <th scope="col" className="text-tertiary px-4 py-3 text-xs font-medium">
                  Typical AI resume tool
                </th>
                <th scope="col" className="text-brand px-4 py-3 text-xs font-medium">
                  CareerForge
                </th>
              </tr>
            </thead>
            <tbody>
              {ROWS.map((row) => (
                <tr key={row.aspect} className="border-subtle border-b last:border-b-0">
                  <th
                    scope="row"
                    className="text-primary w-1/4 px-4 py-3 align-top text-xs font-medium"
                  >
                    {row.aspect}
                  </th>
                  <td className="text-secondary px-4 py-3 align-top text-xs">
                    <span className="flex items-start gap-2">
                      <X className="text-danger mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
                      {row.typical}
                    </span>
                  </td>
                  <td className="text-secondary px-4 py-3 align-top text-xs">
                    <span className="flex items-start gap-2">
                      <Check
                        className="text-evidence mt-0.5 size-3.5 shrink-0"
                        aria-hidden="true"
                      />
                      {row.forge}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="mt-8 grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>同一句话，两种命运</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <p className="text-tertiary text-xs">原文（简历 bullet）</p>
              <p className="text-secondary font-mono text-sm">优化算法性能，提升 70%。</p>
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="danger" announce>
                  Rejected Claim
                </Badge>
                <Badge variant="outline">rule: numeric_without_evidence</Badge>
              </div>
              <p className="text-secondary flex items-start gap-2 text-xs leading-relaxed">
                <TriangleAlert
                  className="text-danger mt-0.5 size-3.5 shrink-0"
                  aria-hidden="true"
                />
                「70%」在证据图谱中没有任何实测数据支撑，因此这句话不会被写进简历 ——
                系统会给出安全改写建议，而不是替你编一个数字。
              </p>
              <p className="text-tertiary font-mono text-[11px]">
                例据来自 docs/API.md §2.7（/resume/versions）
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>证据先于措辞</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <p className="text-secondary text-xs leading-relaxed">
                每条断言在被写进简历之前，都会先检索证据图谱：来源权威性、时效性、具体程度、交叉印证、
                抽取质量五项加权得到
                confidence。低于阈值、或量化但无实测数据支撑的句子，在调用大模型之前
                就被确定性规则拦下。
              </p>
              <p className="text-tertiary font-mono text-[11px]">
                confidence = 0.30·authority + 0.15·recency + 0.20·specificity + 0.20·corroboration +
                0.15·extraction
              </p>
            </CardContent>
          </Card>
        </div>

        <p className="text-tertiary mt-6 font-mono text-[11px]">
          {/* TODO(phase-14): replace with docs/assets/screenshots/validator.png */}
          validator.png（Claim Validator 拒绝「提升 70%」）将在 PHASE 14 补上真实截图。
        </p>
      </div>
    </section>
  );
}
