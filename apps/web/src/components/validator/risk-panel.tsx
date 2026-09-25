'use client';

import { Badge, Card, CardContent, CardHeader, CardTitle } from '@careerforge/ui';
import { ShieldAlert } from 'lucide-react';

import { overallSeverity, riskItems, severityVariant } from '@/components/validator/verdict-copy';
import type { ClaimReason } from '@/lib/validator-api';

/**
 * Reasons and risk — the finding, before the raw codes behind it.
 *
 * One row per distinct rule that fired. The rows are chosen by *rule code*, so a code this build
 * does not know shows its raw name instead of a friendly sentence this page made up. Two rules
 * share a code (`superlative_language`, `low_confidence_sources`); where the API carries no extra
 * field to separate them, the verified message marker decides which copy is correct — see
 * `verdict-copy.ts`.
 */
export function RiskPanel({
  reasons,
  unknowns,
  status,
}: {
  reasons: ClaimReason[];
  unknowns: string[];
  status: string;
}) {
  const risks = riskItems(reasons);
  const worst = overallSeverity(reasons);

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-2">
        <CardTitle className="flex items-center gap-1.5 text-xs">
          <ShieldAlert className="size-3.5" aria-hidden="true" />
          Reasons and risk
        </CardTitle>
        {worst === 'none' ? (
          <Badge variant="outline">no rule fired</Badge>
        ) : (
          // "highest severity", not "blocked": the API sets a reason's severity from whether the
          // adjudicator called the sentence supported, so a `blocker` reason can sit beside a
          // `partially_supported` verdict. Saying "blocker" alone would read as the verdict.
          <Badge variant={severityVariant(worst)}>
            highest severity {worst} · {reasons.length}{' '}
            {reasons.length === 1 ? 'reason' : 'reasons'}
          </Badge>
        )}
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {risks.length === 0 ? (
          <p className="text-secondary text-xs leading-relaxed">
            No rule objected to this sentence: no number without a measurement, no technology
            missing from the evidence, no over-claiming wording. That is what a{' '}
            <span className="font-mono">{status}</span> verdict looks like from the rule layer.
          </p>
        ) : (
          <ul className="flex flex-col gap-2">
            {risks.map((risk) => (
              <li
                key={`${risk.code}:${risk.title}`}
                data-testid="risk-item"
                className="border-subtle bg-base flex flex-col gap-1.5 rounded-md border p-3"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-primary text-xs font-medium" data-testid="risk-title">
                    {risk.title}
                  </p>
                  <Badge variant={severityVariant(risk.severity)}>{risk.severity}</Badge>
                  <span className="text-tertiary font-mono text-[11px]">{risk.code}</span>
                </div>
                <ul className="flex flex-col gap-1">
                  {risk.messages.map((message, index) => (
                    <li
                      key={index}
                      className="text-secondary text-[11px] leading-relaxed"
                      data-testid="risk-message"
                    >
                      {message}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        )}

        {unknowns.length > 0 ? (
          <div className="border-subtle flex flex-col gap-1 border-t pt-3" data-testid="unknowns">
            <p className="text-tertiary text-[11px]">Unknown — not unsupported</p>
            <ul className="flex flex-col gap-1">
              {unknowns.map((item, index) => (
                <li key={index} className="text-secondary font-mono text-[11px]">
                  {item}
                </li>
              ))}
            </ul>
            <p className="text-tertiary text-[11px] leading-relaxed">
              The verdict&rsquo;s own <span className="font-mono">unknowns</span> field: what the
              gate could not resolve either way. A missing fact and a refuted fact are different
              findings, and only one of them is a rejection.
            </p>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
