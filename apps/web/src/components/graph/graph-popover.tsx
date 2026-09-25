'use client';

import { Button, cn } from '@careerforge/ui';
import { useEffect, useId, useRef, useState } from 'react';
import type { ReactNode } from 'react';

/**
 * A non-modal popover: a button that discloses a panel.
 *
 * The brief asks for a **popover, not a modal tour**, and `@careerforge/ui` ships no popover
 * primitive, so this is the smallest correct one rather than a `Dialog` pretending to be one:
 *
 * * the trigger is a real `<button>` with `aria-expanded` and `aria-controls`;
 * * the panel is `role="dialog"` with a name, so a screen reader announces what opened;
 * * Escape closes it and returns focus to the trigger; a click outside closes it;
 * * it is **not** modal — the canvas and the node list stay reachable behind it, which is the
 *   whole point of "how to read this graph" (you read it *while* looking at the graph).
 */
export interface GraphPopoverProps {
  /** Accessible name of the trigger *and* of the panel it opens. */
  label: string;
  /** Trigger contents; the label is used when `showLabel` is false. */
  children: ReactNode;
  icon?: ReactNode;
  showLabel?: boolean;
  /** Passed to the trigger button. */
  triggerClassName?: string;
  align?: 'left' | 'right';
  panelClassName?: string;
  /** Rendered at the top of the panel. */
  title?: string;
}

export function GraphPopover({
  label,
  children,
  icon,
  showLabel = true,
  triggerClassName,
  align = 'right',
  panelClassName,
  title,
}: GraphPopoverProps) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent): void => {
      const target = event.target as Node | null;
      if (!target) return;
      if (panelRef.current?.contains(target) || triggerRef.current?.contains(target)) return;
      setOpen(false);
    };
    document.addEventListener('mousedown', onPointerDown);
    return () => document.removeEventListener('mousedown', onPointerDown);
  }, [open]);

  return (
    <div className="relative">
      <Button
        ref={triggerRef}
        variant="ghost"
        size="sm"
        aria-label={showLabel ? undefined : label}
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        aria-haspopup="dialog"
        onClick={() => setOpen((value) => !value)}
        className={cn('gap-1.5', triggerClassName)}
      >
        {icon}
        {showLabel ? label : null}
      </Button>

      {open ? (
        <div
          ref={panelRef}
          id={panelId}
          role="dialog"
          aria-label={label}
          // React's synthetic preventDefault also marks the native event, and the drawer's window
          // listener skips a default-prevented Escape — so Escape closes the popover, not both.
          onKeyDown={(event) => {
            if (event.key !== 'Escape') return;
            event.preventDefault();
            event.stopPropagation();
            setOpen(false);
            triggerRef.current?.focus();
          }}
          className={cn(
            'border-default bg-elevated absolute top-[calc(100%+6px)] z-[var(--z-palette)]',
            'max-h-[70dvh] w-[min(92vw,32rem)] overflow-y-auto rounded-lg border p-3 shadow-lg',
            align === 'right' ? 'right-0' : 'left-0',
            panelClassName,
          )}
        >
          {title ? (
            <p className="text-secondary mb-2 font-mono text-[10px] uppercase tracking-[0.14em]">
              {title}
            </p>
          ) : null}
          {children}
        </div>
      ) : null}
    </div>
  );
}
