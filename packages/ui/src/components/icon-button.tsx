'use client';

import { cva } from 'class-variance-authority';
import type { VariantProps } from 'class-variance-authority';
import * as React from 'react';

import { cn } from '../lib/cn';
import { Spinner } from './spinner';

export const iconButtonVariants = cva(
  [
    'inline-flex shrink-0 items-center justify-center rounded-md',
    'transition-[background-color,border-color,color,opacity] duration-[var(--dur-fast)] ease-forge',
    'outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand',
    'disabled:pointer-events-none disabled:opacity-50',
  ].join(' '),
  {
    variants: {
      variant: {
        ghost: 'text-tertiary hover:bg-hover hover:text-primary',
        secondary:
          'border border-default bg-elevated text-secondary hover:border-strong hover:text-primary',
        outline:
          'border border-strong bg-transparent text-secondary hover:bg-hover hover:text-primary',
      },
      size: {
        sm: 'size-7',
        md: 'size-9 max-md:size-11',
        lg: 'size-11',
      },
    },
    defaultVariants: {
      variant: 'ghost',
      size: 'md',
    },
  },
);

export interface IconButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof iconButtonVariants> {
  /** Required by design (docs/UI.md §9): an icon-only control must be announced. */
  'aria-label': string;
  loading?: boolean;
}

/**
 * IconButton — square icon-only control. `aria-label` is a required prop, so a bare
 * icon button cannot be authored by accident.
 */
export const IconButton = React.forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { className, variant, size, loading = false, disabled, children, type, ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type ?? 'button'}
      aria-busy={loading || undefined}
      className={cn(iconButtonVariants({ variant, size }), className)}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? <Spinner size="sm" /> : children}
    </button>
  );
});
