import { describe, expect, it } from 'vitest';

import {
  ENGINE_EVIDENCE_SATURATION,
  buildDimensionRows,
  buildMatchFigures,
  buildSkillGroups,
  dimensionWeightedSum,
  evidenceGraphHref,
  formatPoints,
  formatRatioAsPercent,
  type SkillRow,
  type SkillVerdict,
} from '@/components/jobs/job-match-view';
import type { JobMatch, JobSkill, MatchDimension, SkillTree } from '@/lib/jobs-api';

/**
 * The derivation rules, asserted as behaviour rather than as implementation.
 *
 * The three that matter most:
 *
 * 1. a requirement's state comes from **which list the engine put it in** — a strength with its
 *    evidence saturation point reached is Matched, the same entry with fewer items is Partial,
 *    `gaps` is Missing, `unknowns` is Unknown;
 * 2. a requirement the payload does not mention is **Not in result**, never silently folded into
 *    Missing (which would tell the candidate they lack something the engine never said they
 *    lack);
 * 3. a figure the stored-match endpoint does not report is `null`, and the page renders `—`.
 */

/** The real captured dimension block: the five weights, scores and contributions (`.tmp/jobs_probe`). */
function dimensions(): Record<string, MatchDimension> {
  return {
    skill: {
      key: 'skill',
      label: '技能匹配',
      score: 36.97,
      weight: 0.4,
      weighted: 14.79,
      formula: 'Σ(requirement_weight × effective_level) / Σ(requirement_weight)',
      notes: ['required=1.0 / preferred=0.6 / bonus=0.3', '无证据的技能按 40% 计入'],
      evidenceIds: ['e1', 'e2', 'e3'],
    },
    experience: {
      key: 'experience',
      label: '经历匹配',
      score: 0,
      weight: 0.25,
      weighted: 0,
      formula: '100 × (0.60 × min(1, years/required) + 0.40 × min(1, relevant_roles/2))',
      notes: ['要求年限 3，候选人 0'],
      evidenceIds: [],
    },
    project: {
      key: 'project',
      label: '项目匹配',
      score: 25.85,
      weight: 0.2,
      weighted: 5.17,
      formula: '100 × (0.60 × 项目技能覆盖率 + 0.40 × 项目平均证据强度)',
      notes: ['项目数 5'],
      evidenceIds: [],
    },
    education: {
      key: 'education',
      label: '学历匹配',
      score: 100,
      weight: 0.05,
      weighted: 5,
      formula: '学历等级比对',
      notes: ['学历达到要求'],
      evidenceIds: [],
    },
    evidence: {
      key: 'evidence',
      label: '证据强度',
      score: 87,
      weight: 0.1,
      weighted: 8.7,
      formula: '100 × (0.65 × 命中技能平均置信度 + 0.35 × 有证据的命中比例)',
      notes: ['命中技能 3 个，平均置信度 0.80'],
      evidenceIds: [],
    },
  };
}

function matchOf(overrides: Partial<JobMatch> = {}): JobMatch {
  return {
    jobId: '19708201-13a1-4d00-88ab-0a90bd4778cc',
    score: 33.66,
    dimensions: dimensions(),
    strengths: [
      {
        canonicalId: 'stm32',
        displayName: 'STM32',
        requirement: 'required',
        userLevel: 'moderate',
        evidenceCount: 3,
        confidence: 0.8,
        reason: '3 条证据，置信度 0.80',
      },
      {
        canonicalId: 'can',
        displayName: 'CAN',
        requirement: 'required',
        userLevel: 'moderate',
        evidenceCount: 1,
        confidence: 0.74,
        reason: '1 条证据，置信度 0.74',
      },
    ],
    gaps: [
      {
        canonicalId: 'autosar',
        displayName: 'AUTOSAR',
        requirement: 'bonus',
        severity: 'low',
        jdEvidence: '2. 熟悉 AUTOSAR Classic 架构；',
      },
    ],
    unknowns: [
      {
        canonicalId: 'kubernetes',
        displayName: 'Kubernetes',
        requirement: 'bonus',
        reason: '简历与证据图谱中均无相关信息',
        askUser: '你是否接触过 Kubernetes？如有请补充证据。',
      },
    ],
    why: {
      formula: '0.40·skill + 0.25·experience + 0.20·project + 0.05·education + 0.10·evidence',
      algorithmVersion: 'match@1.0.0',
      evidenceUsed: ['e1', 'e2', 'e3'],
      notes: ['命中要求技能 2 个，缺口 1 个，待确认 1 个'],
      explanation: '技能维度 37 分（权重 40%），证据强度 87 分，加权合计 33.7 分。',
      computedAt: '2026-09-25T16:30:54.751149Z',
    },
    evidenceCoverage: 1,
    confidence: 0.8,
    degraded: true,
    narrative: '',
    warnings: ['结果已降级（原因：no_api_key）'],
    ...overrides,
  };
}

