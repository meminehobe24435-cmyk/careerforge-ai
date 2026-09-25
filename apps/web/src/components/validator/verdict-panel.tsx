'use client';

import { Badge, Card, CardContent, CardHeader, CardTitle, Tooltip } from '@careerforge/ui';
import { Info } from 'lucide-react';

import {
  CONFIDENCE_TOOLTIP,
  MIN_INDEPENDENT_SOURCES,
  PARTIAL_THRESHOLD,
  SUPPORTED_THRESHOLD,
  VERDICT_COPY,
  allowsResumeInclusion,
  inclusionCopy,
  readConfidence,
} from '@/components/validator/verdict-copy';
import type { ClaimValidation } from '@/lib/validator-api';

/**
 * Verdict + Confidence — the first two panels, in that order.
 *
 * The verdict is stated as a finding ("Verified by evidence"), never as praise: this page is an
 * audit surface, so the colour is a status token and the label says what was decided. The
 * confidence block never appears without its tooltip sentence, because a bare percentage beside a
 * verdict is exactly the number a reader would misread as "probability this is true".
 */
export function VerdictPanel({
  validation,
  claimId,
}: {
  validation: ClaimValidation;
  claimId: string;
}) {
  const verdict = VERDICT_COPY[validation.status];
  const reading = readConfidence(validation.confidence);
  const sources = validation.sources.length;

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
      <Card className="min-w-0">
        <CardHeader className="flex-row items-center justify-between gap-2">
          <CardTitle className="text-xs">Verdict</CardTitle>
          <Badge variant={statusVariant(validation.status)} data-testid="verdict-badge">
            {validation.status}
          </Badge>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <p
            className="text-primary text-base font-semibold leading-snug"
            data-testid="verdict-label"
          >
            {verdict.label}
          </p>
          <p className="text-secondary text-xs leading-relaxed">{verdict.detail}</p>

          <blockquote className="border-default bg-base text-primary rounded-md border px-3 py-2 text-sm leading-relaxed">
            {validation.claim}
          </blockquote>

          <dl className="text-tertiary flex flex-wrap items-center gap-x-4 gap-y-2 text-[11px]">
            <div className="flex items-center gap-1.5">
              <dt>independent evidence kinds</dt>
              <dd className="text-secondary font-mono tabular-nums">
                {validation.independentSourceCount}
              </dd>
            </div>
            <div className="flex items-center gap-1.5">
              <dt>sources cited</dt>
              <dd className="text-secondary font-mono tabular-nums">{sources}</dd>
            </div>
            <div className="flex items-center gap-1.5">
              <dt>quantified</dt>
              <dd className="text-secondary font-mono">
                {validation.hasQuantifiedClaim ? 'yes' : 'no'}
              </dd>
            </div>
            <div className="flex items-center gap-1.5">
              <dt>rules</dt>
              <dd className="text-secondary font-mono">{validation.ruleVersion || '—'}</dd>
            </div>
            <div className="flex items-center gap-1.5">
              <dt>adjudicator</dt>
              <dd className="text-secondary font-mono">{validation.model ?? 'unavailable'}</dd>
            </div>
            <div className="flex items-center gap-1.5">
              <dt>claim</dt>
              <dd className="text-secondary break-all font-mono">{claimId}</dd>
            </div>
          </dl>

          <p className="text-tertiary text-[11px] leading-relaxed">
            {inclusionCopy(validation.status)}
            {' · '}A fully supported verdict needs {MIN_INDEPENDENT_SOURCES} independent evidence
            kinds and a confidence of at least {SUPPORTED_THRESHOLD.toFixed(2)}.
          </p>

          <a
            href="/app/jobs"
            className="text-signal focus-visible:outline-brand w-fit rounded-sm font-mono text-[11px] underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2"
          >
            Analyze a job →
          </a>
        </CardContent>
      </Card>

      <Card className="min-w-0">
        <CardHeader className="flex-row items-center justify-between gap-2">
          <CardTitle className="text-xs">Confidence</CardTitle>
          <Tooltip content={CONFIDENCE_TOOLTIP}>
            <button
              type="button"
              aria-label="What confidence means"
              className="text-tertiary hover:text-secondary focus-visible:outline-brand rounded-sm focus-visible:outline-2 focus-visible:outline-offset-2"
            >
              <Info className="size-3.5" aria-hidden="true" />
            </button>
          </Tooltip>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          <p className="text-secondary font-mono text-2xl tabular-nums" data-testid="confidence">
            {reading.text}
          </p>
          <p className="text-tertiary text-[11px] leading-relaxed">
            {reading.band} is the band the gate&rsquo;s own thresholds put this value in (&ge;{' '}
            {SUPPORTED_THRESHOLD.toFixed(2)} high, &ge; {PARTIAL_THRESHOLD.toFixed(2)} medium). The
            value is the mean confidence of the top five retrieved sources, not a judgement about
            the sentence.
          </p>
          {/*
            The live stack returns `High · 78%` on an `unsupported` verdict, because the retrieved
            material is well-attested even though it does not carry the sentence. A reader who only
            sees the two panels side by side reads that as a contradiction, so the card says which
            question the number answers.
          */}
          {!allowsResumeInclusion(validation.status) ? (
            <p className="text-tertiary text-[11px] leading-relaxed" data-testid="confidence-note">
              Read this beside the verdict, not instead of it: the band measures the evidence that
              was retrieved, not whether that evidence supports the sentence. A high value here
              means the material is well attested and still does not carry this claim.
            </p>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}

function statusVariant(status: ClaimValidation['status']): 'supported' | 'weak' | 'danger' {
  if (status === 'supported') return 'supported';
  if (status === 'partially_supported') return 'weak';
  return 'danger';
}
