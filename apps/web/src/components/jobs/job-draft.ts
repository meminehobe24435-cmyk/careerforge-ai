/**
 * The input draft and what it becomes as a request.
 *
 * `POST /jobs/analyze` takes **the posting text** and nothing else that describes the job —
 * there is no `company` or `role` field in `AnalyzeJobRequest` (docs/API.md §2.6). The form
 * still offers both, because a poster's title block is often missing from a pasted excerpt and
 * the fields are the only way to supply it, so the rule is explicit and shown to the user:
 *
 * - a line is prepended **only when the posting text does not already contain that value**, so
 *   filling in a company the excerpt already names cannot degrade the parse by making the
 *   parser read a labelled header line as the role;
 * - the panel prints the lines it is about to add, so what is sent is never a surprise.
 *
 * The URL is a plain reference: it is stored with the analysis (`sourceUrl`) and **nothing is
 * fetched from it** — the field's label says exactly that.
 */

import { DEMO_JD_COMPANY, DEMO_JD_ROLE, DEMO_JD_TEXT } from '@/components/jobs/demo-jd';
import type { AnalyzeJobInput } from '@/lib/jobs-api';

export interface JobDraft {
  company: string;
  role: string;
  text: string;
  /** Stored with the analysis, never fetched. */
  sourceUrl: string;
}

export function emptyDraft(): JobDraft {
  return { company: '', role: '', text: '', sourceUrl: '' };
}

export function demoDraft(): JobDraft {
  return { company: DEMO_JD_COMPANY, role: DEMO_JD_ROLE, text: DEMO_JD_TEXT, sourceUrl: '' };
}

/**
 * The exact text that will be sent, given the draft.
 *
 * Exported because the panel prints the prepended lines and the tests assert the request body:
 * the composition rule is behaviour, not formatting.
 */
export function prependedHeaderLines(draft: JobDraft): string[] {
  const text = draft.text.trim().toLowerCase();
  const lines: string[] = [];
  const company = draft.company.trim();
  const role = draft.role.trim();
  if (company && !text.includes(company.toLowerCase())) lines.push(`公司：${company}`);
  if (role && !text.includes(role.toLowerCase())) lines.push(`岗位名称：${role}`);
  return lines;
}

export function composeJdText(draft: JobDraft): string {
  const body = draft.text.trim();
  const header = prependedHeaderLines(draft);
  return header.length > 0 ? `${header.join('\n')}\n${body}` : body;
}

/**
 * The request body.
 *
 * `source` is `url` only when a URL was given — that is what the field *is* (`paste | upload |
 * url | manual`), and it keeps the stored row honest about where the posting came from without
 * claiming anything was retrieved from it.
 */
export function draftToRequest(draft: JobDraft): AnalyzeJobInput {
  const url = draft.sourceUrl.trim();
  return {
    text: composeJdText(draft),
    source: url ? 'url' : 'paste',
    ...(url ? { sourceUrl: url } : {}),
  };
}

/** Whether there is enough to analyse: a posting, not just metadata. */
export function isDraftAnalysable(draft: JobDraft): boolean {
  return draft.text.trim().length > 0;
}
