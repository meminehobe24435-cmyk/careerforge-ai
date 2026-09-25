'use client';

import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  ErrorState,
  Skeleton,
} from '@careerforge/ui';
import { isApiError } from '@careerforge/shared';
import { RefreshCw, Target } from 'lucide-react';
import { useId, useState } from 'react';

import { MatchConclusions } from '@/components/jobs/match-conclusions';
import { MatchFiguresPanel } from '@/components/jobs/match-figures';
import { MatchWhyBreakdown, MatchWhyControl } from '@/components/jobs/match-why';
import { SkillGroupsPanel } from '@/components/jobs/skill-groups';
import { buildSkillGroups, formatPoints, type MatchSource } from '@/components/jobs/job-match-view';
import type { JobDetail, JobMatch, SkillTree } from '@/lib/jobs-api';

export interface JobResultProps {
  analysis: JobDetail;
  tree: SkillTree | undefined;
  /** `undefined` while the tree read is in flight — the page shows skeletons, not zeros. */
  treePending: boolean;
  /**
   * A failed tree read. Rendered instead of an empty tree: "0 requirements" and "the skill tree
   * could not be read" are different facts, and only one of them is true here.
   */
  treeError: unknown;
  onRetryTree: () => void;
  match: JobMatch | null;
  matchSource: MatchSource;
  matchPending: boolean;
  matchError: unknown;
  analyzeWarnings: string[];
  onRecomputeMatch: () => void;
  onRetryMatch: () => void;
}

/**
 * The result half of the split layout.
 *
 * Order follows the reader's question: *what is this role* (header) → *why this number*
 * (`Why N%?`) → *what does it ask for and where do I stand* (the tree) → *what is missing and
 * what is undecided* (strengths / gaps / unknowns) → *how well is any of it evidenced*
 * (coverage, with the API's own definition) → *what do I do next* (the product chain).
 */
export function JobResult({
  analysis,
  tree,
  treePending,
  treeError,
  onRetryTree,
  match,
  matchSource,
  matchPending,
  matchError,
  analyzeWarnings,
  onRecomputeMatch,
  onRetryMatch,
}: JobResultProps) {
  const groups = buildSkillGroups(tree, match);
  const errorIsApi = isApiError(matchError) ? matchError : null;
  const treeErrorIsApi = isApiError(treeError) ? treeError : null;
  // The control sits in the header beside the score; the breakdown it opens renders below the
  // header at full width, because a six-column table inside the header's column would push the
  // page sideways instead of scrolling inside itself.
  const [whyOpen, setWhyOpen] = useState(false);
  const whyId = useId();

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <ResultHeader
        analysis={analysis}
        match={match}
        matchSource={matchSource}
        matchPending={matchPending}
        onRecomputeMatch={onRecomputeMatch}
        whyOpen={whyOpen}
        onToggleWhy={() => setWhyOpen((value) => !value)}
        whyId={whyId}
      />

      {match && whyOpen ? <MatchWhyBreakdown match={match} panelId={whyId} /> : null}

      {matchError ? (
        <ErrorState
          title="匹配计算失败"
          error={matchError}
          code={errorIsApi?.code ?? 'UNKNOWN'}
          requestId={errorIsApi?.requestId ?? null}
          onRetry={onRetryMatch}
          retrying={matchPending}
          statusHref="/system"
          details={
            <span className="font-mono text-[11px]">
              POST /jobs/{analysis.id.slice(0, 8)}…/match
            </span>
          }
        />
      ) : null}

      {treePending ? (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-40" />
          <Skeleton className="h-56" />
        </div>
      ) : treeError ? (
        <ErrorState
          title="技能树读取失败"
          error={treeError}
          code={treeErrorIsApi?.code ?? 'UNKNOWN'}
          requestId={treeErrorIsApi?.requestId ?? null}
          onRetry={onRetryTree}
          retrying={treePending}
          statusHref="/system"
          details={
            <span className="font-mono text-[11px]">
              GET /jobs/{analysis.id.slice(0, 8)}…/skill-tree
            </span>
          }
        />
      ) : (
        <SkillGroupsPanel groups={groups} match={match} />
      )}

      {matchPending && !match ? (
        // The stepper above already says a request is in flight and for how long; these
        // skeletons say which two panels are waiting on it.
        <div className="flex flex-col gap-3">
          <Skeleton className="h-32" />
          <Skeleton className="h-40" />
        </div>
      ) : null}

      {match ? <MatchConclusions match={match} /> : null}

      {match ? (
        <MatchFiguresPanel match={match} source={matchSource} analyzeWarnings={analyzeWarnings} />
      ) : null}

      <NextSteps graphSkillId={graphSkillIdFor(groups, match, analysis)} jobId={analysis.id} />
    </div>
  );
}

/**
 * The node the evidence-graph link opens on.
 *
 * A gap first (the requirement most worth checking), then the first required skill the taxonomy
 * resolved. `null` when there is nothing linkable — the CTA then says so instead of opening the
 * graph on an arbitrary node.
 */
function graphSkillIdFor(
  groups: ReturnType<typeof buildSkillGroups>,
  match: JobMatch | null,
  analysis: JobDetail,
): string | null {
  const topGap = match?.gaps.find((gap) => gap.canonicalId);
  if (topGap) return topGap.canonicalId;
  const missing = groups.required.find((row) => row.verdict === 'missing' && row.canonicalId);
  if (missing?.canonicalId) return missing.canonicalId;
  const required = groups.required.find((row) => row.canonicalId);
  if (required?.canonicalId) return required.canonicalId;
  return analysis.skills.find((skill) => skill.canonicalId)?.canonicalId ?? null;
}

