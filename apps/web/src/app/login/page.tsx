import { Badge } from '@careerforge/ui';
import type { Metadata } from 'next';

import { EvidenceGraphThumb } from '@/components/login/evidence-graph-thumb';
import { LoginPanel } from '@/components/login/login-panel';
import { SiteHeader } from '@/components/landing/site-header';

export const metadata: Metadata = {
  title: '登录',
  description: '进入 CareerForge 工作台，或一键载入预置候选人数据的 Demo 账号。',
};

const HIGHLIGHTS = [
  'Candidate → Experience → Project → Skill → Evidence 完整链路',
  '每个分数都能展开 Why?，公式与所用证据 id 可查',
  'AI 降级、缓存命中、样本不足一律显式标注',
];

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ demo?: string | string[] }>;
}) {
  const params = await searchParams;
  const demoParam = params.demo;
  const demoIntent = Array.isArray(demoParam) ? demoParam.includes('1') : demoParam === '1';

  return (
    <>
      <SiteHeader />
      <main id="main" className="bg-grid">
        <div className="mx-auto grid w-full max-w-6xl grid-cols-1 gap-8 px-4 py-10 sm:px-6 lg:grid-cols-2 lg:gap-12 lg:py-16">
          <section aria-label="产品介绍" className="flex flex-col gap-5">
            <div className="flex flex-col gap-2">
              <p className="text-tertiary font-mono text-[11px] uppercase tracking-[0.18em]">
                CareerForge AI
              </p>
              {/* Deliberately not a heading: the page's only h1 is the login form title, so
                  the document outline stays h1 → h2 with no skipped level. */}
              <p className="text-primary text-xl font-semibold tracking-tight sm:text-2xl">
                你的简历，每一句都有出处。
              </p>
              <p className="text-secondary max-w-md text-sm leading-relaxed">
                Demo 账号预置了完整候选人（Alex Chen）：3 个项目、9 项技能、约 180 条证据记录、 12
                个已分析岗位、16 条投递、5 场面试。
              </p>
            </div>

            <ul className="flex flex-col gap-2">
              {HIGHLIGHTS.map((item) => (
                <li key={item} className="text-secondary flex items-start gap-2 text-xs">
                  <span
                    aria-hidden="true"
                    className="bg-brand mt-1.5 size-1 shrink-0 rounded-full"
                  />
                  {item}
                </li>
              ))}
            </ul>

            <div className="flex flex-wrap gap-2">
              <Badge variant="supported">Supported</Badge>
              <Badge variant="weak">Partially supported</Badge>
              <Badge variant="danger">Rejected claim</Badge>
            </div>

            <EvidenceGraphThumb />
          </section>

          <section aria-labelledby="login-form-heading" className="flex flex-col gap-4">
            <h2 id="login-form-heading" className="sr-only">
              登录表单
            </h2>
            {demoIntent ? (
              <p className="border-brand/30 bg-brand/10 text-brand rounded-md border px-3 py-2 font-mono text-[11px]">
                ?demo=1 — 已为你高亮一键 Demo 入口
              </p>
            ) : null}
            <LoginPanel demoIntent={demoIntent} />
          </section>
        </div>
      </main>
    </>
  );
}
