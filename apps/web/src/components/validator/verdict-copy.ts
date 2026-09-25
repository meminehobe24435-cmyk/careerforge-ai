import type { ClaimReason, ClaimSource, ClaimStatus } from '@/lib/validator-api';

/**
 * The words this page is allowed to use.
 *
 * Every string here is derived from code that was read before it was written down:
 * `packages/ai/careerforge_ai/agents/validator_decide.py` (which status, which code),
 * `parsing/claim_rules.py` (what each rule actually tests) and `schemas/common.py`
 * (`ClaimRuleCode`, `ClaimStatus`). Nothing in this file invents a claim about a rule the
 * backend does not implement, and no rule code is given a friendlier name than it earned.
 */

/** `ClaimStatus` → the verdict line. Audit tone: a finding, not a grade. */
export const VERDICT_COPY: Record<ClaimStatus, { label: string; detail: string }> = {
  supported: {
    label: 'Verified by evidence',
    detail:
      'Every element of this sentence is carried by your evidence, with at least two independent sources behind it.',
  },
  partially_supported: {
    label: 'Some parts are supported, but the wording overstates the evidence',
    detail:
      'Part of the sentence is carried by your evidence and part of it is not. The rules that fired are listed below.',
  },
  unsupported: {
    label: 'No sufficient evidence found',
    detail: 'Your evidence does not carry this sentence as written.',
  },
  contradicted: {
    label: 'Evidence conflicts with this claim',
    detail:
      'The time line or the retrieved material actively disagrees with this sentence — this is the only verdict that accuses rather than merely refuses.',
  },
  pending: {
    label: 'Pending',
    detail: 'The gate has not returned a verdict for this sentence.',
  },
};

/**
 * The confidence tooltip. Wording is fixed: confidence is *evidence strength*, not the
 * probability that the sentence is true (`validator_decide.py` computes it from the
 * `confidence@1.0.0` factors — authority, recency, specificity, corroboration, extraction).
 */
export const CONFIDENCE_TOOLTIP =
  'Confidence estimates how strongly the available evidence supports this verdict. It is not a probability of truth.';

/** The gate's own thresholds (`scoring/confidence.py`: 0.75 supported, 0.45 partial). */
export const SUPPORTED_THRESHOLD = 0.75;
export const PARTIAL_THRESHOLD = 0.45;

/** `validator_decide._MIN_INDEPENDENT_SOURCES` — distinct evidence kinds required. */
export const MIN_INDEPENDENT_SOURCES = 2;

export type ConfidenceBand = 'High' | 'Medium' | 'Low';

export interface ConfidenceReading {
  band: ConfidenceBand;
  /** Rounded percentage of the API's own value — never a recomputation of the verdict. */
  percent: string;
  /** `High · 89%` */
  text: string;
}

/**
 * Band + number. The band uses the gate's thresholds rather than new ones, so `High` and
 * `supported` cannot disagree without the reader seeing both.
 */
export function readConfidence(confidence: number): ConfidenceReading {
  const ratio = Number.isFinite(confidence) ? confidence : 0;
  const band: ConfidenceBand =
    ratio >= SUPPORTED_THRESHOLD ? 'High' : ratio >= PARTIAL_THRESHOLD ? 'Medium' : 'Low';
  const percent = `${Math.round(ratio * 100)}%`;
  return { band, percent, text: `${band} · ${percent}` };
}

/** `ClaimStatus.allows_resume_inclusion` — mirrored from the enum, not re-decided here. */
export function allowsResumeInclusion(status: ClaimStatus): boolean {
  return status === 'supported' || status === 'partially_supported';
}

export function inclusionCopy(status: ClaimStatus): string {
  return allowsResumeInclusion(status)
    ? 'May be written to a résumé without an override'
    : 'Must not be written to a résumé as it stands';
}

/** How the retriever found this source (`RetrievalChannel`). Unknown values stay verbatim. */
export function channelLabel(channel: string): string {
  switch (channel) {
    case 'semantic':
      return 'semantic';
    case 'keyword':
      return 'keyword';
    case 'both':
      return 'semantic + keyword';
    case 'metadata':
      return 'metadata';
    case 'manual':
      return 'manual';
    default:
      return channel;
  }
}

export function severityVariant(severity: string): 'danger' | 'weak' | 'outline' {
  if (severity === 'blocker') return 'danger';
  if (severity === 'warning') return 'weak';
  return 'outline';
}

