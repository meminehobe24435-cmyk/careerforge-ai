# Interview notes

How to talk about this project, in the order an interviewer usually asks. Every number is
reproducible from the repository — that is the point of the file.

---

## 60-second version

> CareerForge AI is a job-search platform built around one idea: **a sentence goes onto your résumé
> only if your own evidence supports it.** So the interesting engineering is not the chatbot, it is
> the gate. Claims are checked in a fixed order — deterministic rules, then retrieval over your
> repository and documents, then a model verdict, then arithmetic — and the model never produces a
> number, only a judgement that the arithmetic then weighs.
>
> I evaluated it the way you would a model: 242 cases across four suites (JD extraction, claim
> validation, RAG retrieval, interview relevance), plus confidence calibration. The evaluation found
> real defects — it showed the gate accepting 10% of unsupported claims, and the two causes were
> both fixable in the decision policy. It now accepts 5%, and the fabricated-number rate is zero.
>
> Everything runs with no API key: the default provider is a deterministic rule engine, so CI,
> 1,025 tests and 11 end-to-end flows all pass for free.

## 3-minute version

Add: the four-layer test strategy and what each layer uniquely caught (`docs/QUALITY.md` §1);
the ADRs that shaped it (the model produces no numbers — ADR-014; the provider chain always ends at
heuristic — ADR-009); the honest gaps (unsafe support 0.05, structured-output tokens, two
scope-inflation cases) and why they are not fixed yet.

---

## Q1 — Why does an AI feature need an evaluation at all?

Because "it looked right when I tried it" is not a property, it is an anecdote. Three things
change once you have a suite:

1. **You find out what the system gets wrong.** Ours accepted 10% of unsupported claims. I would
   not have guessed that number, and I could not have fixed the cause without it.
