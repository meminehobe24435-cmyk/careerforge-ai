'use client';

import * as DialogPrimitive from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import * as React from 'react';

import { cn } from '../lib/cn';
import { IconButton } from './icon-button';

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;
export const DialogClose = DialogPrimitive.Close;
export const DialogPortal = DialogPrimitive.Portal;

export const DialogOverlay = React.forwardRef<
  React.ComponentRef<typeof DialogPrimitive.Overlay>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Overlay>
>(function DialogOverlay({ className, ...props }, ref) {
  return (
    <DialogPrimitive.Overlay
      ref={ref}
      className={cn('bg-overlay fixed inset-0 z-[var(--z-modal)]', className)}
      {...props}
    />
  );
});

export interface DialogContentProps extends React.ComponentPropsWithoutRef<
  typeof DialogPrimitive.Content
> {
  /** Hide the built-in close button (e.g. for a command palette with its own footer). */
  hideClose?: boolean;
  /**
   * Styling for the backdrop. Needed when the content is not a modal but a *drawer*: a drawer lives
   * on a lower layer than a dialog (`--z-drawer` < `--z-modal`), and if only the content is moved
   * down, the overlay is left on top of it — swallowing every tap. PHASE 12's mobile end-to-end run
   * is what caught that (`apps/web/e2e/dashboard.spec.ts`, 375 px: the drawer was unclickable).
   */
  overlayClassName?: string;
  overlayStyle?: React.CSSProperties;
}

export const DialogContent = React.forwardRef<
  React.ComponentRef<typeof DialogPrimitive.Content>,
  DialogContentProps
>(function DialogContent(
  { className, children, hideClose = false, overlayClassName, overlayStyle, ...props },
  ref,
) {
  return (
    <DialogPortal>
      <DialogOverlay className={overlayClassName} style={overlayStyle} />
      <DialogPrimitive.Content
        ref={ref}
        className={cn(
          'fixed left-1/2 top-1/2 z-[var(--z-modal)] flex max-h-[min(88dvh,760px)] -translate-x-1/2 -translate-y-1/2 flex-col',
          'border-default bg-elevated w-[calc(100vw-2rem)] max-w-lg overflow-hidden rounded-lg border shadow-lg',
          'data-[state=open]:animate-dialog-in outline-none',
          className,
        )}
        {...props}
      >
        {children}
        {hideClose ? null : (
          <DialogPrimitive.Close asChild>
            <IconButton aria-label="关闭对话框" className="absolute right-3 top-3">
              <X className="size-4" />
            </IconButton>
          </DialogPrimitive.Close>
        )}
      </DialogPrimitive.Content>
    </DialogPortal>
  );
});

export function DialogHeader({ className, ...props }: React.ComponentProps<'div'>) {
  return <div className={cn('flex flex-col gap-1.5 p-5 pb-0', className)} {...props} />;
}

export const DialogTitle = React.forwardRef<
  React.ComponentRef<typeof DialogPrimitive.Title>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Title>
>(function DialogTitle({ className, ...props }, ref) {
  return (
    <DialogPrimitive.Title
      ref={ref}
      className={cn('text-primary text-base font-semibold tracking-tight', className)}
      {...props}
    />
  );
});

export const DialogDescription = React.forwardRef<
  React.ComponentRef<typeof DialogPrimitive.Description>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Description>
>(function DialogDescription({ className, ...props }, ref) {
  return (
    <DialogPrimitive.Description
      ref={ref}
      className={cn('text-secondary text-xs leading-relaxed', className)}
      {...props}
    />
  );
});

export function DialogBody({ className, ...props }: React.ComponentProps<'div'>) {
  return <div className={cn('min-h-0 flex-1 overflow-y-auto p-5', className)} {...props} />;
}

export function DialogFooter({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <div
      className={cn(
        'border-subtle flex flex-wrap items-center justify-end gap-2 border-t px-5 py-3',
        className,
      )}
      {...props}
    />
  );
}
