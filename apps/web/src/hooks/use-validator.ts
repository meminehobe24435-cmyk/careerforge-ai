'use client';

import { useMutation, useQuery } from '@tanstack/react-query';

import { queryKeys } from '@/lib/query-keys';
import {
  EVIDENCE_PAGE_LIMIT,
  fetchEvidenceIndex,
  validateClaim,
  type ClaimSection,
  type ValidatedClaim,
} from '@/lib/validator-api';

/**
 * The gate is a `POST`, so it is a mutation: the verdict is the answer to *this* sentence, and
 * caching it by text would let a re-run of the same sentence hide a changed evidence base.
 *
 * `retry: false` on purpose. Every other hook in the app retries once because a read that fails
 * is usually a blip; here the user is watching a button they just pressed, and the page offers an
 * explicit retry with the request id attached. A silent second attempt would also double-charge a
 * gate that stores the claim it validated.
 */
export function useValidateClaim() {
  return useMutation<ValidatedClaim, unknown, { text: string; section?: ClaimSection }>({
    mutationFn: (input) => validateClaim(input),
    retry: false,
  });
}

/**
 * The candidate's evidence, indexed by id.
 *
 * The verdict's citations carry a *relevance* (how well retrieval matched) but no confidence —
 * that number lives on the evidence row. This read is what lets the panel show it instead of
 * leaving a blank where a number belongs, and it is also how the page knows the evidence base is
 * empty rather than merely unmatched.
 */
export function useEvidenceIndex(limit: number = EVIDENCE_PAGE_LIMIT) {
  return useQuery({
    queryKey: queryKeys.validator.evidenceIndex(limit),
    queryFn: () => fetchEvidenceIndex(limit),
    staleTime: 30_000,
    retry: 1,
  });
}
