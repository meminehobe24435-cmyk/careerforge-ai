'use client';

import { Badge, Card, CardContent, CardHeader, CardTitle, EmptyState } from '@careerforge/ui';
import { Layers } from 'lucide-react';

import { channelLabel, evidenceGraphHref } from '@/components/validator/verdict-copy';
import type { ClaimSource, EvidenceIndex } from '@/lib/validator-api';

/** `0.9123` → `0.91`. Two places is what the API reports; more would imply precision it has. */
function ratio(value: number): string {
  return Number.isFinite(value) ? value.toFixed(2) : '—';
}

/**
 * Evidence — the sources the verdict was decided on, one block each.
 *
 * Every row answers "why is this here": the title and kind say what the source is, the excerpt is
 * what a reviewer reads, the relevance is how well retrieval matched it, the confidence is the
 * evidence's own stored score, and the channel says which retriever arm found it. The confidence
 * is read from the evidence record (`GET /evidence`), not from the verdict: the verdict's cited
 * source carries relevance only, and printing a relevance under the label "confidence" would be
 * two different numbers sharing one name.
 */
export function EvidencePanel({
  sources,
  index,
  indexError,
}: {
  sources: ClaimSource[];
  index: EvidenceIndex | null;
  indexError: boolean;
}) {
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-2">
        <CardTitle className="text-xs">Evidence</CardTitle>
        <Badge variant={sources.length > 0 ? 'outline' : 'weak'}>
          {sources.length} cited from your evidence base
        </Badge>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        {sources.length === 0 ? (
          <EmptyState
            icon={<Layers className="size-5" />}
            title="No source matched this claim"
            description="Retrieval returned nothing that supports this sentence, so the verdict rests on the rules alone. That is a statement about the evidence base, not about you."
            hint="POST /evidence/validate → sources []"
          />
        ) : (
          <ul className="flex flex-col gap-2">
            {sources.map((source) => {
              const record = index?.byId[source.evidenceId] ?? null;
              return (
                <li
                  key={source.evidenceId}
                  data-testid="evidence-source"
                  className="border-subtle bg-base flex flex-col gap-2 rounded-md border p-3"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <a
                      href={evidenceGraphHref(source)}
                      className="text-signal focus-visible:outline-brand rounded-sm text-xs font-medium underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2"
                    >
                      {source.title || '(untitled source)'}
                    </a>
                    <Badge variant="outline">{source.kind}</Badge>
                    <Badge variant="default" title="Which retriever arm found this source">
                      channel {channelLabel(source.channel)}
                    </Badge>
                  </div>

                  {source.snippet ? (
                    <p className="text-secondary text-[11px] leading-relaxed">{source.snippet}</p>
                  ) : (
                    <p className="text-tertiary text-[11px]">
                      No excerpt returned for this source.
                    </p>
                  )}

                  <dl className="text-tertiary flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px]">
                    <div className="flex items-center gap-1.5">
                      <dt>relevance</dt>
                      <dd className="text-secondary font-mono tabular-nums">
                        {ratio(source.relevance)}
                      </dd>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <dt>confidence</dt>
                      <dd className="text-secondary font-mono tabular-nums">
                        {/* `null` is not `0`: an index that has not loaded, or a row that is
                            absent from it, is reported as unavailable. */}
                        {indexError
                          ? 'unavailable'
                          : record
                            ? ratio(record.confidence)
                            : 'not in index'}
                      </dd>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <dt>locator</dt>
                      <dd className="text-secondary font-mono">
                        {source.locator && source.locator !== '—' ? source.locator : '—'}
                      </dd>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <dt>evidence</dt>
                      <dd className="text-secondary break-all font-mono">{source.evidenceId}</dd>
                    </div>
                  </dl>
                </li>
              );
            })}
          </ul>
        )}
        <p className="text-tertiary text-[11px] leading-relaxed">
          Relevance is how well retrieval matched the sentence. Confidence is the evidence
          record&rsquo;s own stored score, read from{' '}
          <span className="font-mono">GET /evidence</span>
          {index ? ` (${index.count}${index.truncated ? '+' : ''} rows read)` : ''} — the citations
          themselves carry relevance only. Each title links to the evidence graph, where that node
          and its edges can be inspected.
        </p>
      </CardContent>
    </Card>
  );
}
