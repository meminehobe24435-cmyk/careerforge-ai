import type { EvidenceGraphNode, EvidenceItem, EvidenceLocator } from '@/lib/graph-api';

import { nodeStyle } from './graph-node-style';

/**
 * Evidence presentation: what a locator, an excerpt and an authority tier actually say.
 *
 * Split from `graph-model.ts` so each half stays reviewable in one sitting — the model answers
 * *what is connected to what*, and this answers *what this item means*.
 */

/* ── evidence detail presentation ─────────────────────────────────────────── */

/**
 * Authority tier per evidence kind, mirroring `careerforge_ai.scoring.confidence::_KIND_AUTHORITY`.
 *
 * Mirrored rather than fetched because the API returns the tier as a *number* on the factors
 * (`sourceAuthority: 0.8`), and a screen that has to say what that number means needs the same
 * table the scorer used. If the backend map changes, this one has to change with it — the
 * `graph-model.test.ts` case that pins the five scores is what catches that.
 */
export const AUTHORITY_TIERS: Record<string, { tier: string; score: number; note: string }> = {
  repo_file: {
    tier: 'code_or_commit',
    score: 1.0,
    note: 'Source code and commits are the highest-authority tier: a reviewer can open the file and check the line.',
  },
  commit: {
    tier: 'code_or_commit',
    score: 1.0,
    note: 'Source code and commits are the highest-authority tier: a reviewer can check the commit and its diff.',
  },
  readme: {
    tier: 'readme',
    score: 0.85,
    note: 'A README is written by the author to describe their own work, so it outranks a résumé but not the code.',
  },
  document_chunk: {
    tier: 'uploaded_document',
    score: 0.8,
    note: 'An uploaded document is a mid-tier source: it names the work, but nobody outside the account can open the original.',
  },
  experience: {
    tier: 'uploaded_document',
    score: 0.8,
    note: 'A stored experience record is a mid-tier source: it describes the role but does not show the work.',
  },
  project: {
    tier: 'uploaded_document',
    score: 0.8,
    note: 'A stored project record is a mid-tier source: it describes the work but does not show it.',
  },
  achievement: {
    tier: 'uploaded_document',
    score: 0.8,
    note: 'An achievement record is a mid-tier source: it is only as strong as the document behind it.',
  },
  manual: {
    tier: 'resume_self_report',
    score: 0.55,
    note: 'A hand-typed entry is a self-report: there is no file or commit anyone else can check, so only corroboration lifts it.',
  },
  llm_inference: {
    tier: 'llm_inference',
    score: 0.35,
    note: 'A model inference is the weakest tier: it is a machine reading of material, not the material itself.',
  },
};

export function authorityFor(kind: string): { tier: string; score: number; note: string } | null {
  return AUTHORITY_TIERS[kind] ?? null;
}

const LOCATOR_KEYS: [keyof EvidenceLocator, string][] = [
  ['path', 'path'],
  ['line', 'line'],
  ['url', 'url'],
  ['sha', 'sha'],
  ['page', 'page'],
  ['section', 'section'],
];

/**
 * The same locator arrives in two vocabularies, and both have to be read.
 *
 * `GET /evidence/{id}` normalises the stored dict and returns `charStart`/`charEnd`
 * (`schemas/evidence.py::LocatorResponse`), while a graph node's `meta.locator` is the raw stored
 * row — snake_case, exactly as `Evidence.locator` was written. A drawer that only understood the
 * camelCase version silently dropped the character range on every node-side read, which is the bug
 * the `graph-model.test.ts` case for `sourceOf` exists to keep fixed.
 */
function rangeOf(locator: Record<string, unknown>): [number | null, number | null] {
  const start = locator['charStart'] ?? locator['char_start'];
  const end = locator['charEnd'] ?? locator['char_end'];
  return [typeof start === 'number' ? start : null, typeof end === 'number' ? end : null];
}

/** The locator as one checkable string: `Core/Src/freertos.c · line 42`, or `chars 0–290`. */
export function locatorText(locator: EvidenceLocator | null | undefined): string | null {
  if (!locator) return null;
  const parts: string[] = [];
  for (const [key, label] of LOCATOR_KEYS) {
    const value = locator[key];
    if (value === null || value === undefined || value === '') continue;
    parts.push(key === 'path' ? String(value) : `${label} ${String(value)}`);
  }
  const [start, end] = rangeOf(locator as unknown as Record<string, unknown>);
  if (start !== null) {
    parts.push(end !== null ? `chars ${start}–${end}` : `chars from ${start}`);
  }
  return parts.length > 0 ? parts.join(' · ') : null;
}

export interface Excerpt {
  text: string;
  truncated: boolean;
  fullLength: number;
}

