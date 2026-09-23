import * as React from 'react';

import { cn } from '../lib/cn';

/** Kbd — keyboard hint chip (mono, letter-spaced, token-coloured). */
export function Kbd({ className, children, ...props }: React.ComponentProps<'kbd'>) {
  return (
    <kbd
      className={cn(
        'border-default inline-flex h-5 min-w-5 items-center justify-center rounded-sm border',
        'bg-elevated text-tertiary px-1 font-mono text-[10px] leading-none',
        className,
      )}
      {...props}
    >
      {children}
    </kbd>
  );
}
