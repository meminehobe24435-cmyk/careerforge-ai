import * as React from 'react';

import { cn } from '../lib/cn';

export const Label = React.forwardRef<HTMLLabelElement, React.ComponentProps<'label'>>(
  function Label({ className, ...props }, ref) {
    return (
      <label ref={ref} className={cn('text-secondary text-xs font-medium', className)} {...props} />
    );
  },
);
