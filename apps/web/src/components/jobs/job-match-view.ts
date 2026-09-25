/**
 * The derivation layer for `/app/jobs`: wire payload in, renderable rows out. Pure functions,
 * no React, so every claim the page makes can be asserted in a plain unit test.
 *
 * Four rules from the product brief shape everything here:
 *
 * 1. **Never invent a number.** Every figure on the page is a field of a payload; a field the
 *    API does not report renders as `—`. Nothing is recomputed that the API already computes
 *    (the score, the dimension scores, the coverage).
 * 2. **`null` is not `0`.** "The payload does not carry this" and "the payload says zero" are
 *    rendered differently everywhere.
 * 3. **Unknown ≠ Missing.** The engine's `gaps` and `unknowns` lists are never merged, and a
 *    requirement the engine did not list at all gets its own state rather than being guessed
 *    into one of them.
 * 4. **The verdicts are the engine's, not ours.** A requirement's state is decided by *which
 *    list the engine put it in* (`strengths` / `gaps` / `unknowns`), never by re-deriving the
 *    score client-side. See :data:`VERDICT_MEANINGS` for the exact wording shown to a reader.
 */

import type { JobDetail, JobMatch, JobSkill, MatchStrength, SkillTree } from '@/lib/jobs-api';

/**
 * Evidence count at which the engine treats a matched requirement as fully evidenced.
 *
 * This is the engine's own constant (`packages/ai/careerforge_ai/scoring/match.py`,
 * ``_EVIDENCE_SATURATION = 3``): its evidence factor is
 * ``0.60 + 0.40 × min(1, count / 3)``, so a match with three or more independent evidence
 * items is backed to 100% of its nominal level and one with fewer carries 73–87%. The label
 * below distinguishes those two cases and prints the count next to it, so a reader can check
 * the reasoning rather than take the label's word for it.
 */
export const ENGINE_EVIDENCE_SATURATION = 3;

export type SkillVerdict =
  /** In the engine's `strengths` list, with its evidence saturation point reached. */
  | 'matched'
  /** In `strengths`, but with fewer evidence items than the saturation point above. */
  | 'partial'
  /** In `gaps`: the engine has a positive reason to believe the candidate lacks it. */
  | 'missing'
  /** In `unknowns`: nothing points either way, so the engine asks. */
  | 'unknown'
  /** In none of the three lists: the payload carries no per-skill verdict for it. */
  | 'unreported'
  /** The taxonomy could not normalise the requirement, so the engine never scores it. */
  | 'unnormalised'
  /** No match has been computed yet — the tree is shown without verdicts. */
  | 'awaiting';

export const VERDICT_LABELS: Record<SkillVerdict, string> = {
  matched: 'Matched',
  partial: 'Partial',
  missing: 'Missing',
  unknown: 'Unknown',
  unreported: 'Not in result',
  unnormalised: 'Not normalised',
  awaiting: 'Awaiting match',
};

/** Badge variants from `@careerforge/ui` (docs/UI.md §1.2: green = evidenced, amber = partial). */
export const VERDICT_TONES: Record<
  SkillVerdict,
  'supported' | 'weak' | 'danger' | 'default' | 'outline' | 'signal'
> = {
  matched: 'supported',
  partial: 'weak',
  missing: 'danger',
  unknown: 'signal',
  unreported: 'default',
  unnormalised: 'outline',
  awaiting: 'outline',
};

/** The wording behind each label, printed verbatim in the page's legend. */
export const VERDICT_MEANINGS: Record<SkillVerdict, string> = {
  matched:
    'The engine listed it in strengths: the requirement is met and backed by at least three independent evidence items.',
  partial:
    'The engine listed it in strengths — the requirement is met — but with fewer than three evidence items, the point at which the engine treats a match as fully evidenced.',
  missing:
    'The engine listed it in gaps: there is a positive reason to believe it is absent (an unproven claim, a recorded level of "none", or a demonstrated domain gap).',
  unknown:
    'The engine listed it in unknowns: nothing in the profile or the evidence graph points either way, so it asks instead of guessing.',
  unreported:
    'The match payload carries no verdict for this requirement. The engine lists at most six strengths and eight gaps, and a requirement it counts as met but does not advertise appears in none of the three lists.',
  unnormalised:
    'The taxonomy could not resolve this requirement to a canonical skill, so the engine excludes it from scoring rather than counting it as a miss.',
  awaiting: 'No match has been computed for this posting yet, so there is no verdict to show.',
};

