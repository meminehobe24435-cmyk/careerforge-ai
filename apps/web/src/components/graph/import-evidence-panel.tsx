'use client';

import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Input,
  Label,
  Textarea,
} from '@careerforge/ui';
import { FileUp } from 'lucide-react';
import { useState } from 'react';

import { useImportEvidenceSource } from '@/hooks/use-evidence-graph';
import { API_BASE_URL } from '@/lib/api';
import { isApiError } from '@careerforge/shared';

/**
 * The action the empty state offers, and the same panel is reachable while the graph has content.
 *
 * "Import a profile" is a promise the page has to keep, and there is no profile page in the app
 * yet — so this runs the pipeline the API actually exposes, in the order it accepts it:
 * `POST /profile/import`, then `POST /documents`, then the parse task, then
 * `POST /documents/{id}/analyze` (the sequence `apps/api/tests/test_public.py` uses). The result
 * is a populated graph, not a dead end pointing at a route that does not exist.
 *
 * Nothing is retried silently and nothing is invented on failure: the error the API returned is
 * printed with its code, because a half-imported profile behind a green toast is worse than a
 * visible failure.
 */
export function ImportEvidencePanel({
  onImported,
  defaultOpen = false,
}: {
  onImported?: () => void;
  defaultOpen?: boolean;
}) {
  const [text, setText] = useState('');
  const [filename, setFilename] = useState('resume.txt');
  const [progress, setProgress] = useState<string | null>(null);
  const [open, setOpen] = useState<boolean>(defaultOpen || true);
  const importSource = useImportEvidenceSource();

  const apiError = isApiError(importSource.error) ? importSource.error : null;
  const result = importSource.data;

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-2">
        <CardTitle className="flex items-center gap-2 text-xs">
          <FileUp className="size-3.5" aria-hidden="true" />
          Import a profile to build evidence
        </CardTitle>
        <Button size="sm" variant="ghost" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
          {open ? 'Hide' : 'Show'}
        </Button>
      </CardHeader>
      {open ? (
        <CardContent className="flex flex-col gap-3">
          <p className="text-tertiary text-[11px] leading-relaxed">
            Paste resume or project text. The page extracts profile entities, stores the text as a
            document, waits for the parse task and analyses it — then the evidence, skill links and
            confidence behind them are real rows you can open on the canvas.
          </p>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="import-filename">File name recorded with the document</Label>
            <Input
              id="import-filename"
              value={filename}
              onChange={(event) => setFilename(event.target.value)}
              className="max-w-xs"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="import-text">Profile text</Label>
            <Textarea
              id="import-text"
              value={text}
              rows={8}
              placeholder={
                '教育经历\n某某大学 电子信息工程 本科 2019-2023\n\n项目经历\n平衡小车 2022\n基于 STM32 的 PID 平衡控制，使用 FreeRTOS 任务调度与 CAN 通信。'
              }
              onChange={(event) => setText(event.target.value)}
              className="font-mono text-[11px]"
            />
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              loading={importSource.isPending}
              disabled={text.trim().length === 0}
              onClick={() => {
                setProgress('Starting');
                importSource.mutate(
                  {
                    text,
                    filename: filename.trim() || 'resume.txt',
                    onProgress: (update) => setProgress(update.detail),
                  },
                  {
                    onSuccess: () => {
                      setProgress(null);
                      onImported?.();
                    },
                    onError: () => setProgress(null),
                  },
                );
              }}
            >
              Import and analyse
            </Button>
            <span className="text-tertiary font-mono text-[10px]">
              POST {API_BASE_URL}/profile/import → /documents → /documents/{'{id}'}/analyze
            </span>
          </div>

          {importSource.isPending && progress ? (
            <p role="status" className="text-secondary text-[11px]">
              {progress}…
            </p>
          ) : null}

          {result ? (
            <div role="status" className="border-evidence/30 bg-evidence/5 rounded-md border p-3">
              <p className="text-primary text-[11px] font-medium">Evidence built</p>
              <ul className="text-secondary mt-1 flex flex-col gap-0.5 font-mono text-[11px] tabular-nums">
                <li>
                  profile: {result.profile.counts['projects'] ?? 0} projects ·{' '}
                  {result.profile.counts['experiences'] ?? 0} experiences ·{' '}
                  {result.profile.counts['skills'] ?? 0} skills
                </li>
                <li>
                  analysis: {result.analysis.evidenceCreated} evidence created ·{' '}
                  {result.analysis.linksWritten} links written · {result.analysis.skillCount} skills
                  linked
                </li>
              </ul>
              {result.profile.unmappedSkills.length > 0 ? (
                <p className="text-weak mt-1 text-[11px]">
                  The taxonomy did not resolve:{' '}
                  <span className="font-mono">{result.profile.unmappedSkills.join(', ')}</span>. A
                  declaration that cannot be joined to the graph is a declaration nothing can check.
                </p>
              ) : null}
            </div>
          ) : null}

          {apiError ? (
            <div role="alert" className="border-danger/30 bg-surface rounded-md border p-3">
              <p className="text-primary text-[11px] font-medium">
                Import failed — {apiError.code}
              </p>
              <p className="text-secondary mt-0.5 text-[11px]">{apiError.message}</p>
            </div>
          ) : null}
        </CardContent>
      ) : null}
    </Card>
  );
}
