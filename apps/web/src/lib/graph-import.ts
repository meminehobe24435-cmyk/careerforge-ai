import { ApiError } from '@careerforge/shared';

import { api } from './api';
import { invalidResponse, isImportOutcome, isRecord, type ImportOutcome } from './graph-api';

/**
 * The write half of the evidence graph: pasted text in, real evidence rows out.
 *
 * Split from `graph-api.ts` because it is a *sequence* rather than a read: profile extraction, an
 * upload, a queued parse task and a synchronous analysis, in the one order the API accepts
 * (`apps/api/tests/test_public.py::_resume_ready`). Four steps with their own failure modes do not
 * belong in the same file as five guarded GETs.
 */

/* ── the import pipeline the empty state offers ────────────────────────────── */

export async function importProfileText(text: string): Promise<ImportOutcome> {
  const data = await api.post<unknown>('/profile/import', { text });
  if (!isImportOutcome(data)) {
    throw invalidResponse('POST /profile/import', '缺少 counts/warnings', data);
  }
  return data;
}

interface TaskState {
  status: string;
  stage: string | null;
  progress: number;
  error: string | null;
}

export async function fetchTask(taskId: string): Promise<TaskState> {
  const data = await api.get<unknown>(`/tasks/${encodeURIComponent(taskId)}`);
  if (!isRecord(data) || typeof data['status'] !== 'string') {
    throw invalidResponse('GET /tasks/{id}', '缺少 status', data);
  }
  return {
    status: data['status'],
    stage: typeof data['stage'] === 'string' ? data['stage'] : null,
    progress: typeof data['progress'] === 'number' ? data['progress'] : 0,
    error: typeof data['error'] === 'string' ? data['error'] : null,
  };
}

interface UploadAccepted {
  taskId: string | null;
  documentId: string;
  status: string;
  deduplicated: boolean;
}

async function uploadTextDocument(text: string, filename: string): Promise<UploadAccepted> {
  const form = new FormData();
  form.set('file', new File([text], filename, { type: 'text/plain' }));
  form.set('kind', 'resume');
  const data = await api.request<unknown>('/documents', { method: 'POST', body: form });
  if (
    !isRecord(data) ||
    typeof data['documentId'] !== 'string' ||
    (data['taskId'] !== null && typeof data['taskId'] !== 'string')
  ) {
    throw invalidResponse('POST /documents', '缺少 documentId/taskId', data);
  }
  return {
    taskId: (data['taskId'] as string | null) ?? null,
    documentId: data['documentId'],
    status: typeof data['status'] === 'string' ? data['status'] : 'unknown',
    deduplicated: data['deduplicated'] === true,
  };
}

export interface AnalyzeOutcome {
  evidenceCreated: number;
  evidenceUpdated: number;
  linksWritten: number;
  skillCount: number;
  nodeCount: number;
  edgeCount: number;
  warnings: string[];
}

export async function analyzeDocument(documentId: string): Promise<AnalyzeOutcome> {
  const data = await api.post<unknown>(
    `/documents/${encodeURIComponent(documentId)}/analyze`,
    undefined,
  );
  if (!isRecord(data) || typeof data['evidenceCreated'] !== 'number') {
    throw invalidResponse('POST /documents/{id}/analyze', '缺少 evidenceCreated', data);
  }
  return {
    evidenceCreated: data['evidenceCreated'] as number,
    evidenceUpdated: typeof data['evidenceUpdated'] === 'number' ? data['evidenceUpdated'] : 0,
    linksWritten: typeof data['linksWritten'] === 'number' ? data['linksWritten'] : 0,
    skillCount: typeof data['skillCount'] === 'number' ? data['skillCount'] : 0,
    nodeCount: typeof data['nodeCount'] === 'number' ? data['nodeCount'] : 0,
    edgeCount: typeof data['edgeCount'] === 'number' ? data['edgeCount'] : 0,
    warnings: Array.isArray(data['warnings']) ? (data['warnings'] as string[]) : [],
  };
}

export interface ImportProgress {
  step: 'profile' | 'upload' | 'parse' | 'analyze';
  detail: string;
}

/**
 * Paste or drop text in, get a graph out: profile extraction, a stored document, the parse task,
 * then the synchronous analysis that writes evidence, skills and links.
 *
 * This is the same order `apps/api/tests/test_public.py::_resume_ready` uses, because it is the
 * only order the API accepts: the analysis reads chunks that the parse task has to have written
 * first, and the profile entities have to exist before the builder can attach them.
 */
export async function importEvidenceSource(
  text: string,
  options: { filename?: string; onProgress?: (update: ImportProgress) => void } = {},
): Promise<{ profile: ImportOutcome; documentId: string; analysis: AnalyzeOutcome }> {
  const onProgress = options.onProgress ?? (() => {});
  const filename = options.filename ?? 'resume.txt';

  onProgress({ step: 'profile', detail: 'Extracting profile entities' });
  const profile = await importProfileText(text);

  onProgress({ step: 'upload', detail: 'Uploading document' });
  const upload = await uploadTextDocument(text, filename);

  onProgress({ step: 'parse', detail: 'Waiting for the parse task' });
  if (upload.taskId) {
    for (let attempt = 0; attempt < 150; attempt += 1) {
      const task = await fetchTask(upload.taskId);
      if (task.status === 'succeeded') break;
      if (task.status === 'failed' || task.status === 'cancelled') {
        throw new ApiError({
          code: 'TASK_FAILED',
          message: task.error ?? '文档解析任务失败，证据无法构建',
          status: 200,
        });
      }
      onProgress({
        step: 'parse',
        detail: `Parsing${task.stage ? ` · ${task.stage}` : ''} · ${task.progress}%`,
      });
      await new Promise((resolve) => setTimeout(resolve, 400));
    }
  }

  onProgress({ step: 'analyze', detail: 'Building evidence and skill links' });
  const analysis = await analyzeDocument(upload.documentId);
  return { profile, documentId: upload.documentId, analysis };
}