export interface RuleCopy {
  /** The risk statement — what the rule means for the sentence. */
  title: string;
  /** One line on what the rule tests, for the "why was this rejected" panel. */
  explanation: string;
}

/**
 * Two rule codes are raised by *two different* rules each, and the API carries no extra field to
 * tell them apart:
 *
 * * `superlative_language` — `detect_superlatives` (advisory wording) and `detect_ownership_gap`
 *   (the status cap). The ownership message is the one that ends in `是职责范围的断言`;
 *   `claim_rules.py:237` is its only author.
 * * `low_confidence_sources` — the contradicting-evidence branch (`validator_decide.py:136`) and
 *   the model-degraded branch (`validator_decide.py:157`).
 *
 * Matching on those markers is the only faithful option. An unrecognised message keeps the
 * generic copy rather than being upgraded to the graver reading.
 */
const OWNERSHIP_MARKER = '职责范围的断言';
const CONTRADICTION_MARKER = '证据与断言冲突';
const DEGRADED_MARKER = '模型判定不可用';

/** `ClaimRuleCode` (schemas/common.py) → copy. Every code the enum declares is listed. */
const RULE_COPY: Record<string, RuleCopy> = {
  numeric_without_evidence: {
    title: 'Quantified result is not backed by measurable evidence',
    explanation:
      'A number in the sentence has no comparable measurement in your evidence. This rule runs before any model is consulted, and it blocks the claim outright.',
  },
  superlative_language: {
    title: 'Over-claiming wording the evidence cannot carry',
    explanation:
      'Absolute or superlative wording needs its own evidence. On its own this rule is advisory: it never blocks a claim.',
  },
  skill_not_in_graph: {
    title: 'A technology named here never appears in your evidence',
    explanation:
      'Every technical noun in the sentence has to appear somewhere in the evidence, so an interviewer cannot ask about something the material does not show.',
  },
  no_evidence_match: {
    title: 'Part of the sentence has no supporting evidence',
    explanation:
      'The adjudicator named specific fragments it could not support. They are listed in the message, and repeated under "unknowns".',
  },
  single_source_only: {
    title: 'Only one independent source backs this claim',
    explanation:
      'A fully supported verdict needs two independent evidence kinds. One uncorroborated source is one source, whatever its confidence.',
  },
  timeline_conflict: {
    title: 'Dates in your evidence conflict with this sentence',
    explanation:
      'A timeline conflict is the one condition that makes a claim contradicted rather than merely unsupported.',
  },
  low_confidence_sources: {
    title: 'Evidence conflicts with the claim, or the adjudicator was unavailable',
    explanation:
      'This code is raised in two situations: contradicting evidence was found, or the model step degraded and the verdict rests on the deterministic rules and retrieval alone (in which case `model` is null).',
  },
  quantified_skill_unsupported: {
    title: 'Quantified claim about a skill the evidence does not support',
    explanation:
      'Declared in `ClaimRuleCode`, but no rule or heuristic handler in this build emits it — the description comes from the enum, not from an implementation.',
  },
};

const UNKNOWN_RULE_COPY: RuleCopy = {
  title: '',
  explanation:
    'Unknown rule code: this build has no description for it, so the code and the message are shown exactly as the API returned them.',
};

export function ruleCopy(code: string): RuleCopy {
  return RULE_COPY[code] ?? UNKNOWN_RULE_COPY;
}

/** One grouped risk, ready to render. */
export interface RiskItem {
  code: string;
  title: string;
  explanation: string;
  severity: string;
  /** Every message the API returned under this code, verbatim. */
  messages: string[];
  /** `true` when the code has no verified description in this build. */
  unknown: boolean;
}

function variantOf(reason: ClaimReason): string {
  if (reason.rule === 'superlative_language' && reason.message.includes(OWNERSHIP_MARKER)) {
    return 'superlative_language:ownership';
  }
  if (reason.rule === 'low_confidence_sources' && reason.message.includes(CONTRADICTION_MARKER)) {
    return 'low_confidence_sources:contradiction';
  }
  if (reason.rule === 'low_confidence_sources' && reason.message.includes(DEGRADED_MARKER)) {
    return 'low_confidence_sources:degraded';
  }
  return reason.rule;
}

