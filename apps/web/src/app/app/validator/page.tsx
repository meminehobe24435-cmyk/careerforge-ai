import type { Metadata } from 'next';

import { ValidatorView } from '@/components/validator/validator-view';

export const metadata: Metadata = {
  title: 'Resume Claim Validator',
  description:
    'Check whether a resume statement is actually supported by your evidence: the verdict, the confidence, the cited sources, the rules that fired and an evidence-safe rewrite.',
};

/** `/app/validator` — the gate runs server-side via `POST /evidence/validate` (React Query). */
export default function ValidatorPage() {
  return <ValidatorView />;
}
