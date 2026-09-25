import {
  Award,
  Briefcase,
  CircleHelp,
  Cpu,
  FileCode2,
  FileText,
  FolderGit2,
  GitBranch,
  GitCommitHorizontal,
  GraduationCap,
  MessagesSquare,
  Scale,
  Target,
  UserRound,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import type { EvidenceGraphNode, GraphNodeType } from '@/lib/graph-api';

/**
 * How a node kind is drawn.
 *
 * Three rules, taken from the brief and from `docs/UI.md` §2.1:
 *
 * 1. **Identity is carried by an icon, a border weight and a surface — not by colour.** Eight
 *    rainbow node colours is the exact thing this page must not be, so only three accents exist
 *    (brand = the person and their targets, signal = the candidate's own record, neutral = the
 *    leaves) and the eight kinds are told apart by shape first.
 * 2. **Colour means confidence, not identity.** The one number on a node is rendered in the
 *    semantic token for its band, so a green figure always means "evidence ≥ 0.75" and never
 *    "this is a project".
 * 3. **An unknown kind is drawn as unknown.** The API can add a node type before this page knows
 *    about it; falling back to a labelled "other" node is honest, guessing a category is not.
 */

export type NodeGroup =
  | 'candidate'
  | 'skill'
  | 'project'
  | 'experience'
  | 'education'
  | 'achievement'
  | 'repository'
  | 'evidence'
  | 'claim'
  | 'job'
  | 'interview'
  | 'other';

/** Groups shown as filter toggles, in the order they are read on the canvas. */
export const NODE_GROUPS: { group: NodeGroup; label: string; types: GraphNodeType[] }[] = [
  { group: 'candidate', label: 'Candidate', types: ['candidate'] },
  { group: 'job', label: 'Job', types: ['job'] },
  { group: 'project', label: 'Project', types: ['project'] },
  { group: 'experience', label: 'Experience', types: ['experience'] },
  { group: 'education', label: 'Education', types: ['education'] },
  { group: 'repository', label: 'Repository', types: ['repository'] },
  { group: 'skill', label: 'Skill', types: ['skill'] },
  { group: 'evidence', label: 'Evidence', types: ['repo_file', 'commit', 'document'] },
  { group: 'claim', label: 'Claim', types: ['claim'] },
  { group: 'achievement', label: 'Achievement', types: ['achievement'] },
  { group: 'interview', label: 'Interview', types: ['interview'] },
];

export interface NodeStyle {
  group: NodeGroup;
  /** Short English label used on the node, in the list and in the legend. */
  label: string;
  icon: LucideIcon;
  /** Accent token class for the icon chip. `neutral` means no accent — tertiary text only. */
  accent: 'brand' | 'signal' | 'neutral';
  /** Border weight: the person and the pivot are heavier than the leaves. */
  border: 'strong' | 'default' | 'subtle';
  surface: 'elevated' | 'surface' | 'base';
}

const STYLE_BY_TYPE: Record<string, NodeStyle> = {
  candidate: {
    group: 'candidate',
    label: 'Candidate',
    icon: UserRound,
    accent: 'brand',
    border: 'strong',
    surface: 'elevated',
  },
  job: {
    group: 'job',
    label: 'Job',
    icon: Target,
    accent: 'brand',
    border: 'strong',
    surface: 'elevated',
  },
  project: {
    group: 'project',
    label: 'Project',
    icon: FolderGit2,
    accent: 'signal',
    border: 'default',
    surface: 'surface',
  },
  experience: {
    group: 'experience',
    label: 'Experience',
    icon: Briefcase,
    accent: 'signal',
    border: 'default',
    surface: 'surface',
  },
  education: {
    group: 'education',
    label: 'Education',
    icon: GraduationCap,
    accent: 'signal',
    border: 'default',
    surface: 'surface',
  },
  achievement: {
    group: 'achievement',
    label: 'Achievement',
    icon: Award,
    accent: 'signal',
    border: 'default',
    surface: 'surface',
  },
  repository: {
    group: 'repository',
    label: 'Repository',
    icon: GitBranch,
    accent: 'signal',
    border: 'default',
    surface: 'surface',
  },
  skill: {
    group: 'skill',
    label: 'Skill',
    icon: Cpu,
    accent: 'signal',
    border: 'strong',
    surface: 'surface',
  },
  repo_file: {
    group: 'evidence',
    label: 'File',
    icon: FileCode2,
    accent: 'neutral',
    border: 'subtle',
    surface: 'base',
  },
  commit: {
    group: 'evidence',
    label: 'Commit',
    icon: GitCommitHorizontal,
    accent: 'neutral',
    border: 'subtle',
    surface: 'base',
  },
  document: {
    group: 'evidence',
    label: 'Document',
    icon: FileText,
    accent: 'neutral',
    border: 'subtle',
    surface: 'base',
  },
  claim: {
    group: 'claim',
    label: 'Claim',
    icon: Scale,
    accent: 'neutral',
    border: 'subtle',
    surface: 'base',
  },
  interview: {
    group: 'interview',
    label: 'Interview',
    icon: MessagesSquare,
    accent: 'neutral',
    border: 'subtle',
    surface: 'base',
  },
};

const UNKNOWN_STYLE: NodeStyle = {
  group: 'other',
  label: 'Other',
  icon: CircleHelp,
  accent: 'neutral',
  border: 'subtle',
  surface: 'base',
};

export function nodeStyle(type: string): NodeStyle {
  return STYLE_BY_TYPE[type] ?? UNKNOWN_STYLE;
}

export const ACCENT_CLASS: Record<NodeStyle['accent'], string> = {
  brand: 'text-brand',
  signal: 'text-signal',
  neutral: 'text-tertiary',
};

export const BORDER_CLASS: Record<NodeStyle['border'], string> = {
  strong: 'border-strong border-2',
  default: 'border-default border',
  subtle: 'border-subtle border',
};

export const SURFACE_CLASS: Record<NodeStyle['surface'], string> = {
  elevated: 'bg-elevated',
  surface: 'bg-surface',
  base: 'bg-base',
};

/** The API type a node reports, narrowed for the group lookup. */
export function groupOf(type: string): NodeGroup {
  return nodeStyle(type).group;
}

/* ── confidence ────────────────────────────────────────────────────────────── */

export type ConfidenceBand = 'high' | 'medium' | 'low' | 'none';

/**
 * Bands are the backend's own thresholds (`scoring/confidence.py`: `SUPPORTED` at 0.75,
 * `PARTIALLY_SUPPORTED` at 0.45), not a new scale invented for the picture.
 *
 * `null` is `none`, never `low`: a node with no computed confidence is *unmeasured*, and
 * colouring it red would say something the data does not.
 */
export function confidenceBand(value: number | null | undefined): ConfidenceBand {
  if (value === null || value === undefined) return 'none';
  if (value >= 0.75) return 'high';
  if (value >= 0.45) return 'medium';
  return 'low';
}

export const CONFIDENCE_TEXT_CLASS: Record<ConfidenceBand, string> = {
  high: 'text-evidence',
  medium: 'text-weak',
  low: 'text-danger',
  none: 'text-tertiary',
};

export const CONFIDENCE_BADGE: Record<ConfidenceBand, 'supported' | 'weak' | 'danger' | 'default'> =
  {
    high: 'supported',
    medium: 'weak',
    low: 'danger',
    none: 'default',
  };

/** `0.8` → `0.80`; `null` → an em dash. Never `0.00` for an unmeasured value. */
export function formatConfidence(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return value.toFixed(2);
}

export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return `${Math.round(value * 100)}%`;
}

