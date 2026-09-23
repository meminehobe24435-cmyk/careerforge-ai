'use client';

import * as TooltipPrimitive from '@radix-ui/react-tooltip';
import * as React from 'react';

import { cn } from '../lib/cn';

export const TooltipProvider = TooltipPrimitive.Provider;
export const TooltipTrigger = TooltipPrimitive.Trigger;

export const TooltipContent = React.forwardRef<
  React.ComponentRef<typeof TooltipPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof TooltipPrimitive.Content>
>(function TooltipContent({ className, sideOffset = 6, ...props }, ref) {
  return (
    <TooltipPrimitive.Content
      ref={ref}
      sideOffset={sideOffset}
      className={cn(
        'border-default bg-elevated z-[var(--z-modal)] max-w-xs rounded-md border px-2 py-1',
        'text-primary text-xs leading-relaxed shadow-md',
        'data-[state=delayed-open]:animate-fade-in',
        className,
      )}
      {...props}
    />
  );
});

export interface TooltipProps {
  /** Tooltip body. Keep it to one sentence — it explains a metric, it does not document. */
  content: React.ReactNode;
  /** Single element that becomes the trigger (ref-forwarding). */
  children: React.ReactNode;
  side?: 'top' | 'right' | 'bottom' | 'left';
  align?: 'start' | 'center' | 'end';
  delayDuration?: number;
  className?: string;
}

/**
 * Tooltip — used for metric definitions (`口径`) and for labelling icon-only controls
 * in the collapsed sidebar. Hover is never the only path: every trigger also carries an
 * accessible name (`aria-label`) on its own.
 */
export function Tooltip({
  content,
  children,
  side = 'top',
  align = 'center',
  delayDuration = 150,
  className,
}: TooltipProps) {
  return (
    <TooltipProvider delayDuration={delayDuration} skipDelayDuration={300}>
      <TooltipPrimitive.Root>
        <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
        <TooltipPrimitive.Portal>
          <TooltipContent side={side} align={align} className={className}>
            {content}
          </TooltipContent>
        </TooltipPrimitive.Portal>
      </TooltipPrimitive.Root>
    </TooltipProvider>
  );
}
