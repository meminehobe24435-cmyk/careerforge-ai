import { cn } from '@/lib/utils';

import { ScreenshotPlaceholder } from './screenshot-placeholder';

interface Capability {
  number: string;
  title: string;
  value: string;
  /** Which surface the future screenshot comes from. */
  route: string;
  target: string;
  wireframe: 'dashboard' | 'graph' | 'diff' | 'none';
}

/** The six numbered blocks fixed by docs/UI.md §5.1 (01–06). */
const CAPABILITIES: Capability[] = [
  {
    number: '01',
    title: 'Evidence Graph',
    value: '断言 → 技能 → 项目 → 仓库文件 → 提交 的异构图谱，每个证据节点都带确定性置信度分数。',
    route: '/app/evidence-graph',
    target: 'docs/assets/screenshots/evidence-graph.png',
    wireframe: 'graph',
  },
  {
    number: '02',
    title: 'JD Intelligence',
    value: '把 JD 解析成 required / preferred / bonus 三层技能树，每项技能都保留 JD 原文出处。',
    route: '/app/jobs/new',
    target: 'docs/assets/screenshots/job-analysis.png',
    wireframe: 'dashboard',
  },
  {
    number: '03',
    title: 'AI Resume Copilot',
    value: '逐 bullet 改写 diff：每一句都过 claim validator，没有证据支撑的句子会被直接拒绝。',
    route: '/app/resume',
    target: 'docs/assets/screenshots/resume-copilot.png',
    wireframe: 'diff',
  },
  {
    number: '04',
    title: 'Interview Simulator',
    value: '六种面试模式，题目来自你的 JD、简历与证据图谱，难度从 L1 概念递进到 L3 调试。',
    route: '/app/interview',
    target: 'docs/assets/screenshots/interview.png',
    wireframe: 'dashboard',
  },
  {
    number: '05',
    title: 'Career Analytics',
    value: '投递漏斗、响应率、技能 ↔ 面试成功率关联，样本不足时显式标注而不是硬算。',
    route: '/app/analytics',
    target: 'docs/assets/screenshots/analytics.png',
    wireframe: 'dashboard',
  },
  {
    number: '06',
    title: 'Application Pipeline',
    value: '从 Wishlist 到 Offer 的看板流转，每一次状态变更都写入事件历史。',
    route: '/app/applications',
    target: 'docs/assets/screenshots/analytics.png',
    wireframe: 'dashboard',
  },
];

/**
 * Capability blocks 01–06, interleaved left/right at ≥1024px and stacked below.
 * Every block pairs a real card with a labelled screenshot placeholder.
 */
export function CapabilityGrid() {
  return (
    <section
      id="capabilities"
      className="border-subtle border-b"
      aria-labelledby="capabilities-heading"
    >
      <div className="mx-auto w-full max-w-6xl px-4 py-14 sm:px-6 sm:py-20">
        <h2
          id="capabilities-heading"
          className="text-primary max-w-2xl text-xl font-semibold tracking-tight sm:text-2xl"
        >
          六块能力，全部围绕「证据」构建
        </h2>
        <p className="text-secondary mt-3 max-w-2xl text-sm leading-relaxed">
          CareerForge 不是简历生成器。每一句话都要能追溯到真实来源，追溯不到就不写。
        </p>

        <ul className="mt-10 flex flex-col gap-10 sm:gap-14">
          {CAPABILITIES.map((capability, index) => (
            <li
              key={capability.number}
              className={cn(
                'flex flex-col gap-6 lg:items-center lg:gap-10',
                index % 2 === 1 ? 'lg:flex-row-reverse' : 'lg:flex-row',
              )}
            >
              <div className="flex min-w-0 flex-col gap-3 lg:w-[44%]">
                <span className="text-brand font-mono text-xs tabular-nums">
                  {capability.number}
                </span>
                <h3 className="text-primary text-lg font-semibold tracking-tight">
                  {capability.title}
                </h3>
                <p className="text-secondary text-sm leading-relaxed">{capability.value}</p>
                <span className="text-tertiary font-mono text-[11px]">{capability.route}</span>
              </div>
              <ScreenshotPlaceholder
                label={`${capability.title} 功能截图`}
                route={capability.route}
                target={capability.target}
                wireframe={capability.wireframe}
                className="min-w-0 lg:w-[56%]"
              />
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
