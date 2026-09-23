import * as React from 'react';

import { cn } from '../lib/cn';

export interface EmptyStateProps extends React.ComponentProps<'div'> {
  title: string;
  description?: string;
  /** Optional 20–24px icon rendered above the title. */
  icon?: React.ReactNode;
  /** One clear action (docs/UI.md §6.1: an empty state always offers one next step). */
  action?: React.ReactNode;
  /** Mono footnote — e.g. which endpoint would fill this panel. */
  hint?: string;
}

export function EmptyState({
  title,
  description,
  icon,
  action,
  hint,
  className,
  ...props
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        'border-default bg-surface/60 flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed px-6 py-10 text-center',
        className,
      )}
      {...props}
    >
      {icon ? (
        <span aria-hidden="true" className="text-tertiary">
          {icon}
        </span>
      ) : null}
      <div className="flex flex-col gap-1">
        <p className="text-primary text-sm font-medium">{title}</p>
        {description ? (
          <p className="text-secondary mx-auto max-w-md text-xs leading-relaxed">{description}</p>
        ) : null}
      </div>
      {action ? (
        <div className="mt-1 flex flex-wrap items-center justify-center gap-2">{action}</div>
      ) : null}
      {hint ? <p className="text-tertiary font-mono text-[11px]">{hint}</p> : null}
    </div>
  );
}