/**
 * A monospace excerpt, clipped on purpose.
 *
 * A chunk of a résumé is a few hundred characters and a repository file can be thousands; the
 * drawer shows one readable paragraph and states how much was left out, rather than making the
 * reader scroll a file to find the sentence the node is about.
 */
export function excerptOf(text: string, limit = 420): Excerpt {
  const collapsed = text.replace(/\r\n/g, '\n').trim();
  if (collapsed.length <= limit) {
    return { text: collapsed, truncated: false, fullLength: collapsed.length };
  }
  return {
    text: `${collapsed.slice(0, limit).trimEnd()}…`,
    truncated: true,
    fullLength: collapsed.length,
  };
}

/**
 * The nine `EvidenceKind` values as a reader would say them.
 *
 * Kept apart from `graph-node-style`, which is keyed by *node* type: `document_chunk` is an
 * evidence kind that a `document` node carries in `meta.kind`, and the two vocabularies are not
 * the same list even though they overlap.
 */
const EVIDENCE_KIND_LABELS: Record<string, string> = {
  repo_file: 'Repository file',
  commit: 'Commit',
  readme: 'README',
  document_chunk: 'Document chunk',
  experience: 'Experience record',
  project: 'Project record',
  achievement: 'Achievement record',
  manual: 'Manual entry',
  llm_inference: 'Model inference',
};

/** `document_chunk` → `Document chunk`; an unknown kind keeps its own name, title-cased. */
export function kindLabel(kind: string): string {
  const known = EVIDENCE_KIND_LABELS[kind];
  if (known) return known;
  const style = nodeStyle(kind);
  if (style.group !== 'other') return style.label;
  return kind
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

/** Where a piece of evidence came from, in the words the drawer uses. */
export function sourceOf(node: EvidenceGraphNode, item?: EvidenceItem | null): string {
  const meta = node.meta ?? {};
  const locator = item
    ? locatorText(item.locator)
    : locatorText(meta['locator'] as EvidenceLocator);
  const filename = typeof meta['filename'] === 'string' ? meta['filename'] : null;
  const path = typeof meta['path'] === 'string' ? meta['path'] : null;
  const chunk = typeof meta['chunkIndex'] === 'number' ? `chunk ${meta['chunkIndex']}` : null;
  const parts = [filename ?? path, chunk, locator].filter(
    (part): part is string => typeof part === 'string' && part.length > 0,
  );
  return parts.length > 0 ? parts.join(' · ') : node.label || 'source not recorded';
}

/**
 * "Why it matters", assembled only from what the payload says: the tier the item sits in, which
 * skills it supports, and how many independent sources agree. It deliberately does not rate the
 * candidate or the job — that is a verdict, and a verdict belongs to the claim validator.
 */
export function whyItMatters(
  node: EvidenceGraphNode,
  facts: { evidenceCount: number; confidence: number | null },
  supportingSkills: string[],
): string {
  const kind = String((node.meta ?? {})['kind'] ?? node.type);
  const tier = authorityFor(kind);
  const corroboration =
    typeof (node.meta ?? {})['corroboration'] === 'number'
      ? (node.meta['corroboration'] as number)
      : null;

  const supports =
    supportingSkills.length === 0
      ? 'Nothing in this view cites it as a source for a skill.'
      : supportingSkills.length === 1
        ? `It is the source behind ${supportingSkills[0]}.`
        : `It is one of the sources behind ${supportingSkills.slice(0, 4).join(', ')}${
            supportingSkills.length > 4 ? ` and ${supportingSkills.length - 4} more` : ''
          }.`;

  const tierSentence = tier ? ` ${tier.note}` : '';
  const corroborationSentence =
    corroboration !== null && corroboration > 1
      ? ` ${corroboration} independent source kinds agree on it.`
      : facts.evidenceCount > 0
        ? ' The confidence figure above is the weighted sum of its five factors, not an opinion.'
        : '';

  return `${supports}${tierSentence}${corroborationSentence}`;
}

/**
 * A timestamp in UTC, or a sentence.
 *
 * `null` is rendered as "not recorded", which is what it is: the evidence engine leaves
 * `occurred_at` empty for material with no date (most READMEs), and printing `1970-01-01` there
 * would be an invented fact.
 */
export function formatTimestamp(value: string | null | undefined): string | null {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return `${parsed.toISOString().slice(0, 16).replace('T', ' ')} UTC`;
}

/** The five factors of `confidence@1.0.0`, with the weights the formula applies to each. */
export const CONFIDENCE_WEIGHTS = [
  { key: 'sourceAuthority', label: 'Source authority', weight: 0.3 },
  { key: 'recency', label: 'Recency', weight: 0.15 },
  { key: 'specificity', label: 'Specificity', weight: 0.2 },
  { key: 'corroboration', label: 'Corroboration', weight: 0.2 },
  { key: 'extractionQuality', label: 'Extraction quality', weight: 0.15 },
] as const;

export type { NodeGroup } from './graph-node-style';
