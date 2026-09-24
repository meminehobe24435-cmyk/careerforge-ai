/**
 * 9. Public candidate page — part of the frozen client contract.
 *
 * Split out of `types.ts` when that file crossed the 500-line guard; the split is by
 * domain, and `types.ts` re-exports every one of these so importers do not care.
 */

/* ------------------------------------------------------------------ *
 * 9. Public candidate page (API.md §2.13, PRD FR-16)
 * ------------------------------------------------------------------ */

/**
 * One citation behind a public skill.
 *
 * `url` is present only when the material is linkable by a stranger — a local file path is not
 * a link, and the API omits it rather than publishing a path nobody can open.
 */
export interface PublicEvidence {
  evidenceId: string;
  title: string;
  kind: string;
  locator: string;
  url: string | null;
  confidence: number;
}

export interface PublicSkill {
  canonicalId: string;
  displayName: string;
  category: string;
  confidence: number;
  evidenceCount: number;
  corroboration: number;
  /** Empty when the candidate keeps citations private; `evidenceCount` still says they exist. */
  evidence: PublicEvidence[];
}

export interface PublicProject {
  name: string;
  role: string | null;
  summary: string;
  techStack: string[];
  repositoryUrl: string | null;
  highlights: string[];
}

export interface PublicProfileMeta {
  slug: string;
  generatedAt: string | null;
  evidenceCoverage: number;
  profileStrength: number;
  /** Sections the candidate has hidden, so the page can say so instead of showing less. */
  hiddenSections: string[];
  redactions: Record<string, string>[];
  viewCount: number;
}

/** `data` of `GET /public/candidate/{slug}` — everything a stranger may see. */
export interface PublicProfileResponse {
  displayName: string;
  headline: string;
  location: string | null;
  summary: string;
  targetRoles: string[];
  skills: PublicSkill[];
  projects: PublicProject[];
  highlights: string[];
  interviewTopics: string[];
  githubUrl: string | null;
  websiteUrl: string | null;
  contact: Record<string, string>;
  meta: PublicProfileMeta;
}

export interface PublicPiiFinding {
  kind: string;
  masked: string;
  field?: string;
}

/** `data` of `GET /public/settings` — the owner's own view. */
export interface PublicSettingsResponse {
  slug: string | null;
  url: string | null;
  isPublished: boolean;
  publishedAt: string | null;
  viewCount: number;
  sections: Record<string, boolean>;
  hiddenSkills: string[];
  canPublish: boolean;
  piiFindings: Record<string, unknown>[];
}
