'use client';

import { Badge, Card, CardContent, CardHeader, CardTitle, CopyButton } from '@careerforge/ui';
import { FileCheck2 } from 'lucide-react';

import { noRewriteCopy } from '@/components/validator/verdict-copy';
import type { ClaimReason, SafeRewrite } from '@/lib/validator-api';

/**
 * Suggested rewrite — the constructive half of the gate.
 *
 * The original always sits above the suggestion: a rewrite shown without the sentence it replaces
 * is an edit the reader cannot audit. When the API returns no rewrite the panel says so and says
 * why, because "no suggestion" and "the gate failed to produce one" must not look the same.
 */
export function RewritePanel({
  original,
  rewrite,
  reasons,
}: {
  original: string;
  rewrite: SafeRewrite | null;
  reasons: ClaimReason[];
}) {
  const declined = noRewriteCopy(reasons);

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-2">
        <CardTitle className="flex items-center gap-1.5 text-xs">
          <FileCheck2 className="size-3.5" aria-hidden="true" />
          Suggested rewrite
        </CardTitle>
        {rewrite ? (
          <Badge variant="outline">evidence-safe wording</Badge>
        ) : (
          <Badge variant="default">none offered</Badge>
        )}
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-col gap-1">
          <p className="text-tertiary text-[11px]">Original</p>
          <p
            className="border-subtle bg-base text-secondary rounded-md border px-3 py-2 text-sm leading-relaxed"
            data-testid="rewrite-original"
          >
            {original}
          </p>
        </div>

        {rewrite ? (
          <div className="flex flex-col gap-1">
            <p className="text-tertiary text-[11px]">Evidence-safe wording</p>
            <p
              className="border-evidence/30 bg-evidence/5 text-primary rounded-md border px-3 py-2 text-sm leading-relaxed"
              data-testid="rewrite-text"
            >
              {rewrite.text}
            </p>
            <div className="flex flex-wrap items-center gap-2">
              {/* `size="md"` + `w-auto` + `whitespace-nowrap`: `CopyButton` is an IconButton, whose
                  `size-*` utilities are square and whose label has no `nowrap`. Left square the
                  label wrapped into a 28 px column (1440 screenshot); without `nowrap` it broke over
                  two lines (375), and `max-md:size-11` then clipped it so the label spilled over
                  'Removed: …' — hence the mobile width override as well. */}
              <CopyButton
                value={rewrite.text}
                label="Copy rewrite"
                copiedLabel="Copied rewrite"
                showLabel
                size="md"
                variant="secondary"
                className="h-8 w-auto whitespace-nowrap px-2 max-md:h-11 max-md:w-auto"
              />
              {rewrite.removedClaims.length > 0 ? (
                <p className="text-tertiary text-[11px]">
                  Removed:{' '}
                  <span className="text-secondary font-mono">
                    {rewrite.removedClaims.join(', ')}
                  </span>
                </p>
              ) : null}
            </div>
            {rewrite.rationale ? (
              <p className="text-tertiary text-[11px] leading-relaxed">{rewrite.rationale}</p>
            ) : null}
          </div>
        ) : (
          <div className="flex flex-col gap-1" data-testid="rewrite-declined">
            <p className="text-secondary text-xs font-medium">{declined.title}</p>
            <p className="text-tertiary text-[11px] leading-relaxed">{declined.body}</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
