'use client';

import { useState } from 'react';
import { Badge, Button, Card, CardContent, CardHeader, CardTitle } from '@careerforge/ui';
import { ChevronDown } from 'lucide-react';

import {
  affirmativeExplanation,
  riskItems,
  rulePanelTitle,
} from '@/components/validator/verdict-copy';
import type { ClaimReason, ClaimSource, ClaimStatus } from '@/lib/validator-api';

interface RejectedPanelProps {
  /** The verdict this panel belongs to. The heading is phrased for it, not for a rejection. */
  status: ClaimStatus;
  reasons: ClaimReason[];
  /** What the gate retrieved — printed in place of an empty rule list, never invented. */
  sources: ClaimSource[];
  /** `claim.independentSourceCount`: distinct evidence kinds behind the retrieved sources. */
  independentSourceCount: number;
  confidence: number;
}

/**
 * The expandable audit trail under a verdict.
 *
 * Two panels share the slot, and which one appears is decided by the data:
 *
 * * **rule codes present** — the panel says *what* the gate objected to, in the raw codes and
 *   messages plus one line on what each rule tests, so a candidate can check the objection instead
 *   of taking it on faith. Collapsed by default: the finding matters first, the codes are the
 *   receipt. The heading follows the verdict (`Why is this supported?` / `…only partially
 *   supported?` / `Why was this rejected?`), because a reader who has just been told their sentence
 *   is supported must not then be asked why it was rejected;
 * * **no rule codes** — there is no rejection section to render at all, so the affirmative
 *   explanation takes its place and states what the verdict rested on. Rendering an empty list
 *   with a `0 rule codes` badge would be a section that exists only to say it has nothing to say.
 *
 * Every rule identified in `packages/ai/careerforge_ai/parsing/claim_rules.py` and
 * `agents/validator_decide.py`.
 */
export function RejectedPanel({
  status,
  reasons,
  sources,
  independentSourceCount,
  confidence,
}: RejectedPanelProps) {
  const [open, setOpen] = useState(false);
  const risks = riskItems(reasons);

  if (risks.length === 0) {
    const explanation = affirmativeExplanation(status, {
      sources,
      independentSourceCount,
      confidence,
    });
    return (
      <Card data-testid="affirmative-explanation">
        <CardHeader>
          <CardTitle className="text-xs">{explanation.title}</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-secondary text-[11px] leading-relaxed">{explanation.body}</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-2">
        <CardTitle className="text-xs">{rulePanelTitle(status)}</CardTitle>
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
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
