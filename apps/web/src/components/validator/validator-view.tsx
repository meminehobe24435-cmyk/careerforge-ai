'use client';

import { useState } from 'react';
import {
  Badge,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CodeBlock,
  EmptyState,
  ErrorState,
  Skeleton,
} from '@careerforge/ui';
import { isApiError } from '@careerforge/shared';
import { ScanSearch } from 'lucide-react';

import { ClaimInput } from '@/components/validator/claim-input';
import type { DemoClaim } from '@/components/validator/demo-claims';
import { EvidencePanel } from '@/components/validator/evidence-panel';
import { RejectedPanel } from '@/components/validator/rejected-panel';
import { RewritePanel } from '@/components/validator/rewrite-panel';
import { RiskPanel } from '@/components/validator/risk-panel';
import { VerdictPanel } from '@/components/validator/verdict-panel';
import { VALIDATOR_ENDPOINT, VERDICT_COPY } from '@/components/validator/verdict-copy';
import { useEvidenceIndex, useValidateClaim } from '@/hooks/use-validator';
import { API_BASE_URL } from '@/lib/api';

/**
 * `/app/validator` — Resume Claim Validator.
 *
 * One sentence in, one verdict out, and the whole chain visible: **Claim → Evidence → Confidence
 * → Source → Decision**. The page refuses three temptations that would make it look better and be
 * worth less:
 *
 * 1. it never scores the résumé — there is no overall grade, because a gate that graded prose
 *    would invite optimising the grade instead of the evidence;
 * 2. it never prints a number the API did not return (`confidence` is the gate's own arithmetic,
 *    source confidence comes from the evidence rows, and an absent value says so);
 * 3. it never re-states a rejection without its rule code, because a verdict a reader cannot check
 *    is indistinguishable from a bug.
 *
 * The verdicts come from `POST /evidence/validate`, which runs the same gate as
 * `/ai/validate/claim` but supplies it with a retriever over the candidate's stored evidence —
 * see `lib/validator-api.ts` for why the stateless endpoint cannot carry this page.
 */
export function ValidatorView() {
  const [claimText, setClaimText] = useState('');
  const validation = useValidateClaim();
  const evidenceIndex = useEvidenceIndex();

  const submit = (text: string) => {
    const trimmed = text.trim();
    if (trimmed.length < 2) return;
    validation.mutate({ text: trimmed, section: 'summary' });
  };

  const onDemo = (claim: DemoClaim) => {
    setClaimText(claim.text);
    submit(claim.text);
  };

  const apiError = isApiError(validation.error) ? validation.error : null;
  const result = validation.data ?? null;
  const submitted = validation.variables?.text ?? null;
  const editedSince = result !== null && submitted !== null && claimText.trim() !== submitted;
  const evidenceCount = evidenceIndex.data?.count ?? null;

  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <h1 className="text-primary text-lg font-semibold tracking-tight">
            Resume Claim Validator
          </h1>
          <p className="text-secondary text-xs leading-relaxed">
            Check whether a resume statement is actually supported by your evidence.
          </p>
          <p className="text-tertiary font-mono text-[11px]">
            {VALIDATOR_ENDPOINT} · {API_BASE_URL}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {evidenceCount === null ? (
            <Badge variant="outline">evidence base: reading…</Badge>
          ) : evidenceCount === 0 ? (
            <Badge variant="danger" data-testid="evidence-base">
              evidence base: empty
            </Badge>
          ) : (
            <Badge variant="outline" data-testid="evidence-base">
              evidence base: {evidenceCount}
              {evidenceIndex.data?.truncated ? '+' : ''} rows
            </Badge>
          )}
        </div>
      </header>

      <h2 className="sr-only">Claim to validate</h2>
      <ClaimInput
        value={claimText}
        onValueChange={setClaimText}
        onSubmit={() => submit(claimText)}
        onDemo={onDemo}
        pending={validation.isPending}
      />

      {evidenceCount === 0 ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-xs">Your evidence base is empty</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            <p className="text-secondary text-xs leading-relaxed">
              No evidence is stored for this account, so every claim will come back unsupported —
              not because the sentence is false, but because there is nothing to check it against.
              Import your material first: <span className="font-mono">POST /profile/import</span>{' '}
              and a document upload are what fill the evidence rows this page reads.
            </p>
          </CardContent>
        </Card>
      ) : null}

      <section aria-labelledby="validator-result" className="flex flex-col gap-4">
        <h2 id="validator-result" className="sr-only">
          Validation result
        </h2>

        {validation.isPending ? <ResultSkeleton /> : null}

        {!validation.isPending && validation.isError ? (
          <ErrorState
            title={apiError?.isNetworkError ? 'Backend not reachable' : 'The gate did not answer'}
            error={validation.error}
            code={apiError?.code ?? 'UNKNOWN'}
            requestId={apiError?.requestId ?? null}
            onRetry={() => submit(claimText)}
            retryLabel="Retry the same claim"
            retrying={validation.isPending}
            statusHref="/system"
            details={
              <CodeBlock
                filename="API base URL"
                code={API_BASE_URL}
                language="txt"
                maxHeight={64}
              />
            }
          />
        ) : null}

        {!validation.isPending && !validation.isError && result === null ? (
          <EmptyState
            icon={<ScanSearch className="size-5" />}
            title="Validate a resume statement against your evidence."
            description="Type one sentence — or pick a preset — and the gate reports whether your own material carries it, which sources it rests on, and what it would have to remove to make the sentence safe."
            hint={`${VALIDATOR_ENDPOINT} → status, confidence, sources, reasons`}
          />
        ) : null}

        {!validation.isPending && result !== null ? (
          <div className="flex flex-col gap-4" data-testid="validator-result">
            {editedSince ? (
              <p className="text-weak text-[11px] leading-relaxed" data-testid="edited-since">
                The sentence in the box has changed since this verdict was returned. The panel below
                still describes the sentence it was run against.
              </p>
            ) : null}

            <VerdictPanel validation={result.claim} claimId={result.claimId} />

            <EvidencePanel
              sources={result.claim.sources}
              index={evidenceIndex.data ?? null}
              indexError={evidenceIndex.isError}
            />

            <RiskPanel
              reasons={result.claim.reasons}
              unknowns={result.claim.unknowns}
              status={VERDICT_COPY[result.claim.status].label}
            />

            <RewritePanel
              original={result.claim.claim}
              rewrite={result.claim.safeRewrite}
              reasons={result.claim.reasons}
            />

            <RejectedPanel reasons={result.claim.reasons} />
          </div>
        ) : null}
      </section>
    </div>
  );
}

/** The result panel's pending shape — the same order the answer will arrive in. */
function ResultSkeleton() {
  return (
    <div className="flex flex-col gap-4" data-testid="validator-skeleton">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Skeleton className="h-48" />
        <Skeleton className="h-48" />
      </div>
      <Skeleton className="h-40" />
      <Skeleton className="h-32" />
      <Skeleton className="h-32" />
      <Skeleton className="h-24" />
    </div>
  );
}
