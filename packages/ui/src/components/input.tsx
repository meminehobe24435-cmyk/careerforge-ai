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
          'focus-visible:border-brand focus-visible:ring-brand/40 focus-visible:outline-none focus-visible:ring-2',
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
