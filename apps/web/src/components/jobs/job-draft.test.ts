import { describe, expect, it } from 'vitest';

import { DEMO_JD_TEXT } from '@/components/jobs/demo-jd';
import {
  composeJdText,
  demoDraft,
  draftToRequest,
  emptyDraft,
  isDraftAnalysable,
  prependedHeaderLines,
  type JobDraft,
} from '@/components/jobs/job-draft';

/**
 * The request the page actually sends.
 *
 * `POST /jobs/analyze` takes the posting text and nothing else that describes the job, so the
 * two fields the form offers have to become text. These assertions pin the rule down: a line is
 * added only when the posting does not already carry it — otherwise filling in a company the
 * excerpt already names would put a labelled header line in front of the title, and the parser
 * would read that line as the role (which is exactly what happened when the composition rule
 * was "always prepend", observed against the live API).
 */

function draftOf(overrides: Partial<JobDraft> = {}): JobDraft {
  return { ...emptyDraft(), ...overrides };
}

describe('composing the text sent for analysis', () => {
  it('sends the posting verbatim when the fields are empty', () => {
    const draft = draftOf({ text: '  嵌入式软件工程师\n岗位职责：…  ' });

    expect(prependedHeaderLines(draft)).toEqual([]);
    expect(composeJdText(draft)).toBe('嵌入式软件工程师\n岗位职责：…');
    expect(draftToRequest(draft)).toEqual({
      text: '嵌入式软件工程师\n岗位职责：…',
      source: 'paste',
    });
  });

  it('prepends a company and role the posting does not name', () => {
    const draft = draftOf({
      company: '某某智能科技',
      role: '嵌入式软件工程师',
      text: '岗位职责：写固件',
    });

    expect(prependedHeaderLines(draft)).toEqual([
      '公司：某某智能科技',
      '岗位名称：嵌入式软件工程师',
    ]);
    expect(
      composeJdText(draft).startsWith('公司：某某智能科技\n岗位名称：嵌入式软件工程师\n'),
    ).toBe(true);
  });

  it('adds nothing when the posting already carries the value', () => {
    const draft = demoDraft();

    expect(prependedHeaderLines(draft)).toEqual([]);
    // The demo posting is sent exactly as published, which is the text that was verified
    // against the live parser (role, company, location and 3 years all resolved from it).
    expect(composeJdText(draft)).toBe(DEMO_JD_TEXT);
    expect(draftToRequest(draft).text).toBe(DEMO_JD_TEXT);
  });

  it('records a URL as the source without claiming anything was fetched from it', () => {
    const draft = draftOf({ text: 'JD', sourceUrl: '  https://example.com/jobs/123  ' });

    expect(draftToRequest(draft)).toEqual({
      text: 'JD',
      source: 'url',
      sourceUrl: 'https://example.com/jobs/123',
    });
  });

  it('requires a posting, not just metadata', () => {
    expect(isDraftAnalysable(draftOf({ company: 'X', role: 'Y' }))).toBe(false);
    expect(isDraftAnalysable(draftOf({ text: '   ' }))).toBe(false);
    expect(isDraftAnalysable(draftOf({ text: 'JD' }))).toBe(true);
  });

  it('keeps a real Chinese posting behind the demo button', () => {
    // A demo that is a placeholder would make the page's own verification meaningless.
    expect(DEMO_JD_TEXT).toContain('任职要求');
    expect(DEMO_JD_TEXT).toContain('加分项');
    expect(DEMO_JD_TEXT).toContain('STM32');
    expect(DEMO_JD_TEXT.length).toBeGreaterThan(200);
  });
});
