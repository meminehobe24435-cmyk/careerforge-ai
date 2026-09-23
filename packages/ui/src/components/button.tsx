'use client';

import { Slot } from '@radix-ui/react-slot';
import { cva } from 'class-variance-authority';
import type { VariantProps } from 'class-variance-authority';
import * as React from 'react';

import { cn } from '../lib/cn';
import { Spinner } from './spinner';

/**
 * Button — the primary interaction primitive.
 *
 * Variants: primary / secondary / ghost / danger / outline · Sizes: sm / md / lg.
 * Below 768px every size grows to a ≥44px touch target (docs/UI.md §10).
 */
export const buttonVariants = cva(
  [
    'relative inline-flex select-none items-center justify-center gap-2 whitespace-nowrap',
    'rounded-md font-medium',
    'transition-[background-color,border-color,color,opacity] duration-[var(--dur-fast)] ease-forge',
    'outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand',
    'disabled:pointer-events-none disabled:opacity-50',
    '[&_svg]:shrink-0',
  ].join(' '),
  {
    variants: {
      variant: {
        primary: 'bg-brand text-brand-fg hover:bg-brand-strong',
        secondary:
          'border border-default bg-elevated text-primary hover:border-strong hover:bg-hover',
        outline: 'border border-strong bg-transparent text-primary hover:bg-hover',
        ghost: 'text-secondary hover:bg-hover hover:text-primary',
        danger: 'bg-danger text-inverse hover:opacity-90',
      },
      size: {
        sm: 'h-8 px-3 text-xs max-md:h-11 max-md:px-4 max-md:text-sm',
        md: 'h-9 px-4 text-sm max-md:h-11',
        lg: 'h-11 px-5 text-[15px]',
      },
    },
    defaultVariants: {
      variant: 'primary',
      size: 'md',
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  /** Render the single child element instead of a `<button>` (Radix Slot). */
  asChild?: boolean;
  /** Swaps in a spinner, disables the button and sets `aria-busy`. */
  loading?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    className,
    variant,
    size,
    asChild = false,
    loading = false,
    disabled,
    children,
    type,
    ...props
  },
  ref,
) {
  const Comp = (asChild && !loading ? Slot : 'button') as React.ElementType;

  return (
    <Comp
      ref={ref}
      data-loading={loading ? '' : undefined}
      aria-busy={loading || undefined}
      className={cn(buttonVariants({ variant, size }), className)}
      disabled={asChild ? undefined : disabled || loading}
      type={asChild ? undefined : (type ?? 'button')}
      {...props}
    >
      {loading ? (
        <>
          <Spinner size="sm" />
          <span>{children}</span>
        </>
      ) : (
        children
      )}
    </Comp>
  );
});
