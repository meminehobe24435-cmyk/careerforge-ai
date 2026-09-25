'use client';

import { useState } from 'react';
import { Badge, Button, Card, CardContent, CardHeader, CardTitle } from '@careerforge/ui';
import { ChevronDown } from 'lucide-react';

import { riskItems } from '@/components/validator/verdict-copy';
import type { ClaimReason } from '@/lib/validator-api';

/**
 * "Why was this rejected?" — the expandable audit trail.
 *
 * The panel above says *what* the gate objected to; this one shows the raw rule codes and messages
 * and one line on what each of those rules tests, so a candidate can check the objection instead
 * of taking it on faith. Collapsed by default: the interesting thing on first read is the finding,
 * and the codes are the receipt. Every rule identified in
 * `packages/ai/careerforge_ai/parsing/claim_rules.py` and `agents/validator_decide.py`.
 */
export function RejectedPanel({ reasons }: { reasons: ClaimReason[] }) {
  const [open, setOpen] = useState(false);
  const risks = riskItems(reasons);

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-2">
        <CardTitle className="text-xs">Why was this rejected?</CardTitle>
        <Badge variant="outline">{risks.length} rule codes</Badge>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <Button
          variant="secondary"
          size="sm"
          className="w-fit"
          aria-expanded={open}
          aria-controls="validator-rejected-reasons"
          onClick={() => setOpen((current) => !current)}
          data-testid="why-rejected"
        >
          <ChevronDown
            className={open ? 'size-3.5 rotate-180 transition-transform' : 'size-3.5'}
            aria-hidden="true"
          />
          {open ? 'Hide the rule detail' : 'Show the rule detail'}
        </Button>

        {open ? (
          <div id="validator-rejected-reasons" className="flex flex-col gap-2">
            <p className="text-tertiary text-[11px] leading-relaxed">
              Exactly what the API returned, plus one line on what each rule tests. The codes are
              the gate&rsquo;s own vocabulary; this page does not translate them into anything the
              backend did not say.
            </p>
            {risks.length === 0 ? (
              <p className="text-secondary text-[11px] leading-relaxed">
                No rule fired for this claim, so there is nothing to explain. The verdict came from
                the evidence arithmetic and the adjudicator alone.
              </p>
            ) : (
              <ol className="flex flex-col gap-3">
                {risks.map((risk) => (
                  <li
                    key={`why:${risk.code}:${risk.title}`}
                    className="flex flex-col gap-1"
                    data-testid="rule-explanation"
                  >
                    <p className="text-primary font-mono text-[11px]">
                      {risk.code}
                      <span className="text-tertiary"> · {risk.severity}</span>
                      {risk.unknown ? (
                        <span className="text-tertiary"> · no description in this build</span>
                      ) : null}
                    </p>
                    <p className="text-secondary text-[11px] leading-relaxed">{risk.explanation}</p>
                    <ul className="flex flex-col gap-1">
                      {risk.messages.map((message, index) => (
                        <li key={index} className="text-tertiary text-[11px] leading-relaxed">
                          {message}
                        </li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ol>
            )}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
