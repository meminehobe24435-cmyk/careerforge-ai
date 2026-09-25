import * as React from 'react';

import { cn } from '../lib/cn';

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.ComponentProps<'textarea'>>(
  function Textarea({ className, rows = 5, ...props }, ref) {
    return (
      <textarea
        ref={ref}
        rows={rows}
        className={cn(
          'border-default bg-base text-primary w-full min-w-0 rounded-md border px-3 py-2 text-sm',
          'placeholder:text-tertiary',
          'ease-forge transition-colors duration-[var(--dur-fast)]',
          'hover:border-strong',
          // Same as `input.tsx`: `ring-brand/40` was a 2.32:1 ring, below the 3:1 WCAG 2.2 floor
          // for a focus indicator. `ring-brand` is 9.28:1 and matches docs/UI.md §9.
          'focus-visible:border-brand focus-visible:ring-brand focus-visible:outline-none focus-visible:ring-2',
          'disabled:cursor-not-allowed disabled:opacity-50',
          'aria-invalid:border-danger aria-invalid:ring-danger/30',
          className,
        )}
        {...props}
      />
    );
  },
);
