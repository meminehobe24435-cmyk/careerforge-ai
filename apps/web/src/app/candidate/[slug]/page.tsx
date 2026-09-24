import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { Badge, Card, CardContent, CardHeader, CardTitle, Separator } from '@careerforge/ui';
import { ExternalLink, MapPin } from 'lucide-react';

import { SkillEvidence } from '@/components/public/skill-evidence';
import { PUBLIC_API_BASE_URL, fetchPublicProfile } from '@/lib/public-api';

export const dynamic = 'force-dynamic';

interface PageProps {
  params: Promise<{ slug: string }>;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params;
  const { data } = await fetchPublicProfile(slug);
  if (!data) return { title: '候选人页面不存在' };
  return {
    title: `${data.displayName} · CareerForge 证据画像`,
    description: data.headline || data.summary.slice(0, 120),
  };
}

/**
 * `/candidate/[slug]` — the Recruiter View, rendered on the server.
 *
 * A server component on purpose. This is the one page whose whole purpose is to be *shared*:
 * it must render for a stranger with no account, no token and no JavaScript-dependent wait, and
 * its content should be in the HTML a link preview or a crawler sees. Everything private was
 * already filtered by the API before it arrived here — this component renders what it is given
 * and never decides what is safe to show.
 */
export default async function CandidatePage({ params }: PageProps) {
  const { slug } = await params;
  const { data, status } = await fetchPublicProfile(slug);

  if (status === 404) notFound();

  if (!data) {
    return (
      <main className="mx-auto flex min-h-dvh max-w-3xl flex-col gap-4 p-6">
        <h1 className="text-primary text-xl font-semibold">暂时读不到这个页面</h1>
        <Card>
          <CardContent className="pt-5">
            <p className="text-secondary text-sm leading-relaxed">
              {status === 0
                ? '无法连接后端服务。这不代表页面不存在——请稍后重试。'
                : `后端返回了 HTTP ${status}。`}
            </p>
            <p className="text-tertiary mt-2 font-mono text-[11px]">
              {PUBLIC_API_BASE_URL}/public/candidate/{slug}
            </p>
          </CardContent>
        </Card>
      </main>
    );
  }

  const { meta } = data;
  const backedSkills = data.skills.filter((skill) => skill.evidenceCount > 0).length;

  return (
    <main className="mx-auto flex min-h-dvh max-w-3xl flex-col gap-6 p-6 sm:p-8">
      <header className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-primary text-2xl font-semibold tracking-tight">{data.displayName}</h1>
          <Badge variant="signal">Verified by evidence</Badge>
        </div>
        {data.headline ? <p className="text-secondary text-sm">{data.headline}</p> : null}
        <div className="text-tertiary flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[11px]">
          {data.location ? (
            <span className="inline-flex items-center gap-1">
              <MapPin className="size-3" aria-hidden="true" />
              {data.location}
            </span>
          ) : null}
          {data.githubUrl ? (
            <a
              className="inline-flex items-center gap-1 underline decoration-dotted underline-offset-2"
              href={data.githubUrl}
              target="_blank"
              rel="noreferrer noopener"
            >
              GitHub <ExternalLink className="size-3" aria-hidden="true" />
            </a>
          ) : null}
          {data.websiteUrl ? (
            <a
              className="inline-flex items-center gap-1 underline decoration-dotted underline-offset-2"
              href={data.websiteUrl}
              target="_blank"
              rel="noreferrer noopener"
            >
              个人主页 <ExternalLink className="size-3" aria-hidden="true" />
            </a>
          ) : null}
          <span>
            {data.skills.length} 项技能 · {backedSkills} 项带证据 · 证据覆盖率{' '}
            {(meta.evidenceCoverage * 100).toFixed(0)}%
          </span>
        </div>
      </header>

      {data.summary ? (
        <Card>
          <CardHeader>
            <CardTitle>概述</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-secondary whitespace-pre-line text-sm leading-relaxed">
              {data.summary}
            </p>
          </CardContent>
        </Card>
      ) : null}

      <section aria-labelledby="skills-heading" className="flex flex-col gap-3">
        <h2 id="skills-heading" className="text-primary text-sm font-semibold">
          Evidence-backed Skills
        </h2>
        <SkillEvidence
          slug={meta.slug}
          skills={data.skills}
          evidenceVisible={!meta.hiddenSections.includes('evidence')}
        />
      </section>

      {data.projects.length > 0 ? (
        <section aria-labelledby="projects-heading" className="flex flex-col gap-3">
          <h2 id="projects-heading" className="text-primary text-sm font-semibold">
            Projects
          </h2>
          {data.projects.map((project) => (
            <Card key={project.name}>
              <CardHeader>
                <CardTitle>{project.name}</CardTitle>
                {project.role ? <p className="text-tertiary text-xs">{project.role}</p> : null}
              </CardHeader>
              <CardContent className="flex flex-col gap-2">
                {project.summary ? (
                  <p className="text-secondary text-sm leading-relaxed">{project.summary}</p>
                ) : null}
                {project.techStack.length > 0 ? (
                  <div className="flex flex-wrap gap-1.5">
                    {project.techStack.map((tech) => (
                      <Badge key={tech} variant="outline">
                        {tech}
                      </Badge>
                    ))}
                  </div>
                ) : null}
                {project.repositoryUrl ? (
                  <a
                    className="text-tertiary font-mono text-[11px] underline decoration-dotted underline-offset-2"
                    href={project.repositoryUrl}
                    target="_blank"
                    rel="noreferrer noopener"
                  >
                    {project.repositoryUrl}
                  </a>
                ) : null}
              </CardContent>
            </Card>
          ))}
        </section>
      ) : null}

      {data.highlights.length > 0 ? (
        <section aria-labelledby="highlights-heading" className="flex flex-col gap-3">
          <h2 id="highlights-heading" className="text-primary text-sm font-semibold">
            Engineering Highlights
          </h2>
          <ul className="flex flex-col gap-2">
            {data.highlights.map((item) => (
              <li key={item} className="text-secondary flex gap-2 text-sm leading-relaxed">
                <span aria-hidden="true" className="text-signal">
                  ▪
                </span>
                {item}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {data.interviewTopics.length > 0 ? (
        <section aria-labelledby="topics-heading" className="flex flex-col gap-3">
          <h2 id="topics-heading" className="text-primary text-sm font-semibold">
            Interview Topics
          </h2>
          <p className="text-tertiary text-xs">
            可以在面试中深入讨论的话题——每题都能追到具体证据。
          </p>
          <ul className="flex flex-wrap gap-2">
            {data.interviewTopics.map((topic) => (
              <li key={topic}>
                <Badge variant="outline">{topic}</Badge>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <Separator />

      <footer className="text-tertiary flex flex-col gap-2 text-[11px] leading-relaxed">
        {meta.hiddenSections.length > 0 ? (
          <p>
            候选人隐藏了 {meta.hiddenSections.length} 个板块（
            {meta.hiddenSections.join('、')}）。页面显示的是他们选择公开的部分。
          </p>
        ) : null}
        {meta.redactions.length > 0 ? (
          <p>
            页面已自动脱敏 {meta.redactions.length} 处个人信息（邮箱 / 电话等），
            脱敏发生在服务端，不是在前端隐藏。
          </p>
        ) : null}
        <p>
          本页由 CareerForge AI 生成，所有技能都可点击展开真实证据 · 浏览 {meta.viewCount} 次
          {meta.generatedAt ? ` · 生成于 ${meta.generatedAt.slice(0, 10)}` : ''}
        </p>
      </footer>
    </main>
  );
}
