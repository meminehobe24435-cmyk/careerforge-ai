import { cva } from 'class-variance-authority';
import type { VariantProps } from 'class-variance-authority';
import * as React from 'react';

import { cn } from '../lib/cn';

/**
 * Badge — small status pill. `supported` / `weak` / `danger` are the evidence semantics
 * from docs/UI.md §1.2 (green = evidenced, amber = partial, red = rejected).
 */
export const badgeVariants = cva(
  [
    'inline-flex items-center gap-1 rounded-sm border px-1.5 py-0.5',
    'font-mono text-[11px] font-medium leading-none tracking-wide tabular-nums',
    'whitespace-nowrap',
  ].join(' '),
  {
    variants: {
      variant: {
        default: 'border-default bg-elevated text-secondary',
        supported: 'border-evidence/30 bg-evidence/10 text-evidence',
        weak: 'border-weak/30 bg-weak/10 text-weak',
        danger: 'border-danger/30 bg-danger/10 text-danger',
        signal: 'border-signal/30 bg-signal/10 text-signal',
        outline: 'border-strong bg-transparent text-secondary',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  },
);

export interface BadgeProps
  extends React.ComponentProps<'span'>, VariantProps<typeof badgeVariants> {
  /** Renders `role="status"` so screen readers announce status changes (docs/UI.md §9). */
  announce?: boolean;
}

export function Badge({ className, variant, announce, ...props }: BadgeProps) {
  return (
    <span
      role={announce ? 'status' : undefined}
      className={cn(badgeVariants({ variant }), className)}
      {...props}
    />
  );
}
