import * as React from 'react';

import { cn } from '../lib/cn';
import { CopyButton } from './copy-button';

export interface CodeBlockProps extends React.ComponentProps<'div'> {
  code: string;
  /** Purely informational label (e.g. `json`, `bash`) — no syntax highlighting yet. */
  language?: string;
  /** File path shown in the header, mono + tabular (docs/UI.md §2.2). */
  filename?: string;
  maxHeight?: number | string;
  copyable?: boolean;
}

/**
 * CodeBlock — mono panel for hashes, paths, payloads and commands, with a copy affordance.
 * No syntax highlighting in PHASE 1 (that lands with the Evidence Drawer work).
 */
export function CodeBlock({
  code,
  language,
  filename,
  maxHeight = 320,
  copyable = true,
  className,
  ...props
}: CodeBlockProps) {
  const hasHeader = Boolean(filename || language || copyable);

  return (
    <div
      className={cn('border-default bg-base overflow-hidden rounded-lg border', className)}
      {...props}
    >
      {hasHeader ? (
        <div className="border-subtle bg-surface flex items-center justify-between gap-2 border-b px-3 py-1.5">
          <span className="text-tertiary truncate font-mono text-[11px] tabular-nums">
            {filename ?? language ?? 'output'}
          </span>
          <div className="flex items-center gap-1">
            {filename && language ? (
              <span className="text-tertiary font-mono text-[11px]">{language}</span>
            ) : null}
            {copyable ? <CopyButton value={code} label="复制内容" /> : null}
          </div>
        </div>
      ) : null}
      <pre
        className="text-secondary overflow-auto p-3 font-mono text-xs leading-relaxed"
        style={{ maxHeight }}
      >
        <code>{code}</code>
      </pre>
    </div>
  );
}
