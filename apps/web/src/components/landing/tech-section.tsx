import { ArrowRight } from 'lucide-react';

const STACK_BADGES = [
  'Next.js 15',
  'React 19',
  'TypeScript strict',
  'Tailwind v4',
  'FastAPI',
  'PostgreSQL + pgvector',
  'Redis',
  'Docker',
  'Python 3.12',
];

const EVIDENCE_CHAIN = ['Candidate', 'Experience', 'Project', 'Skill', 'Evidence'];

/** Technical section (docs/UI.md §5.1): architecture sketch + stack badges. */
export function TechSection() {
  return (
    <section className="border-subtle border-b" aria-labelledby="tech-heading">
      <div className="mx-auto w-full max-w-6xl px-4 py-14 sm:px-6 sm:py-20">
        <h2
          id="tech-heading"
          className="text-primary text-xl font-semibold tracking-tight sm:text-2xl"
        >
          架构
        </h2>

        <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-[1.1fr_0.9fr]">
          <div className="border-default bg-surface overflow-hidden rounded-lg border">
            {[
              {
                layer: 'Frontend',
                detail: 'Next.js 15 · App Router · TypeScript strict · Tailwind v4',
              },
              { layer: 'API', detail: 'FastAPI · Pydantic v2 · SQLAlchemy 2.0 async · Alembic' },
              {
                layer: 'AI Core',
                detail: 'Agent Orchestrator · 9 Agents · Hybrid RAG · Evidence Graph Engine',
              },
              { layer: 'Ports', detail: 'LLMProvider · VectorStore · Queue · GitHub · Storage' },
              {
                layer: 'Infrastructure',
                detail: 'PostgreSQL + pgvector · Redis · Worker · Object storage',
              },
            ].map((row) => (
              <div
                key={row.layer}
                className="border-subtle flex flex-col gap-1 border-b px-4 py-3 last:border-b-0 sm:flex-row sm:items-baseline sm:gap-4"
              >
                <span className="text-brand w-32 shrink-0 font-mono text-[11px] uppercase tracking-wide">
                  {row.layer}
                </span>
                <span className="text-secondary text-xs leading-relaxed">{row.detail}</span>
              </div>
            ))}
          </div>

          <div className="flex flex-col gap-6">
            <div className="border-default bg-surface rounded-lg border p-4">
              <p className="text-tertiary font-mono text-[11px] uppercase tracking-wide">
                Evidence chain
              </p>
              <ol className="mt-3 flex flex-wrap items-center gap-2">
                {EVIDENCE_CHAIN.map((step, index) => (
                  <li key={step} className="flex items-center gap-2">
                    <span className="border-default bg-elevated text-secondary rounded-sm border px-2 py-1 font-mono text-[11px]">
                      {step}
                    </span>
                    {index < EVIDENCE_CHAIN.length - 1 ? (
                      <ArrowRight className="text-tertiary size-3" aria-hidden="true" />
                    ) : null}
                  </li>
                ))}
              </ol>
              <p className="text-secondary mt-3 text-xs leading-relaxed">
                说法 → 证据 → 分数，链路完整可审计；断链的断言不会被写进任何产出。
              </p>
            </div>

            <ul className="flex flex-wrap gap-2">
              {STACK_BADGES.map((badge) => (
                <li
                  key={badge}
                  className="border-default bg-elevated text-tertiary rounded-sm border px-2 py-1 font-mono text-[11px]"
                >
                  {badge}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}