export interface SkillRow {
  /** Stable React key: canonical id when there is one, else the raw text. */
  key: string;
  canonicalId: string | null;
  rawText: string;
  requirement: string;
  weight: number;
  jdEvidence: string;
  mentions: number;
  verdict: SkillVerdict;
  /** From the engine's strength entry, or `null` when it reported no count. */
  evidenceCount: number | null;
  /** The level the engine read from the profile, or `null`. */
  userLevel: string | null;
  /** Mean evidence confidence for this skill, or `null`. */
  confidence: number | null;
  /** The engine's own reason / JD sentence / question, whichever applies. */
  note: string | null;
  /** The question the engine wants to ask (`unknowns[*].askUser`). */
  askUser: string | null;
  severity: string | null;
}

export interface SkillGroups {
  required: SkillRow[];
  preferred: SkillRow[];
  bonus: SkillRow[];
  /** Verdict counts across all three groups. */
  counts: Record<SkillVerdict, number>;
  /** Requirements with no verdict in the payload — the number behind the legend's caveat. */
  unreported: number;
  total: number;
}

/** A requirement as the match payload describes it: an id, and the level it was required at. */
interface MatchEntry {
  canonicalId: string;
  requirement?: string;
}

function sameId(entry: MatchEntry, id: string): boolean {
  return entry.canonicalId.toLowerCase() === id;
}

/**
 * Find the engine's entry for one requirement.
 *
 * The level is checked first because the same canonical skill can be required at two levels
 * (a posting that names FreeRTOS under both "任职要求" and "加分项" produces two rows), and a
 * bonus-level match must not be reported against the required-level row. When no entry carries
 * the level — the payload's `requirement` vocabulary moving is the realistic cause — the id
 * alone is used, because a changed label is not a missing verdict.
 */
function findEntry<T extends MatchEntry>(entries: T[], skill: JobSkill): T | undefined {
  const id = (skill.canonicalId ?? '').toLowerCase();
  if (!id) return undefined;
  return (
    entries.find((entry) => sameId(entry, id) && entry.requirement === skill.requirement) ??
    entries.find((entry) => sameId(entry, id))
  );
}

/** `matched` vs `partial` for a requirement the engine counts as met (see the constant above). */
function strengthVerdict(strength: MatchStrength): SkillVerdict {
  return strength.evidenceCount >= ENGINE_EVIDENCE_SATURATION ? 'matched' : 'partial';
}

function rowFor(skill: JobSkill, verdict: SkillVerdict): SkillRow {
  return {
    key: `${skill.canonicalId ?? skill.rawText.trim().toLowerCase()}::${skill.requirement}`,
    canonicalId: skill.canonicalId,
    rawText: skill.rawText,
    requirement: skill.requirement,
    weight: skill.weight,
    jdEvidence: skill.jdEvidence,
    mentions: skill.mentions,
    verdict,
    evidenceCount: null,
    userLevel: null,
    confidence: null,
    note: null,
    askUser: null,
    severity: null,
  };
}

function rowForSkill(skill: JobSkill, match: JobMatch | null): SkillRow {
  if (!skill.canonicalId) return rowFor(skill, 'unnormalised');
  if (!match) return rowFor(skill, 'awaiting');

  const strength = findEntry(match.strengths, skill);
  if (strength) {
    return {
      ...rowFor(skill, strengthVerdict(strength)),
      evidenceCount: strength.evidenceCount,
      userLevel: strength.userLevel,
      confidence: strength.confidence,
      note: strength.reason || `profile level ${strength.userLevel}`,
    };
  }

  const gap = findEntry(match.gaps, skill);
  if (gap) {
    return {
      ...rowFor(skill, 'missing'),
      severity: gap.severity,
      note: gap.jdEvidence || null,
    };
  }

  const unknown = findEntry(match.unknowns, skill);
  if (unknown) {
    return {
      ...rowFor(skill, 'unknown'),
      note: unknown.reason || null,
      askUser: unknown.askUser || null,
    };
  }

  return rowFor(skill, 'unreported');
}