2. **You can tell a fix from a regression.** `python evals/compare.py baseline current` classifies
   every metric as improved/same/regressed, with the direction declared per metric (for calibration
   error, lower is better — an assumption baked into code rather than into someone's head).
3. **You can ship a threshold.** A gate is only meaningful if a number can fail it: fabricating a
   measurement, or calling an unsupported claim supported, exits non-zero.

The nuance I would emphasise: quality thresholds are _reported_, safety thresholds _gate_. A
threshold quietly lowered until it always passes converts an honest gap into a green check, which
is worse than having no threshold at all.

## Q2 — How do you judge RAG retrieval quality?

Four metrics, because each answers a different question, and they disagree in a useful way:

- **Hit@k** — did a relevant document come back at all (the user's question);
- **Recall@5** — what share of the relevant set came back (a query can be Hit@5 with one of four
  relevant documents, and Hit@k alone would never notice);
- **MRR** — is the first relevant hit near the top (a UI that shows three results cares);
- **per-arm breakdown** — hybrid vs BM25-only vs dense-only, so a fusion change can be attributed.

Current numbers on a 59-query corpus with construction-known relevance: Hit@1 0.8475, Hit@3
0.9661, Hit@5 0.9661, MRR 0.9011. And the finding I volunteer: **keyword-only beats the hybrid on
this corpus** (0.9831 vs 0.9661), one fusion loss and zero wins. The tempting move is to tune the
RRF weights until it looks better; on 59 queries that is overfitting with extra steps, so it is
reported.

## Q3 — What does "confidence 80%" mean in your system?

It is arithmetic, not a model output. Five factors with fixed weights — authority 0.30, recency
0.15, specificity 0.20, corroboration 0.20, extraction 0.15 — combined in
`careerforge_ai/scoring/confidence.py`, mirrored by a database `CHECK` so a value that bypasses the
function cannot be stored. The model is explicitly _forbidden_ from producing it
(`ClaimLLMVerdict` has no confidence field), because a language model asked how confident it is
will answer.

What it means operationally: ≥0.75 **and** at least two independent evidence _kinds_ ⇒ supported;
≥0.45 ⇒ partially supported; below ⇒ unsupported. One confident source is still one source.

## Q4 — What is calibration, and why did you measure it?

Calibration asks whether the stated confidence matches the observed frequency: of everything the
system called 0.8, was it right about 80% of the time? Accuracy alone cannot answer that — a system
can be 88% accurate and systematically over-confident.

I bucket the 60 evidence cases by predicted confidence and compare mean confidence with actual
accuracy, then compute ECE (sample-weighted mean gap) and Brier score (mean squared error).
Measured: **ECE 0.0166, Brier 0.1034**, with 45 cases in the 0.8–0.9 bucket calibrated to within
0.001 and the 0.9–1.0 bucket over-confident by 0.063. The top bucket is where the interesting
failure lives, so it is the one I quote.

## Q5 — Why not just report accuracy?

Because the two error directions are not equally bad, and accuracy averages them away. On the
60-case claim set: accuracy 0.8833, macro F1 0.8306 — and 12 of the 60 cases are judged
_unsupported_ where I labelled them _partially supported_, which is the gate being conservative.
Averaging that in with "an invented achievement was accepted" hides the only asymmetry that
matters. So the report carries a full confusion matrix and three separate rates.

## Q6 — Why single out unsupported claims?

Because it is the only error direction that harms the user. A false negative — "we could not
confirm this" — costs the candidate a review: they add a link and move on. A false positive writes
an invented achievement onto their CV, in their own voice, and they may never know.

Measured today: `unsafe_support_rate 0.0500` (2 of 40), `unsafe_numeric_support_rate 0.0000`
(0 of 4 fabricated measurements), and **zero** of the 31 unsupported cases promoted to _supported_
in the confusion matrix. The residual 0.05 is scope inflation over real work, named case by case in
`reports/README.md`, with the countermeasure I have not built.

## Q7 — How do you stop an AI résumé writer from making things up?

Five mechanisms, in order of cost:

1. **Deterministic rules before any model** — a quantified claim whose unit family appears nowhere
   in the evidence is rejected without a token being spent; a technical noun the material never
   mentions is flagged.
2. **Retrieval over the candidate's own material**, with corroboration counted by evidence _kind_
   (a file and a commit are independent; two files in one repository are not).
3. **A model verdict that may only judge support**, never confidence and never a number.
4. **Arithmetic for the status**, in one function used by the graph, the API and the validator.
5. **A rewrite that refuses to soften.** A contradicted claim gets no rewrite at all, and a
   fabricated number gets one only if removing the number leaves nothing unsupported behind —
   keeping "Kubernetes" while deleting "300%" would assert the same unsupportable thing with the
   evidence of the edit hidden.

## Q8 — Unit test, integration test, end-to-end — where do you draw the line?

By _what the layer can physically observe_:

- unit — pure logic, no I/O. Arithmetic, rules, fusion, tokenisation.
- integration — the HTTP contract as shipped: envelope, auth, ownership, migrations, failure
  injection, cost aggregation. Real database, real provider chain.
- component — rendering decisions in jsdom: "null is not 0", keyboard coordinates, runtime guards.
- end-to-end — anything requiring a browser: layout, stacking order, real CORS, real session,
  real page.

Not a hierarchy of value but a division of observability. A component test cannot see a 375 px
overflow; a browser test cannot cheaply enumerate 500 rule-layer edge cases.

## Q9 — What has your test suite actually caught that you would not have found otherwise?

Three concrete ones, all from PHASE 11–12, and each invisible to the layers below it:

1. **A 375 px table that pushed cost, status and time off-screen.** 143 passing component tests,
   because jsdom has no layout engine. Found by the first real-browser screenshot.
2. **A browser-origin request the API refused.** The 25-check Node smoke suite passed — Node's
   `fetch` does not enforce CORS. Found by driving the real browser; the fix was a correctly
   declared origin, not a wildcard.
3. **A mobile drawer rendered _below_ its own overlay**, so every tap was intercepted. DOM tests
   were green (the element exists and is visible in jsdom terms); the 375 px end-to-end run could
   not click it. Found by the opt-in mobile project, then fixed by moving both layers to the
   drawer's z-index.

And two the _evaluation_ caught in the product, which no amount of ordinary testing would have:
scope-inflated claims being accepted as fully supported, and the gate softening model-reported
blockers because retrieval returned _some_ document. Both were fixed in the decision policy; both
are now regression-tested.

The meta-lesson I would state out loud: **each test layer has a blind spot that looks like
coverage.** If I had stopped at "1,025 tests pass", I would have shipped all three UI defects.

---

## Numbers to have ready

|                       |                                                                                                                  |
| --------------------- | ---------------------------------------------------------------------------------------------------------------- |
| tests                 | 1,025 (504 AI core · 348 API · 143 web · 11 E2E · 19 metrics)                                                    |
| eval                  | 4 suites · 242 cases · 39 metrics · all gates pass in 763 ms                                                     |
| claim gate            | accuracy 0.8833 · macro F1 0.8306 · unsafe support 0.0500 · numeric unsafe 0.0000                                |
| retrieval             | Hit@1 0.8475 · Hit@5 0.9661 · MRR 0.9011                                                                         |
| calibration           | ECE 0.0166 · Brier 0.1034                                                                                        |
| coverage              | core domain 91.9% (claim gate 95.0 · matching 96.2 · RAG 91.2 · parsing 95.7 · interview 94.3 · accounting 80.7) |
| cost to run all of it | **$0** — the default provider is deterministic and keyless                                                       |
