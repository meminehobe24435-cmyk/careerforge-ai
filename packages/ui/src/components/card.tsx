import * as React from 'react';

import { cn } from '../lib/cn';

export const Card = React.forwardRef<HTMLDivElement, React.ComponentProps<'div'>>(function Card(
  { className, ...props },
  ref,
) {
  return (
    <div
      ref={ref}
      className={cn('border-default bg-surface rounded-lg border', className)}
      {...props}
    />
  );
});

export const CardHeader = React.forwardRef<HTMLDivElement, React.ComponentProps<'div'>>(
  function CardHeader({ className, ...props }, ref) {
    return <div ref={ref} className={cn('flex flex-col gap-1 p-4 sm:p-5', className)} {...props} />;
  },
);

export const CardTitle = React.forwardRef<HTMLHeadingElement, React.ComponentProps<'h3'>>(
  function CardTitle({ className, ...props }, ref) {
    return (
      <h3
        ref={ref}
        className={cn('text-primary text-sm font-semibold tracking-tight', className)}
        {...props}
      />
    );
  },
);

export const CardDescription = React.forwardRef<HTMLParagraphElement, React.ComponentProps<'p'>>(
  function CardDescription({ className, ...props }, ref) {
    return <p ref={ref} className={cn('text-secondary text-xs', className)} {...props} />;
  },
);

export const CardContent = React.forwardRef<HTMLDivElement, React.ComponentProps<'div'>>(
  function CardContent({ className, ...props }, ref) {
    return <div ref={ref} className={cn('px-4 pb-4 sm:px-5 sm:pb-5', className)} {...props} />;
  },
);

export const CardFooter = React.forwardRef<HTMLDivElement, React.ComponentProps<'div'>>(
  function CardFooter({ className, ...props }, ref) {
    return (
      <div
        ref={ref}
        className={cn(
          'border-subtle flex flex-wrap items-center gap-2 border-t px-4 py-3 sm:px-5',
          className,
        )}
        {...props}
      />
    );
  },
);