function skillOf(overrides: Partial<JobSkill> & { rawText: string }): JobSkill {
  return {
    canonicalId: null,
    requirement: 'required',
    weight: 1,
    jdEvidence: '',
    mentions: 1,
    ...overrides,
  };
}

function treeOf(overrides: Partial<SkillTree> = {}): SkillTree {
  return {
    jobId: '19708201-13a1-4d00-88ab-0a90bd4778cc',
    role: '嵌入式软件工程师（电机控制方向）',
    company: '某某智能科技',
    required: [
      skillOf({ canonicalId: 'stm32', rawText: 'STM32' }),
      skillOf({ canonicalId: 'can', rawText: 'CAN' }),
      skillOf({ canonicalId: 'autosar', rawText: 'AUTOSAR' }),
      skillOf({ canonicalId: 'kubernetes', rawText: 'Kubernetes' }),
      // In the tree, in none of the match payload's three lists.
      skillOf({ canonicalId: 'motor_control', rawText: 'Motor Control' }),
      // The taxonomy could not resolve it.
      skillOf({ rawText: 'Vector CANoe' }),
    ],
    preferred: [
      skillOf({ canonicalId: 'free_rtos', rawText: 'FreeRTOS', requirement: 'preferred' }),
    ],
    bonus: [skillOf({ canonicalId: 'git', rawText: 'Git', requirement: 'bonus' })],
    unmatchedCount: 1,
    ...overrides,
  };
}

function verdictOf(rows: SkillRow[], canonicalId: string): SkillVerdict {
  const row = rows.find((item) => item.canonicalId === canonicalId);
  if (!row) throw new Error(`no row for ${canonicalId}`);
  return row.verdict;
}

describe('the skill verdict mapping', () => {
  it('reads the verdict off the engine’s own lists, never off a recomputation', () => {
    const groups = buildSkillGroups(treeOf(), matchOf());

    expect(verdictOf(groups.required, 'stm32')).toBe('matched');
    expect(verdictOf(groups.required, 'autosar')).toBe('missing');
    expect(verdictOf(groups.required, 'kubernetes')).toBe('unknown');
    expect(verdictOf(groups.required, 'motor_control')).toBe('unreported');
  });

  it('separates Unknown from Missing and keeps their reasons apart', () => {
    const groups = buildSkillGroups(treeOf(), matchOf());
    const unknown = groups.required.find((row) => row.canonicalId === 'kubernetes');
    const missing = groups.required.find((row) => row.canonicalId === 'autosar');

    expect(unknown?.verdict).toBe('unknown');
    expect(unknown?.askUser).toContain('你是否接触过 Kubernetes');
    expect(unknown?.severity).toBeNull();

    expect(missing?.verdict).toBe('missing');
    expect(missing?.severity).toBe('low');
    expect(missing?.askUser).toBeNull();
    // "no information either way" is not "there is a reason to believe it is absent".
    expect(groups.counts.unknown).toBe(1);
    expect(groups.counts.missing).toBe(1);
  });

  it('counts an unmet evidence saturation point as Partial, not Matched', () => {
    const groups = buildSkillGroups(treeOf(), matchOf());
    const matched = groups.required.find((row) => row.canonicalId === 'stm32');
    const partial = groups.required.find((row) => row.canonicalId === 'can');

    expect(ENGINE_EVIDENCE_SATURATION).toBe(3);
    expect(matched?.verdict).toBe('matched');
    expect(matched?.evidenceCount).toBe(3);
    expect(partial?.verdict).toBe('partial');
    expect(partial?.evidenceCount).toBe(1);
    // The count travels with the label, so the reader can check the split.
    expect(partial?.note).toBe('1 条证据，置信度 0.74');
  });

  it('marks a requirement the taxonomy could not resolve instead of calling it a miss', () => {
    const groups = buildSkillGroups(treeOf(), matchOf());
    const row = groups.required.find((item) => item.canonicalId === null);

    expect(row?.verdict).toBe('unnormalised');
    expect(row?.rawText).toBe('Vector CANoe');
    // A requirement with no canonical id has no evidence-graph node to open.
    expect(row?.canonicalId).toBeNull();
  });

  it('carries no verdict at all before a match has been computed', () => {
    const groups = buildSkillGroups(treeOf(), null);

    // Every requirement with a canonical id waits for a match; the un-normalisable one is
    // already marked as such, because the taxonomy's verdict does not depend on the match.
    expect(groups.counts.awaiting).toBe(7);
    expect(groups.counts.unnormalised).toBe(1);
    expect(groups.counts.matched).toBe(0);
    expect(groups.counts.missing).toBe(0);
    expect(groups.counts.unknown).toBe(0);
    expect(groups.counts.unreported).toBe(0);
  });

  it('reports how many requirements the payload never itemised', () => {
    const groups = buildSkillGroups(treeOf(), matchOf());

    // motor_control plus the two levels the fixture's match lists do not mention.
    expect(groups.unreported).toBe(3);
    expect(groups.total).toBe(8);
    expect(groups.counts.matched).toBe(1);
    expect(groups.counts.partial).toBe(1);
    expect(groups.counts.unnormalised).toBe(1);
  });

  it('counts per level, so a bonus-level match is not read as a required one', () => {
    const match = matchOf({
      strengths: [
        {
          canonicalId: 'git',
          displayName: 'Git',
          requirement: 'bonus',
          userLevel: 'moderate',
          evidenceCount: 3,
          confidence: 0.8,
          reason: '3 条证据，置信度 0.80',
        },
      ],
    });
    const groups = buildSkillGroups(treeOf(), match);

    expect(verdictOf(groups.bonus, 'git')).toBe('matched');
    // Nothing is claimed about the rest: the payload listed one strength and nothing else, so
    // the other requirements stay "no verdict" rather than turning into gaps.
    expect(groups.counts.matched).toBe(1);
    expect(groups.counts.awaiting).toBe(0);
    // stm32, can, motor_control and the preferred level — none of them mentioned by the payload.
    expect(groups.counts.unreported).toBe(4);
    expect(groups.counts.unnormalised).toBe(1);
  });

  it('degrades to an empty structure when the tree is missing, without inventing rows', () => {
    const groups = buildSkillGroups(undefined, matchOf());

    expect(groups.total).toBe(0);
    expect(groups.required).toHaveLength(0);
    expect(groups.unreported).toBe(0);
  });
});