function ResultHeader({
  analysis,
  match,
  matchSource,
  matchPending,
  onRecomputeMatch,
  whyOpen,
  onToggleWhy,
  whyId,
}: {
  analysis: JobDetail;
  match: JobMatch | null;
  matchSource: MatchSource;
  matchPending: boolean;
  onRecomputeMatch: () => void;
  whyOpen: boolean;
  onToggleWhy: () => void;
  whyId: string;
}) {
  return (
    // `sm:items-start` with a `min-w-0` left column: the header is two columns above `sm`, and
    // the summary column has to be allowed to shrink or the mono identifiers push the score out
    // of the viewport (measured at 768 px before `min-w-0` was on the scroll wrapper and the
    // breakdown was moved out of this column).
    <Card className="min-w-0">
      <CardHeader className="flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 flex-col gap-1">
          <h2 className="text-primary text-base font-semibold tracking-tight">{analysis.role}</h2>
          <p className="text-secondary text-xs">
            {analysis.company ? (
              analysis.company
            ) : (
              <span className="text-weak">company: null — 未能从文本中识别公司名</span>
            )}
          </p>
          <div className="text-tertiary flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] tabular-nums">
            {analysis.location ? <span>{analysis.location}</span> : null}
            {analysis.yearsExperienceMin !== null ? (
              <span>≥ {formatPoints(analysis.yearsExperienceMin)} 年</span>
            ) : null}
            {analysis.educationRequirement ? <span>{analysis.educationRequirement}</span> : null}
            {analysis.level ? <span>{analysis.level}</span> : null}
            <span>{analysis.descriptionChars} 字符</span>
            <span>
              job {analysis.id.slice(0, 8)} · {analysis.source}
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge variant={analysis.parseStatus === 'parsed' ? 'outline' : 'weak'}>
              {analysis.parseStatus}
            </Badge>
            <span className="text-tertiary font-mono text-[11px] tabular-nums">
              parseConfidence {analysis.parseConfidence.toFixed(2)}
            </span>
            {analysis.requiredCount + analysis.preferredCount + analysis.bonusCount > 0 ? (
              <span className="text-tertiary font-mono text-[11px] tabular-nums">
                {analysis.requiredCount}/{analysis.preferredCount}/{analysis.bonusCount} 项要求
              </span>
            ) : null}
          </div>
        </div>

        <div className="flex shrink-0 flex-col items-start gap-2 sm:items-end">
          <div className="flex items-baseline gap-1">
            <span
              className="text-primary font-mono text-3xl tabular-nums leading-none"
              aria-label="匹配分数"
            >
              {match ? formatPoints(match.score) : '—'}
            </span>
            <span className="text-tertiary font-mono text-xs">/100</span>
          </div>
          <span className="text-tertiary text-[11px]">
            {match
              ? `${matchSource === 'computed' ? '本次计算' : '库中最新一次'} · match@${match.why.algorithmVersion.replace(/^match@/, '')}`
              : 'match 等待计算'}
          </span>
          <div className="flex flex-wrap items-center gap-2">
            {match ? (
              <MatchWhyControl
                score={match.score}
                open={whyOpen}
                onToggle={onToggleWhy}
                panelId={whyId}
              />
            ) : null}
            <Button
              variant="ghost"
              size="sm"
              onClick={onRecomputeMatch}
              loading={matchPending}
              aria-label="重新计算匹配"
            >
              <RefreshCw className="size-3.5" aria-hidden="true" />
              重新计算
            </Button>
          </div>
        </div>
      </CardHeader>
    </Card>
  );
}

/**
 * The product chain, as three links (PRD §1 "the chain is the product").
 *
 * Each CTA carries the identifier it needs: the graph opens on the skill the match flagged, the
 * validator and the interview start from the same job context. When there is no resolvable
 * skill, the graph link is disabled and says why rather than opening an empty canvas.
 */
function NextSteps({ graphSkillId, jobId }: { graphSkillId: string | null; jobId: string }) {
  const graphHref = graphSkillId
    ? `/app/evidence-graph?skill=${encodeURIComponent(graphSkillId)}`
    : null;
  return (
    <Card className="min-w-0">
      <CardHeader className="flex-row items-center justify-between gap-2">
        <CardTitle className="flex items-center gap-1.5">
          <Target className="size-3.5" aria-hidden="true" />
          Next steps
        </CardTitle>
        <span className="text-tertiary font-mono text-[11px]">job {jobId.slice(0, 8)}</span>
      </CardHeader>
      <CardContent className="flex flex-wrap items-center gap-2">
        <Button asChild variant="secondary" size="sm">
          <a href="/app/validator">Validate a Claim</a>
        </Button>
        <Button asChild variant="secondary" size="sm">
          <a href="/app/interview">Start Interview</a>
        </Button>
        {graphHref ? (
          <Button asChild variant="secondary" size="sm">
            <a href={graphHref} aria-label={`查看证据图谱：${graphSkillId}`}>
              View Evidence Graph
            </a>
          </Button>
        ) : (
          <Button variant="secondary" size="sm" disabled>
            View Evidence Graph
          </Button>
        )}
        {!graphHref ? (
          <span className="text-tertiary text-[11px]">
            这次解析没有任何技能归一化到词表，因此没有可以定位的证据节点。
          </span>
        ) : null}
      </CardContent>
    </Card>
  );
}
