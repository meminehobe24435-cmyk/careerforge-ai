import * as React from 'react';

import { cn } from '../lib/cn';

export const Input = React.forwardRef<HTMLInputElement, React.ComponentProps<'input'>>(
  function Input({ className, type = 'text', ...props }, ref) {
    return (
      <input
        ref={ref}
        type={type}
        className={cn(
          'border-default bg-base text-primary h-9 w-full min-w-0 rounded-md border px-3 text-sm',
          'placeholder:text-tertiary',
          'ease-forge transition-colors duration-[var(--dur-fast)]',
          'hover:border-strong',
          // `ring-brand/40` measured 2.32:1 against `--bg-base` — below the 3:1 that WCAG 2.2
          // requires of a focus indicator, so the ring was there but not reliably visible. The
          // full brand colour is 9.28:1 and is the "2px brand focus ring" docs/UI.md §9 asks for.
          'focus-visible:border-brand focus-visible:ring-brand focus-visible:outline-none focus-visible:ring-2',
          'disabled:cursor-not-allowed disabled:opacity-50',
          'aria-invalid:border-danger aria-invalid:ring-danger/30',
          'max-md:h-11',
          className,
        )}
        {...props}
      />
    );
  },
);