describe('the score breakdown', () => {
  it('keeps the engine’s dimension order and its own numbers', () => {
    const rows = buildDimensionRows(matchOf());

    expect(rows.map((row) => row.key)).toEqual([
      'skill',
      'experience',
      'project',
      'education',
      'evidence',
    ]);
    expect(rows[0]?.weighted).toBe(14.79);
    expect(rows[0]?.weight).toBe(0.4);
    expect(rows[0]?.formula).toContain('Σ(requirement_weight');
    expect(rows[0]?.notes).toContain('无证据的技能按 40% 计入');
  });

  it('counts distinct evidence ids, because the engine’s list repeats them', () => {
    // The live skill dimension returns 22 entries that are 3 distinct evidence items; printing
    // 22 beside `why.evidenceUsed` (3) would look like a contradiction inside one panel.
    const base = dimensions();
    const rows = buildDimensionRows(
      matchOf({
        dimensions: {
          ...base,
          skill: { ...base['skill']!, evidenceIds: ['e1', 'e1', 'e2', 'e1', 'e3', 'e2'] },
        },
      }),
    );

    expect(rows[0]?.evidenceCount).toBe(3);
    expect(rows[0]?.evidenceIdCount).toBe(6);
  });

  it('sums the five contributions to the reported score', () => {
    const rows = buildDimensionRows(matchOf());

    expect(dimensionWeightedSum(rows)).toBe(33.66);
  });

  it('reports the real difference when the contributions do not add up', () => {
    const match = matchOf({ score: 40 });
    const rows = buildDimensionRows(match);

    // The panel prints both numbers rather than reconciling them silently; the arithmetic here
    // is the assertion that it *can* see a mismatch of any size.
    expect(dimensionWeightedSum(rows)).toBe(33.66);
    expect(Math.abs(dimensionWeightedSum(rows) - match.score)).toBeGreaterThan(0.005);
  });
});

describe('the figures beside the score', () => {
  it('reports coverage and confidence when this page computed the match', () => {
    const figures = buildMatchFigures(matchOf(), 'computed');

    expect(figures.evidenceCoverage).toBe(1);
    expect(figures.confidence).toBe(0.8);
    expect(figures.degraded).toBe(true);
    expect(figures.warnings).toHaveLength(1);
  });

  it('reports them as unreported — not as zero — for a stored match', () => {
    // `GET /jobs/{id}/match` serialises the model defaults for these fields, so a `0` here is
    // indistinguishable from a measured zero. The figures are therefore `null`, and the page
    // prints `—` plus the endpoint that does report them.
    const figures = buildMatchFigures(matchOf({ evidenceCoverage: 0, confidence: 0 }), 'stored');

    expect(figures.evidenceCoverage).toBeNull();
    expect(figures.confidence).toBeNull();
    expect(figures.degraded).toBeNull();
    expect(figures.warnings).toEqual([]);
  });
});

describe('formatting', () => {
  it('never rounds a number the API reported', () => {
    expect(formatPoints(33.66)).toBe('33.66');
    expect(formatPoints(100)).toBe('100');
    expect(formatPoints(0)).toBe('0');
  });

  it('renders an unreported value as a dash rather than as zero', () => {
    expect(formatPoints(null)).toBe('—');
    expect(formatRatioAsPercent(null)).toBe('—');
    expect(formatRatioAsPercent(1)).toBe('100%');
    expect(formatRatioAsPercent(0)).toBe('0%');
  });

  it('builds the evidence-graph link from the canonical id', () => {
    expect(evidenceGraphHref('free_rtos')).toBe('/app/evidence-graph?skill=free_rtos');
    expect(evidenceGraphHref('c++')).toBe('/app/evidence-graph?skill=c%2B%2B');
  });
});
