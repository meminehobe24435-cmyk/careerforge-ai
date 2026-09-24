'use client';

import { useState } from 'react';
import { Badge, Card, cn } from '@careerforge/ui';
import type { PublicEvidence, PublicSkill } from '@careerforge/shared';

import { PUBLIC_API_BASE_URL, fetchPublicSkillEvidence } from '@/lib/public-api';

interface SkillEvidenceProps {
  slug: string;
  skills: PublicSkill[];
  /** False when the candidate keeps citations private — the chips stay, the panel explains. */
  evidenceVisible: boolean;
}

/**
 * The evidence-backed skills, and the click that expands one in place.
 *
 * The evidence is fetched on first expand rather than shipped with the page. Two reasons, both
 * about the reader: the initial HTML stays small enough to open on a phone at a career fair, and
 * the request that fetches it is the *unauthenticated* one — which is the whole claim being made
 * to a recruiter ("you can check this without an account"). Failures are shown as failures: an
 * empty panel would read as "there is no evidence", which is a different statement.
 */
export function SkillEvidence({ slug, skills, evidenceVisible }: SkillEvidenceProps) {
  const [openSkill, setOpenSkill] = useState<string | null>(null);
  const [evidence, setEvidence] = useState<Record<string, PublicEvidence[]>>({});
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function toggle(skill: PublicSkill) {
    const id = skill.canonicalId;
    if (openSkill === id) {
      setOpenSkill(null);
      return;
    }
    setOpenSkill(id);
    setError(null);
    if (evidence[id]) return;
    if (!evidenceVisible) return;

    setLoading(id);
    const result = await fetchPublicSkillEvidence(slug, id);
    setLoading(null);
    if (result.status === 0) {
      setError('无法连接后端服务，证据暂时读不到——这不代表没有证据。');
      return;
    }
    if (result.data === null) {
      setError(`读取证据失败（HTTP ${result.status}）。`);
      return;
    }
    setEvidence((current) => ({ ...current, [id]: result.data ?? [] }));
  }

  if (skills.length === 0) {
    return (
      <Card className="p-4">
        <p className="text-secondary text-sm">这位候选人目前没有公开任何技能。</p>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <ul className="flex flex-wrap gap-2">
        {skills.map((skill) => {
          const open = openSkill === skill.canonicalId;
          return (
            <li key={skill.canonicalId}>
              <button
                type="button"
                onClick={() => void toggle(skill)}
                aria-expanded={open}
                className={cn(
                  'border-subtle bg-surface hover:border-signal/40 focus-visible:ring-signal/50 flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2',
                  open && 'border-signal/50 bg-signal/10',
                )}
              >
                <span className="text-primary font-medium">{skill.displayName}</span>
                <span className="text-tertiary font-mono text-[10px]">{skill.evidenceCount}</span>
              </button>
            </li>
          );
        })}
      </ul>

      {openSkill ? (
        <Card className="bg-sunken/40 p-4" data-testid="evidence-panel">
          {(() => {
            const skill = skills.find((candidate) => candidate.canonicalId === openSkill);
            if (!skill) return null;
            return (
              <div className="flex flex-col gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-primary text-sm font-semibold">{skill.displayName}</h3>
                  <Badge variant="outline">{skill.category}</Badge>
                  <span className="text-tertiary font-mono text-[11px]">
                    置信度 {(skill.confidence * 100).toFixed(0)}% · {skill.corroboration} 个独立来源
                  </span>
                </div>

                {!evidenceVisible ? (
                  <p className="text-secondary text-xs leading-relaxed">
                    这位候选人选择不公开引用来源，因此这里只显示技能本身与它的证据数量。
                    证据是真实存在的（{skill.evidenceCount} 条），只是没有公开。
                  </p>
                ) : loading === openSkill ? (
                  <p className="text-secondary text-xs">正在读取证据…</p>
                ) : error ? (
                  <p className="text-danger text-xs">{error}</p>
                ) : (evidence[openSkill] ?? []).length === 0 ? (
                  <p className="text-secondary text-xs">
                    这条技能没有可公开的引用（可能来源是本地文件，陌生人打不开）。
                  </p>
                ) : (
                  <ul className="flex flex-col gap-2">
                    {(evidence[openSkill] ?? []).map((item) => (
                      <li key={item.evidenceId} className="flex flex-col gap-0.5">
                        <span className="text-primary text-xs">
                          {item.url ? (
                            <a
                              href={item.url}
                              target="_blank"
                              rel="noreferrer noopener"
                              className="underline decoration-dotted underline-offset-2"
                            >
                              {item.title}
                            </a>
                          ) : (
                            item.title
                          )}
                        </span>
                        <span className="text-tertiary font-mono text-[10px]">
                          {item.kind}
                          {item.locator ? ` · ${item.locator}` : ''} · 置信度{' '}
                          {(item.confidence * 100).toFixed(0)}%
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            );
          })()}
        </Card>
      ) : null}

      <p className="text-tertiary text-[11px] leading-relaxed">
        点击技能即可就地展开证据，无需登录。所有引用都来自候选人自己的材料（
        <span className="font-mono">{PUBLIC_API_BASE_URL}</span>）。
      </p>
    </div>
  );
}