const OWNERSHIP_COPY: RuleCopy = {
  title: 'Claim implies ownership beyond the available evidence',
  explanation:
    'The sentence asserts ownership or scope that the evidence never states. The underlying work can still be real, so the status is capped at partially supported rather than rejected.',
};

const CONTRADICTION_COPY: RuleCopy = {
  title: 'Evidence conflicts with this claim',
  explanation:
    'Retrieved material actively disagrees with the sentence. A contradiction is never reworded: there is no honest way to restate a sentence the evidence refutes.',
};

const DEGRADED_COPY: RuleCopy = {
  title: 'Model judgement unavailable',
  explanation:
    'The adjudication step degraded, so the verdict rests on the deterministic rules and retrieval alone. The response reports `model: null` in that case.',
};

function copyFor(variant: string, code: string): RuleCopy {
  if (variant === 'superlative_language:ownership') return OWNERSHIP_COPY;
  if (variant === 'low_confidence_sources:contradiction') return CONTRADICTION_COPY;
  if (variant === 'low_confidence_sources:degraded') return DEGRADED_COPY;
  return ruleCopy(code);
}

/**
 * Group the API's reasons into one risk per (code, variant), keeping every raw message.
 *
 * Same-code reasons are grouped because `detect_superlatives` returns one reason per matched
 * phrase: five rows saying the same thing five times would hide the one that differs.
 */
export function riskItems(reasons: ClaimReason[]): RiskItem[] {
  const grouped = new Map<string, RiskItem>();
  for (const reason of reasons) {
    const variant = variantOf(reason);
    const existing = grouped.get(variant);
    if (existing) {
      existing.messages.push(reason.message);
      if (reason.severity === 'blocker') existing.severity = 'blocker';
      continue;
    }
    const copy = copyFor(variant, reason.rule);
    grouped.set(variant, {
      code: reason.rule,
      title: copy.title || reason.rule,
      explanation: copy.explanation,
      severity: reason.severity,
      messages: [reason.message],
      unknown: !(reason.rule in RULE_COPY),
    });
  }
  return [...grouped.values()];
}

/** The worst severity present, for the panel header. */
export function overallSeverity(reasons: ClaimReason[]): string {
  if (reasons.some((reason) => reason.severity === 'blocker')) return 'blocker';
  if (reasons.some((reason) => reason.severity === 'warning')) return 'warning';
  if (reasons.length > 0) return 'info';
  return 'none';
}

/**
 * Why the gate returned no rewrite.
 *
 * `claim_rules.build_safer_formulation` returns an empty string — which
 * `validator_decide._safe_rewrite` turns into `safe_rewrite: null` — when nothing changed, when
 * there was no number to drop, or when dropping the numbers would leave a sentence that still names
 * a technical noun the evidence does not carry. Which of them applies is read off the rule codes
 * that fired; an ownership-only claim is the case where the objection is to a clause the evidence
 * *does* overlap with, so no clause can be dropped at all.
 */
export function noRewriteCopy(reasons: ClaimReason[]): { title: string; body: string } {
  const codes = new Set(reasons.map((reason) => reason.rule));
  const ownership = reasons.some(
    (reason) => variantOf(reason) === 'superlative_language:ownership',
  );
  if (codes.has('skill_not_in_graph')) {
    return {
      title: 'No evidence-safe wording offered',
      body: 'The gate declines a rewrite when what remains would still assert something your evidence does not carry. Here the sentence would still name a technology the evidence never mentions, and an edit that hides the removed claim is worse than no edit.',
    };
  }
  if (ownership) {
    // Verified against the live gate: an ownership-only claim ("主导了…并独立完成…") returns
    // `safe_rewrite: null`. The clause-dropping fallback can only remove parts the evidence cannot
    // carry, and the overstated clause is precisely the part the evidence *does* overlap with — so
    // there is no edit it can make, and it does not pretend otherwise.
    return {
      title: 'No evidence-safe wording offered',
      body: 'The objection is to the wording of the role, and the gate rewrites by dropping parts the evidence cannot carry. It cannot soften an ownership assertion without changing what you are claiming, so it offers nothing rather than a sentence that still overstates the same thing.',
    };
  }
  if (codes.has('numeric_without_evidence') || codes.has('no_evidence_match')) {
    return {
      title: 'No evidence-safe wording offered',
      body: 'The gate rewrites by dropping what the evidence cannot carry, and only when the rest of the sentence is still supported. Nothing could be dropped here without either leaving another unsupported statement or changing nothing at all.',
    };
  }
  return {
    title: 'No rewrite needed',
    body: 'The gate proposes a shorter sentence only when part of the sentence is unsupported. Nothing in this claim had to be removed.',
  };
}