/* ── the one number on each node ───────────────────────────────────────────── */

export interface NodeReadout {
  /** Rendered value, or `—` when the API has nothing. */
  value: string;
  /** What the number counts, for the tooltip and the accessible name. */
  label: string;
  /** Two-or-three letter unit printed on the card next to the value. */
  metric: string;
  band: ConfidenceBand;
}

export interface NodeFacts {
  evidenceCount: number;
  demonstratedSkills: number;
  requirements: number;
  /** Mean confidence of the evidence behind the node; `null` when none was computed. */
  confidence: number | null;
}

/**
 * Each kind shows the number that decides something about *it*:
 *
 * * a skill shows how many sources back it (the number that turns "I know it" into "it is shown");
 * * an evidence leaf shows its own confidence;
 * * a project / experience / repository shows how many skills it demonstrates;
 * * a job shows how many requirements it states;
 * * the candidate shows how much evidence the current view holds.
 */
export function nodeReadout(node: EvidenceGraphNode, facts: NodeFacts): NodeReadout {
  const style = nodeStyle(node.type);
  switch (style.group) {
    case 'skill':
      return {
        value: String(facts.evidenceCount),
        label: `${facts.evidenceCount} evidence source${facts.evidenceCount === 1 ? '' : 's'}`,
        metric: 'src',
        band: confidenceBand(facts.confidence),
      };
    case 'project':
    case 'experience':
    case 'education':
    case 'achievement':
    case 'repository':
      return {
        value: String(facts.demonstratedSkills),
        label: `${facts.demonstratedSkills} skill${facts.demonstratedSkills === 1 ? '' : 's'} demonstrated`,
        metric: 'skills',
        band: confidenceBand(facts.confidence),
      };
    case 'job':
      return {
        value: String(facts.requirements),
        label: `${facts.requirements} requirement${facts.requirements === 1 ? '' : 's'}`,
        metric: 'req',
        band: confidenceBand(facts.confidence),
      };
    case 'candidate':
      return {
        value: String(facts.evidenceCount),
        label: `${facts.evidenceCount} evidence item${facts.evidenceCount === 1 ? '' : 's'} in this view`,
        metric: 'ev',
        band: confidenceBand(facts.confidence),
      };
    default: {
      const value = facts.confidence ?? node.confidence;
      return {
        value: formatConfidence(value),
        label: value === null ? 'confidence unavailable' : `confidence ${formatConfidence(value)}`,
        metric: 'conf',
        band: confidenceBand(value),
      };
    }
  }
}
