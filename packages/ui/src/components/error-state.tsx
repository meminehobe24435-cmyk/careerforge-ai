'use client';

import { RefreshCw, TriangleAlert } from 'lucide-react';
import * as React from 'react';

import { cn } from '../lib/cn';
import { Button } from './button';
import { CopyButton } from './copy-button';

interface NormalisedError {
  code: string | null;
  message: string | null;
  requestId: string | null;
}

/**
 * Duck-typed unwrapping of anything error-shaped (`ApiError`, `Error`, a raw payload).
 * Keeps `@careerforge/ui` free of a dependency on `@careerforge/shared`.
 */
function normaliseError(error: unknown): NormalisedError {
  if (error === null || error === undefined) {
    return { code: null, message: null, requestId: null };
  }
  if (typeof error === 'object') {
    const record = error as Record<string, unknown>;
    const code = typeof record['code'] === 'string' ? record['code'] : null;
    const message = typeof record['message'] === 'string' ? record['message'] : null;
    const requestId = typeof record['requestId'] === 'string' ? record['requestId'] : null;
    return { code, message, requestId };
  }
  if (typeof error === 'string') return { code: null, message: error, requestId: null };
  return { code: null, message: null, requestId: null };
}

export interface ErrorStateProps extends Omit<React.ComponentProps<'div'>, 'title'> {
  title?: string;
  /** Raw error — `code` / `message` / `requestId` are read off it when present. */
  error?: unknown;
  code?: string | null;
  message?: string | null;
  requestId?: string | null;
  onRetry?: () => void;
  retryLabel?: string;
  retrying?: boolean;
  /** Extra content, e.g. the API base URL or a link to `/system`. */
  details?: React.ReactNode;
  /** Renders a mono “查看状态页” link (docs/UI.md §6.1). */
  statusHref?: string;
}

/**
 * ErrorState — code + human sentence + retry + copyable `requestId`
 * (docs/UI.md §6.1). Never renders fabricated data next to a failure.
 */
export function ErrorState({
  title = '加载失败',
  error,
  code,
  message,
  requestId,
  onRetry,
  retryLabel = '重试',
  retrying = false,
  details,
  statusHref,
  className,
  ...props
}: ErrorStateProps) {
  const normalised = normaliseError(error);
  const resolvedCode = code ?? normalised.code;
  const resolvedMessage = message ?? normalised.message;
  const resolvedRequestId = requestId ?? normalised.requestId;

  return (
    <div
      role="alert"
      className={cn(
        'border-danger/30 bg-surface flex flex-col gap-3 rounded-lg border p-4 sm:p-5',
        className,
      )}
      {...props}
    >
      <div className="flex items-start gap-3">
        <span
          aria-hidden="true"
          className="border-danger/30 bg-danger/10 text-danger mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-md border"
        >
          <TriangleAlert className="size-4" />
        </span>
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <p className="text-primary text-sm font-semibold">{title}</p>
          <p className="text-secondary text-xs leading-relaxed">
            {resolvedMessage ?? '请求未能完成，请稍后重试。'}
          </p>
        </div>
      </div>

      {resolvedCode || resolvedRequestId ? (
        <dl className="border-subtle bg-base flex flex-wrap items-center gap-x-4 gap-y-2 rounded-md border px-3 py-2">
          {resolvedCode ? (
            <div className="flex items-center gap-2">
              <dt className="text-tertiary font-mono text-[11px] uppercase tracking-wide">code</dt>
              <dd className="text-danger font-mono text-[11px] tabular-nums">{resolvedCode}</dd>
            </div>
          ) : null}
          {resolvedRequestId ? (
            <div className="flex min-w-0 items-center gap-2">
              <dt className="text-tertiary font-mono text-[11px] uppercase tracking-wide">
                requestId
              </dt>
              <dd className="text-secondary truncate font-mono text-[11px] tabular-nums">
                {resolvedRequestId}
              </dd>
              <CopyButton value={resolvedRequestId} label="复制 requestId" />
            </div>
          ) : null}
        </dl>
      ) : null}

      {details ? <div className="text-secondary text-xs">{details}</div> : null}

      <div className="flex flex-wrap items-center gap-2">
        {onRetry ? (
          <Button variant="secondary" size="sm" onClick={onRetry} loading={retrying}>
            <RefreshCw className="size-3.5" aria-hidden="true" />
            {retryLabel}
          </Button>
        ) : null}
        {statusHref ? (
          <a
            href={statusHref}
            className="text-signal focus-visible:outline-brand rounded-sm font-mono text-[11px] underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2"
          >
            查看状态页 →
          </a>
        ) : null}
      </div>
    </div>
  );
}
