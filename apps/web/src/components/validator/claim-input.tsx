'use client';

import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Textarea } from '@careerforge/ui';
import { Zap } from 'lucide-react';

import { DEMO_CLAIMS, type DemoClaim } from '@/components/validator/demo-claims';

/** One sentence, one gate. The textarea is the input; the presets only save typing. */
export function ClaimInput({
  value,
  onValueChange,
  onSubmit,
  onDemo,
  pending,
}: {
  value: string;
  onValueChange: (next: string) => void;
  onSubmit: () => void;
  onDemo: (claim: DemoClaim) => void;
  pending: boolean;
}) {
  const trimmed = value.trim();
  const tooLong = value.length > 1000;

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-2">
        <CardTitle className="flex items-center gap-1.5 text-xs">
          <Zap className="size-3.5" aria-hidden="true" />
          Claim
        </CardTitle>
        <Badge variant="outline">one sentence · max 1000 chars</Badge>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-col gap-1">
          <label htmlFor="claim-text" className="text-secondary text-xs font-medium">
            Résumé sentence
          </label>
          <Textarea
            id="claim-text"
            value={value}
            rows={3}
            maxLength={1000}
            onChange={(event) => onValueChange(event.target.value)}
            onKeyDown={(event) => {
              // Ctrl/Cmd+Enter submits, which is how every other single-field form in the app
              // behaves. The button stays the labelled path; this is the shortcut.
              if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
                event.preventDefault();
                onSubmit();
              }
            }}
            aria-describedby="claim-text-hint"
            aria-invalid={tooLong || undefined}
            placeholder="例如：使用 STM32 与 FreeRTOS 实现串级 PID 控制环"
          />
          <p id="claim-text-hint" className="text-tertiary text-[11px] leading-relaxed">
            The gate checks this sentence against your stored evidence — not against a job
            description and not against the model&rsquo;s opinion of how plausible it sounds.
          </p>
        </div>

        <div className="flex flex-col gap-2">
          <p className="text-tertiary text-[11px]">
            Presets — each one types its sentence and runs the real gate:
          </p>
          <div role="group" aria-label="Demo claims" className="flex flex-wrap gap-2">
            {DEMO_CLAIMS.map((claim) => (
              <Button
                key={claim.id}
                variant="secondary"
                size="sm"
                disabled={pending}
                onClick={() => onDemo(claim)}
                title={claim.hint}
                data-testid={`demo-claim-${claim.id}`}
              >
                {claim.label}
              </Button>
            ))}
          </div>
          <ul className="flex flex-col gap-1">
            {DEMO_CLAIMS.map((claim) => (
              <li key={claim.id} className="text-tertiary text-[11px] leading-relaxed">
                <span className="text-secondary font-mono">{claim.label}</span>
                {' → '}
                {claim.hint} Expect <span className="font-mono">{claim.expectedLabel}</span> on the
                demo evidence.
              </li>
            ))}
          </ul>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-tertiary font-mono text-[11px]">
            {pending ? 'running the gate' : 'POST /evidence/validate'}
          </p>
          <Button
            onClick={onSubmit}
            disabled={pending || trimmed.length < 2 || tooLong}
            loading={pending}
            data-testid="validate-claim"
          >
            Validate claim
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
