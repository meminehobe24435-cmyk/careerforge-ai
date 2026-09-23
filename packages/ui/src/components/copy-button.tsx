'use client';

import { Check, Copy } from 'lucide-react';
import * as React from 'react';

import type { IconButtonProps } from './icon-button';
import { IconButton } from './icon-button';

async function writeToClipboard(text: string): Promise<boolean> {
  const nav = (globalThis as { navigator?: Navigator }).navigator;
  try {
    if (nav?.clipboard?.writeText) {
      await nav.clipboard.writeText(text);
      return true;
    }
  } catch {
    // Clipboard API blocked (insecure origin / permissions) — try the legacy path below.
  }

  try {
    const doc = (globalThis as { document?: Document }).document;
    if (!doc) return false;
    const helper = doc.createElement('textarea');
    helper.value = text;
    helper.setAttribute('readonly', '');
    helper.style.position = 'fixed';
    helper.style.top = '-1000px';
    helper.style.opacity = '0';
    doc.body.appendChild(helper);
    helper.select();
    const ok = doc.execCommand('copy');
    doc.body.removeChild(helper);
    return ok;
  } catch {
    return false;
  }
}

export interface CopyButtonProps {
  value: string;
  /** Accessible name when idle (default `复制`). */
  label?: string;
  /** Accessible name right after a successful copy (default `已复制`). */
  copiedLabel?: string;
  className?: string;
  size?: IconButtonProps['size'];
  variant?: IconButtonProps['variant'];
  /** Render the visible text label next to the icon (wide variant). */
  showLabel?: boolean;
  onCopied?: () => void;
  onFailed?: () => void;
}

export function CopyButton({
  value,
  label = '复制',
  copiedLabel = '已复制',
  className,
  size = 'sm',
  variant = 'ghost',
  showLabel = false,
  onCopied,
  onFailed,
}: CopyButtonProps) {
  const [copied, setCopied] = React.useState(false);
  const timer = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  React.useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  const handleCopy = React.useCallback(async () => {
    const ok = await writeToClipboard(value);
    if (!ok) {
      onFailed?.();
      return;
    }
    onCopied?.();
    setCopied(true);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setCopied(false), 1600);
  }, [onCopied, onFailed, value]);

  return (
    <IconButton
      type="button"
      size={size}
      variant={variant}
      aria-label={copied ? copiedLabel : label}
      onClick={handleCopy}
      className={className}
      data-copied={copied ? '' : undefined}
    >
      {copied ? <Check className="text-evidence size-3.5" /> : <Copy className="size-3.5" />}
      {showLabel ? <span className="ml-1 text-xs">{copied ? copiedLabel : label}</span> : null}
    </IconButton>
  );
}
