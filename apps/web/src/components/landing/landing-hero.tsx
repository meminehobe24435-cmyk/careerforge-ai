import { Button } from '@careerforge/ui';
import { ArrowRight, Github, Network } from 'lucide-react';
import Link from 'next/link';

import { ScreenshotPlaceholder } from './screenshot-placeholder';

const TRUST_BADGES = [
  'Claim → Evidence Traceability',
  'Explainable Match Score',
  'Hybrid RAG + pgvector',
  'Works without API keys',
];

/**
 * Landing hero — docs/UI.md §5.1.
 *
 * The H1 states the product's *thesis* rather than a benefit: every AI résumé tool promises better
 * wording, and this one is making a different claim — that the wording is checkable. At 375px the
 * H1 drops to 32px and the CTAs stack vertically.
 *
 * The second CTA says "Explore the Evidence Graph" and goes to the demo login, because the graph is
 * behind a session: linking straight at `/app/evidence-graph` would be a redirect that silently
 * loses the intent, and a link that lies about where it goes is worse than one extra click.
 */
export function LandingHero() {
  return (
    <section className="border-subtle bg-grid relative overflow-hidden border-b">
      <div
        aria-hidden="true"
        className="bg-hero-glow pointer-events-none absolute inset-x-0 top-0 h-[520px]"
      />
      <div className="relative mx-auto w-full max-w-6xl px-4 pb-14 pt-14 sm:px-6 sm:pt-20">
        <p className="text-tertiary font-mono text-[11px] uppercase tracking-[0.18em]">
          Evidence-driven AI career operating system
        </p>

        <h1 className="text-primary mt-5 max-w-3xl text-[32px] font-semibold leading-[1.12] tracking-tight sm:text-5xl lg:text-[56px]">
          Most resumes describe what you claim to know.
          <span className="text-secondary block">CareerForge shows the evidence.</span>
        </h1>

        <p className="text-secondary mt-5 max-w-2xl text-sm leading-relaxed sm:text-base">
          Your resume, projects and repositories become an evidence graph. Job matching, claim
          validation and interviews are built on it — and every sentence it helps you write stays
          traceable to something you actually did.
        </p>

        <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center">
          <Button asChild size="lg">
            <Link href="/login?demo=1">
              Try the demo
              <ArrowRight className="size-4" aria-hidden="true" />
            </Link>
          </Button>
          <Button asChild size="lg" variant="secondary">
            <Link href="/login?demo=1">
              <Network className="size-4" aria-hidden="true" />
              Explore the Evidence Graph
            </Link>
          </Button>
          {/* TODO(phase-14): replace `#` with the real public repository URL. */}
          <Button asChild size="lg" variant="outline">
            <a href="#" rel="noreferrer">
              <Github className="size-4" aria-hidden="true" />
              GitHub
            </a>
          </Button>
        </div>

        <p className="text-tertiary mt-6 font-mono text-[11px] tracking-wide">
          Evidence &gt; Hallucination · 零 Key 可运行 · 评测基线公开
        </p>

        <div className="mt-12">
          <ScreenshotPlaceholder
            label="Dashboard 全貌（1440 × 900，Demo 账号真实数据）"
            route="/app/dashboard"
            target="docs/assets/screenshots/dashboard.png"
            wireframe="dashboard"
          />
        </div>
      </div>

      <div className="border-subtle bg-base/60 relative border-t">
        <div className="mx-auto flex w-full max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-4 sm:px-6">
          {TRUST_BADGES.map((badge) => (
            <span key={badge} className="text-tertiary font-mono text-[11px] tracking-wide">
              {badge}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}
