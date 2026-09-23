'use client';

import * as DropdownMenuPrimitive from '@radix-ui/react-dropdown-menu';
import * as React from 'react';

import { cn } from '../lib/cn';

export const DropdownMenu = DropdownMenuPrimitive.Root;
export const DropdownMenuTrigger = DropdownMenuPrimitive.Trigger;
export const DropdownMenuGroup = DropdownMenuPrimitive.Group;
export const DropdownMenuPortal = DropdownMenuPrimitive.Portal;

export const DropdownMenuContent = React.forwardRef<
  React.ComponentRef<typeof DropdownMenuPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Content>
>(function DropdownMenuContent({ className, sideOffset = 6, ...props }, ref) {
  return (
    <DropdownMenuPrimitive.Portal>
      <DropdownMenuPrimitive.Content
        ref={ref}
        sideOffset={sideOffset}
        className={cn(
          'z-[var(--z-modal)] min-w-44 max-w-[calc(100vw-1rem)] overflow-hidden rounded-md',
          'border-default bg-elevated border p-1 shadow-md',
          'data-[state=open]:animate-fade-in',
          className,
        )}
        {...props}
      />
    </DropdownMenuPrimitive.Portal>
  );
});

export const DropdownMenuItem = React.forwardRef<
  React.ComponentRef<typeof DropdownMenuPrimitive.Item>,
  React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Item> & { inset?: boolean }
>(function DropdownMenuItem({ className, inset = false, ...props }, ref) {
  return (
    <DropdownMenuPrimitive.Item
      ref={ref}
      className={cn(
        'relative flex cursor-default select-none items-center gap-2 rounded-sm px-2 py-1.5',
        'text-secondary text-sm outline-none',
        'ease-forge transition-colors duration-[var(--dur-fast)]',
        'data-[highlighted]:bg-hover data-[highlighted]:text-primary',
        'data-[disabled]:pointer-events-none data-[disabled]:opacity-50',
        '[&_svg]:size-3.5 [&_svg]:shrink-0',
        inset && 'pl-8',
        className,
      )}
      {...props}
    />
  );
});

export const DropdownMenuLabel = React.forwardRef<
  React.ComponentRef<typeof DropdownMenuPrimitive.Label>,
  React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Label>
>(function DropdownMenuLabel({ className, ...props }, ref) {
  return (
    <DropdownMenuPrimitive.Label
      ref={ref}
      className={cn(
        'text-tertiary px-2 py-1.5 font-mono text-[10px] uppercase tracking-wider',
        className,
      )}
      {...props}
    />
  );
});

export const DropdownMenuSeparator = React.forwardRef<
  React.ComponentRef<typeof DropdownMenuPrimitive.Separator>,
  React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Separator>
>(function DropdownMenuSeparator({ className, ...props }, ref) {
  return (
    <DropdownMenuPrimitive.Separator
      ref={ref}
      className={cn('bg-subtle -mx-1 my-1 h-px', className)}
      {...props}
    />
  );
});

/** Right-aligned mono hint (e.g. a shortcut or a value). */
export function DropdownMenuShortcut({ className, ...props }: React.ComponentProps<'span'>) {
  return (
    <span
      className={cn('text-tertiary ml-auto font-mono text-[10px] tracking-wider', className)}
      {...props}
    />
  );
}
