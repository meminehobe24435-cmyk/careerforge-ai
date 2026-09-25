'use client';

import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Input,
  Kbd,
  Textarea,
} from '@careerforge/ui';
import { Eraser, FileText, Play, Wand2 } from 'lucide-react';

import { prependedHeaderLines, type JobDraft } from '@/components/jobs/job-draft';

export interface JdInputPanelProps {
  draft: JobDraft;
  onChange: (patch: Partial<JobDraft>) => void;
  onAnalyze: () => void;
  onLoadDemo: () => void;
  onClear: () => void;
  /** A request is in flight — the primary action is disabled and says so. */
  busy: boolean;
}

/**
 * The input half of the split layout: company, role, the posting text and an optional URL.
 *
 * Two disclosures matter more than the fields themselves:
 *
 * 1. **the URL is a reference, not a fetch.** Nothing is retrieved from it; the label and the
 *    hint say so, because a URL box next to an "Analyze" button otherwise promises a scrape
 *    that this API does not do;
 * 2. **company and role become part of the text.** The API parses the posting text and takes no
 *    separate fields, so the panel prints the exact lines it prepends. The rule is in
 *    `job-draft.ts`; here it is only shown.
 *
 * Every control is labelled, the primary action is reachable with ⌘/Ctrl + Enter, and the
 * layout stacks below `lg` (docs/UI.md §10).
 */
export function JdInputPanel({
  draft,
  onChange,
  onAnalyze,
  onLoadDemo,
  onClear,
  busy,
}: JdInputPanelProps) {
  const prepended = prependedHeaderLines(draft);
  const analysable = draft.text.trim().length > 0;

  return (
    <Card className="min-w-0">
      <CardHeader className="flex-row items-center justify-between gap-2">
        <CardTitle className="flex items-center gap-1.5">
          <FileText className="size-3.5" aria-hidden="true" />
          Job description
        </CardTitle>
        <span className="text-tertiary font-mono text-[11px] tabular-nums">POST /jobs/analyze</span>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="flex min-w-0 flex-col gap-1">
            <span className="text-tertiary text-[11px]">Company</span>
            <Input
              value={draft.company}
              onChange={(event) => onChange({ company: event.target.value })}
              placeholder="例如 某某智能科技"
              autoComplete="off"
            />
          </label>
          <label className="flex min-w-0 flex-col gap-1">
            <span className="text-tertiary text-[11px]">Role</span>
            <Input
              value={draft.role}
              onChange={(event) => onChange({ role: event.target.value })}
              placeholder="例如 嵌入式软件工程师"
              autoComplete="off"
            />
          </label>
        </div>

        {prepended.length > 0 ? (
          // Printed because these lines go into the request body, and a field that silently
          // rewrites what you paste is the kind of thing a user should never have to discover.
          <p className="text-tertiary text-[11px] leading-relaxed">
            会加在文本开头的行（原文里已包含时不会重复添加）：
            <span className="text-secondary font-mono">{prepended.join(' · ')}</span>
          </p>
        ) : null}

        <label className="flex flex-col gap-1">
          <span className="text-tertiary text-[11px]">JD text</span>
          <Textarea
            value={draft.text}
            onChange={(event) => onChange({ text: event.target.value })}
            onKeyDown={(event) => {
              if (
                (event.metaKey || event.ctrlKey) &&
                event.key === 'Enter' &&
                analysable &&
                !busy
              ) {
                event.preventDefault();
                onAnalyze();
              }
            }}
            rows={14}
            placeholder="把岗位描述原文粘贴到这里（含岗位职责与任职要求）"
            spellCheck={false}
            className="min-h-48 font-mono text-[12px] leading-relaxed"
            aria-describedby="jd-text-hint"
          />
        </label>

        <p id="jd-text-hint" className="text-tertiary text-[11px] leading-relaxed">
          {draft.text.trim().length} 字符 · 解析在同一段文本上进行，解析结果按文本去重：
          再次提交同一段文本会更新同一条岗位，而不是新建。
        </p>

        <label className="flex flex-col gap-1">
          <span className="text-tertiary text-[11px]">Job URL（可选）</span>
          <Input
            value={draft.sourceUrl}
            onChange={(event) => onChange({ sourceUrl: event.target.value })}
            placeholder="https://example.com/jobs/123"
            inputMode="url"
            autoComplete="off"
            aria-describedby="jd-url-hint"
          />
        </label>
        <p id="jd-url-hint" className="text-tertiary text-[11px] leading-relaxed">
          只作为来源记录随分析一起保存（<span className="font-mono">sourceUrl</span>）。 系统
          <b className="font-medium">不会</b>访问这个地址，也不会抓取任何内容——
          解析用的始终是上面的文本。
        </p>

        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={onAnalyze} disabled={!analysable} loading={busy}>
            <Play className="size-3.5" aria-hidden="true" />
            Analyze
          </Button>
          <Button variant="secondary" onClick={onLoadDemo} disabled={busy}>
            <Wand2 className="size-3.5" aria-hidden="true" />
            Load Demo JD
          </Button>
          <Button variant="ghost" onClick={onClear} disabled={busy}>
            <Eraser className="size-3.5" aria-hidden="true" />
            Clear
          </Button>
          <span className="text-tertiary ml-auto hidden items-center gap-1 text-[11px] sm:flex">
            <Kbd>⌘</Kbd>
            <Kbd>⏎</Kbd>
          </span>
        </div>
      </CardContent>
    </Card>
  );
}
