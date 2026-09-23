import { clsx } from 'clsx';
import type { ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

/**
 * `cn()` — conditional classes (clsx) with Tailwind conflict resolution (tailwind-merge).
 * Every primitive in this package routes its `className` through it so callers can
 * override styles without fighting specificity.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
