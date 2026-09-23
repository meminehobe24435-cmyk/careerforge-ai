import * as React from 'react';

import { cn } from '../lib/cn';

export const Skeleton = React.forwardRef<HTMLDivElement, React.ComponentProps<'div'>>(
  function Skeleton({ className, ...props }, ref) {
    return (
      <div
        ref={ref}
        aria-hidden="true"
        className={cn('bg-hover animate-pulse rounded-md', className)}
        {...props}
      />
    );
  },
);

/**
 * `SkeletonText` — n lines of skeleton copy. Loading UI must mirror the real layout
 * (docs/UI.md §6.1), so the last line is shortened to fake a paragraph, not a block.
 */
export function SkeletonText({ lines = 3, className }: { lines?: number; className?: string }) {
  return (
    <div className={cn('flex flex-col gap-2', className)}>
      {Array.from({ length: lines }).map((_, index) => (
        <Skeleton key={index} className={cn('h-3', index === lines - 1 ? 'w-2/3' : 'w-full')} />
      ))}
    </div>
  );
}
