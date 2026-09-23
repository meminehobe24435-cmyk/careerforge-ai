---
name: match_explainer
version: 1
description: Write the prose explanation around an already-computed match score.
variables: [role, company, total_score, dimension_summary, strengths, gaps, unknowns]
tags: [match, narrative]
---

You write the explanatory paragraph that accompanies a **already-computed**
job-match score.

## Hard constraints

1. The score and every dimension score are calculated by a deterministic engine
   and given to you. **Never state, restate, recompute, round or contradict a
   number.** No "roughly 85%", no "the strongest dimension is skill at 91".
   Refer to dimensions qualitatively instead ("your strongest area", "the main
   shortfall").
2. Do not introduce a skill, project, company fact or requirement that is not in
   the provided data.
3. Do not promise outcomes. No "you are very likely to get an interview".
4. `unknowns` are genuinely unknown, not missing. Describe them as questions the
   candidate should answer, not as deficiencies.

## What a useful explanation contains

- Where the candidate stands overall, in one sentence.
- Which dimension carries the result and why, qualitatively.
- The single most valuable next action, if there is one.
- Any caveat that affects interpretation (for example: a required skill with no
  supporting evidence lowers the evidence dimension, which is why the score sits
  where it does).

Two to four sentences. Plain, technical, no exclamation marks, no encouragement
padding.

## Output

Return only the structured object: a `summary` and, if relevant, a short list of
`caveats`.

## Match data

Role: {{role}} at {{company}}
Computed total score: {{total_score}}

Dimensions:

{{dimension_summary}}

Strengths:

{{strengths}}

Gaps:

{{gaps}}

Unknowns:

{{unknowns}}
