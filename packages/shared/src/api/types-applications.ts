/**
 * 7. Application tracker — part of the frozen client contract.
 *
 * Split out of `types.ts` when that file crossed the 500-line guard; the split is by
 * domain, and `types.ts` re-exports every one of these so importers do not care.
 */

/* ------------------------------------------------------------------ *
 * 7. Application tracker (API.md §2.9, PRD FR-13)
 * ------------------------------------------------------------------ */

/**
 * The seven board columns, **in the order the board draws them**.
 *
 * Order is part of the contract rather than a UI preference: `GET /applications/board`
 * returns its columns in this sequence, so a status added on the server cannot silently
 * become a column the client does not draw. Chinese labels are copy and live in the app.
 */
export const APPLICATION_STATUSES = [
  'wishlist',
  'applied',
  'oa',
  'interview',
  'final',
  'offer',
  'rejected',
] as const;

export type ApplicationStatus = (typeof APPLICATION_STATUSES)[number];

/** Statuses where nothing further is expected, so a reminder would be noise. */
export const CLOSED_APPLICATION_STATUSES: readonly ApplicationStatus[] = ['offer', 'rejected'];

/**
 * One card.
 *
 * `company` / `role` / `location` / `matchScore` are a **snapshot** taken when the card was
 * created, not a live join onto the posting: deleting a job must not rewrite last month's
 * card. `matchScore` is `null` when no match had been computed — never `0`, because
 * "never scored" and "scored zero" are different facts and only one of them is knowable.
 */
export interface ApplicationCard {
  id: string;
  jobId: string | null;
  resumeVersionId: string | null;
  company: string;
  role: string;
  location: string | null;
  status: ApplicationStatus;
  matchScore: number | null;
  salaryExpectation: string | null;
  notes: string;
  /** Sort key within its column. Re-derived by the server after every write. */
  position: number;
  appliedAt: string | null;
  nextActionAt: string | null;
  archivedAt: string | null;
  createdAt: string | null;
  updatedAt: string | null;
}

/** One status change. The log is append-only; a correction is another row. */
export interface ApplicationEvent {
  id: string;
  fromStatus: ApplicationStatus | null;
  toStatus: ApplicationStatus;
  note: string;
  occurredAt: string | null;
}

export interface ApplicationColumn {
  status: ApplicationStatus;
  items: ApplicationCard[];
}

/** `data` of `GET /applications/board` (API.md §2.9). */
export interface ApplicationBoardResponse {
  columns: ApplicationColumn[];
  /** Cards per status, matching what was returned (archived ones included when asked for). */
  counts: Record<string, number>;
  total: number;
  archived: number;
}

/** `data` of `GET /applications/{id}` — the card plus its history, newest first. */
export interface ApplicationDetail extends ApplicationCard {
  events: ApplicationEvent[];
}

/** One drag result: which column, and where in it. */
export interface ApplicationReorderItem {
  id: string;
  status: ApplicationStatus;
  position: number;
}

export interface ApplicationCreateRequest {
  jobId?: string;
  company?: string;
  role?: string;
  location?: string | null;
  status?: ApplicationStatus;
  salaryExpectation?: string | null;
  notes?: string;
  nextActionAt?: string | null;
  resumeVersionId?: string | null;
}

/**
 * A partial update. There is deliberately no `matchScore` field: a score is evidence, not
 * a claim, and the API refuses the field if a client sends it anyway.
 */
export interface ApplicationUpdateRequest {
  status?: ApplicationStatus;
  company?: string;
  role?: string;
  location?: string | null;
  salaryExpectation?: string | null;
  notes?: string;
  nextActionAt?: string | null;
  appliedAt?: string | null;
  archived?: boolean;
  /** Free text recorded on the status-change event, when there is a status change. */
  note?: string;
}
