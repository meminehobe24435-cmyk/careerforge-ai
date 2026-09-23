import { LoaderCircle } from 'lucide-react';
import * as React from 'react';

import { cn } from '../lib/cn';

const sizeClasses = {
  sm: 'size-3.5',
  md: 'size-4',
  lg: 'size-5',
} as const;

export interface SpinnerProps extends React.SVGProps<SVGSVGElement> {
  size?: keyof typeof sizeClasses;
  /** When provided, the spinner becomes a live region for screen readers. */
  label?: string;
}

export function Spinner({ size = 'md', label, className, ...props }: SpinnerProps) {
  const icon = (
    <LoaderCircle
      aria-hidden="true"
      className={cn('animate-spin', sizeClasses[size], className)}
      {...props}
    />
  );

  if (!label) {
    return (
      <span role="presentation" aria-hidden="true" className="inline-flex items-center">
        {icon}
      </span>
    );
  }

  return (
    <span role="status" className="inline-flex items-center gap-2">
      {icon}
      <span className="sr-only">{label}</span>
    </span>
  );
}