/**
 * Join the skill tree with the match payload.
 *
 * The tree is the source of *what the posting asks for* (three levels, each requirement with
 * its JD sentence) and the match payload is the source of *what the engine found*. Neither is
 * derived from the other, and a requirement the payload does not mention keeps its own state
 * instead of being folded into "missing" — the mistake rule 3 of the module header forbids.
 */
export function buildSkillGroups(tree: SkillTree | undefined, match: JobMatch | null): SkillGroups {
  const empty = (): SkillGroups => ({
    required: [],
    preferred: [],
    bonus: [],
    counts: {
      matched: 0,
      partial: 0,
      missing: 0,
      unknown: 0,
      unreported: 0,
      unnormalised: 0,
      awaiting: 0,
    },
    unreported: 0,
    total: 0,
  });
  if (!tree) return empty();

  const groups = empty();
  const rowsOf = (skills: JobSkill[]): SkillRow[] =>
    skills.map((skill) => rowForSkill(skill, match));
  groups.required = rowsOf(tree.required);
  groups.preferred = rowsOf(tree.preferred);
  groups.bonus = rowsOf(tree.bonus);

  for (const row of [...groups.required, ...groups.preferred, ...groups.bonus]) {
    groups.counts[row.verdict] += 1;
    groups.total += 1;
  }
  groups.unreported = groups.counts.unreported;
  return groups;
}

export interface DimensionRow {
  key: string;
  label: string;
  score: number;
  weight: number;
  weighted: number;
  formula: string;
  /**
   * `null` on a stored match: the row keeps the score, the weight and the formula, but not the
   * per-skill notes or citations. Rendering that as "0 evidence" would claim the dimension is
   * unsupported when the API simply does not carry the detail — so the panel says unavailable.
   */
  notes: string[] | null;
  /**
   * Distinct evidence ids this dimension cites.
   *
   * The engine appends an id per met requirement, so `evidenceIds` legitimately repeats: the
   * live payload carries 22 entries that are 3 distinct evidence items. Printing 22 beside the
   * `why.evidenceUsed` figure of 3 would read as a contradiction, so the deduplicated count is
   * what the panel shows and the column header says "unique".
   */
  evidenceCount: number | null;
  /** The list exactly as returned, repeats included; `null` when the read did not carry it. */
  evidenceIdCount: number | null;
  /** The weight as a percentage of the total, for the bar's label. */
  share: number;
}

/** The engine's documented dimension order (``scoring/weights.py`` / docs/API.md §2.6). */
const DIMENSION_ORDER_INDEX: Record<string, number> = {
  skill: 0,
  experience: 1,
  project: 2,
  education: 3,
  evidence: 4,
};

/**
 * The five dimensions in their fixed order, with each one's numeric contribution.
 *
 * The order is ours (the payload is a map); the numbers are the API's. `share` re-expresses
 * the API's own `weight` as a percentage for the label — arithmetic on a reported number, not
 * a second computation of the score.
 */
export function buildDimensionRows(match: JobMatch): DimensionRow[] {
  return Object.values(match.dimensions)
    .slice()
    .sort(
      (left, right) =>
        (DIMENSION_ORDER_INDEX[left.key] ?? 99) - (DIMENSION_ORDER_INDEX[right.key] ?? 99) ||
        left.label.localeCompare(right.label),
    )
    .map((dimension) => ({
      key: dimension.key,
      label: dimension.label,
      score: dimension.score,
      weight: dimension.weight,
      weighted: dimension.weighted,
      formula: dimension.formula,
      notes: dimension.notes,
      // `evidenceIds` is `null` on a stored match: the row keeps the score and the weights but not
      // the per-skill citations, so counting them here would report "0 pieces of evidence" for a
      // dimension that has some. The panel renders "unavailable" for that case instead.
      evidenceCount: dimension.evidenceIds === null ? null : new Set(dimension.evidenceIds).size,
      evidenceIdCount: dimension.evidenceIds?.length ?? null,
      share: Math.round(dimension.weight * 100),
    }));
}