/** `POST /evidence/validate` request path, printed in the header in mono. */
export const VALIDATOR_ENDPOINT = 'POST /evidence/validate';

/**
 * The rule-detail panel's heading, phrased for the verdict it belongs to.
 *
 * The panel used to ask **"Why was this rejected?"** over every verdict — including `supported`,
 * where it told the reader the opposite of what the gate had just said, directly under a headline
 * reading "Verified by evidence". The heading is the reader's first question and it has to be the
 * question the verdict actually raises, so it is derived from the status rather than fixed.
 *
 * `pending` and anything this build does not know get a neutral heading: asking why a *rejection*
 * happened when no rejection is on record would be a claim the payload does not support.
 */
export function rulePanelTitle(status: ClaimStatus): string {
  switch (status) {
    case 'supported':
      return 'Why is this supported?';
    case 'partially_supported':
      return 'Why is this only partially supported?';
    case 'unsupported':
    case 'contradicted':
      return 'Why was this rejected?';
    default:
      return 'Why this verdict?';
  }
}

/** What replaces the rule list when no rule fired: the reason the verdict came out as it did. */
export interface AffirmativeExplanation {
  title: string;
  body: string;
}

/**
 * The explanation for a verdict that carries **no rule codes**.
 *
 * An empty rejection section is worse than no section: it renders a heading, a `0 rule codes`
 * badge and, once expanded, a sentence apologising for having nothing to say. When no rule fired
 * there is no objection to list, so the panel is not a rejection panel at all — it states what the
 * verdict actually rested on, in the API's own figures (`independentSourceCount`, the evidence
 * kinds behind the retrieved sources, and the gate's `confidence`).
 *
 * Every number here comes from the payload. Nothing is inferred from the fact that a verdict came
 * out a particular way.
 */
export function affirmativeExplanation(
  status: ClaimStatus,
  evidence: { sources: ClaimSource[]; independentSourceCount: number; confidence: number },
): AffirmativeExplanation {
  const reading = readConfidence(evidence.confidence);
  const kinds = [...new Set(evidence.sources.map((source) => source.kind))].sort();
  const kindText = kinds.length > 0 ? ` across ${kinds.join(' / ')}` : '';
  const plural = evidence.independentSourceCount === 1 ? 'kind' : 'kinds';

  if (status === 'supported') {
    return {
      title: 'What carries this sentence',
      body:
        `No rule fired for this claim, so there is no objection to expand and none is shown. ` +
        `The verdict comes from the evidence arithmetic instead: ${evidence.independentSourceCount} independent evidence ${plural}${kindText}, ` +
        `which clears the gate's own minimum of ${MIN_INDEPENDENT_SOURCES} before it will call a sentence supported, ` +
        `at a confidence of ${reading.text}. The sources listed above are the rows that carried it — ` +
        `each one shows the channel it was retrieved on and the confidence stored on the evidence itself.`,
    };
  }

  if (status === 'partially_supported') {
    return {
      title: 'What this verdict rests on',
      body:
        `No rule fired for this claim: the partial verdict comes from the evidence arithmetic rather than from a rule objection. ` +
        `${evidence.independentSourceCount} independent evidence ${plural}${kindText} were retrieved at a confidence of ${reading.text}, ` +
        `which is below the ${SUPPORTED_THRESHOLD} a supported verdict requires. ` +
        `The sources above are what the gate did find; the parts of the sentence it could not place are listed under "unknowns".`,
    };
  }

  return {
    title: 'Why no rule is listed',
    body:
      `No rule fired for this claim — the verdict came from the evidence arithmetic alone. ` +
      `${evidence.independentSourceCount} independent evidence ${plural}${kindText} were retrieved at a confidence of ${reading.text}. ` +
      `The gate reports this rather than a rule code because that is what it decided on; there is no rule objection to show you.`,
  };
}

/** Where one cited source can be inspected. The graph highlights the node. */
export function evidenceGraphHref(source: ClaimSource): string {
  return `/app/evidence-graph?node=${encodeURIComponent(source.evidenceId)}`;
}