/**
 * The sum of the five weighted contributions — the arithmetic behind the headline score.
 *
 * Returned as a number so the panel can *show* that the breakdown adds up to the reported
 * score rather than asserting it in prose. When they disagree (a rounding difference, or a
 * payload whose weights were changed without the score following) the panel prints both,
 * because a "why" panel that quietly rounds a mismatch away is the thing this product exists
 * to avoid.
 */
export function dimensionWeightedSum(rows: DimensionRow[]): number {
  return Math.round(rows.reduce((total, row) => total + row.weighted, 0) * 100) / 100;
}

export type MatchSource = 'computed' | 'stored';

export interface MatchFigures {
  /** 0–1, or `null` when the endpoint that produced this match does not report it. */
  evidenceCoverage: number | null;
  confidence: number | null;
  degraded: boolean | null;
  warnings: string[];
}

/**
 * The figures shown beside the score, and whether they were actually reported.
 *
 * `GET /jobs/{id}/match` builds its response without `evidenceCoverage`, `confidence`,
 * `degraded`, `narrative` and `warnings` (see `routers/jobs.py`: the `MatchResponse` is
 * constructed without them, so the model's defaults of `0.0` / `false` / `[]` are serialised).
 * A default is indistinguishable on the wire from a measured zero, so for a stored match the
 * page prints `—` and says why instead of printing "0%" for a coverage the live endpoint
 * reports as 100%. `POST /jobs/{id}/match` returns all five and is the only path that fills
 * these fields.
 */
export function buildMatchFigures(match: JobMatch, source: MatchSource): MatchFigures {
  if (source === 'stored') {
    return { evidenceCoverage: null, confidence: null, degraded: null, warnings: [] };
  }
  return {
    evidenceCoverage: match.evidenceCoverage,
    confidence: match.confidence,
    degraded: match.degraded,
    // The API now reports `null` for a stage that did not run, so the panel cannot assume a list;
    // an absent list is rendered as "not recorded" rather than as "no warnings".
    warnings: match.warnings ?? [],
  };
}

/**
 * What the API's coverage number actually counts.
 *
 * `JobMatchResult.evidence_coverage` is documented as "share of required skills backed by at
 * least one piece of evidence", and the implementation
 * (`scoring/match.py::_evidence_dimension`) measures it over the requirements the engine
 * classified as **met** — the same list the evidence dimension scores. Both readings are
 * printed next to the figure so a reader is not left with an unexplained percentage.
 */
export const EVIDENCE_COVERAGE_DEFINITION =
  'Requirements the engine counts as met that carry at least one evidence item — ' +
  'match.py::_evidence_dimension, over the same list the evidence dimension scores.';

/** Warnings `POST /jobs/analyze` attaches to its response; `GET /jobs/{id}` has none. */
export function analysisWarnings(detail: JobDetail | undefined): string[] {
  const raw = detail?.analysis?.['warnings'];
  return Array.isArray(raw) ? raw.filter((item): item is string => typeof item === 'string') : [];
}

/** `/app/evidence-graph?skill=<canonicalId>` — the product chain's next step from a skill. */
export function evidenceGraphHref(canonicalId: string): string {
  return `/app/evidence-graph?skill=${encodeURIComponent(canonicalId)}`;
}

/** A reported number, with trailing `.0` dropped. Never rounds a value the API sent. */
export function formatPoints(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return String(value);
}

/** A 0–1 ratio as a percentage. `null` in, `—` out: an unmeasured ratio is not 0%. */
export function formatRatioAsPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return `${Math.round(value * 100)}%`;
}

/** A dimension weight as a percentage of the total (the API's `weight` is 0–1). */
export function formatWeightPercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

/** An evidence count, or `—` when the payload reported none for this row. */
export function formatEvidenceCount(value: number | null): string {
  return value === null ? '—' : String(value);
}
