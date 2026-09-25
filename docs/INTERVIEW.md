# Interview notes

How to talk about this project, in the order an interviewer usually asks. Every number is
reproducible from the repository — that is the point of the file.

**Pick your length**: [30 seconds](#30-second-version) · [60 seconds](#60-second-version) ·
[3 minutes](#3-minute-version) · [5 minutes](#5-minute-version) · then the [question bank](#question-bank).

---

## 30-second version

> CareerForge AI is an **evidence-driven career OS**. Ordinary AI résumé tools generate text straight
> from a prompt; CareerForge first builds your résumé, projects and repositories into an **Evidence
> Graph**, then uses AI for job matching, claim validation and interviews — with every generated
> sentence traceable to evidence you actually have.
>
> To keep the AI from being confidently wrong, I evaluate it independently: evidence F1, an **unsafe
> support rate**, RAG Hit@K and confidence calibration. 1,025 tests, four evaluation suites, and it
> all runs with no API key.

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
heuristic — ADR-009); the evidence-confidence formula (five weighted factors, mirrored by a DB
`CHECK`); the honest gaps (unsafe support 0.05, structured-output tokens, two scope-inflation
cases) and why they are not fixed yet. Walk the demo in `docs/DEMO.md` if you have a screen.

## 5-minute version

Add, after the 3-minute material: the failure-injection approach (a scripted provider that times
out, hangs, 429s, emits malformed JSON, returns the wrong shape, crashes or exhausts a budget — and
what each one proved about degradation); the coverage scope argument (why 91.9% of the _core_ and
not 75% of the _repository_); and the two things you would do next with another week
(the `structured_output` usage envelope, and the `SKILL_NOT_IN_GRAPH` false-positive audit).

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

## Q10 — Why not generate the whole résumé with an LLM?

Because the failure mode is invisible and expensive. A generated sentence that reads well and is
false is the one thing a résumé tool must never produce, and there is no way to notice it by
looking at the output. So generation sits behind a gate (rules → retrieval → model verdict →
arithmetic), the gate is evaluated on 60 hand-labelled cases, and the failure direction it guards
against — accepting an unsupported claim — has its own metric.

The LLM is not removed from the product; it is confined to the part it is good at: judging whether
a given set of evidence supports a given sentence. It never produces a number, never sets a
confidence, and never decides alone.

## Q11 — Why a graph instead of just a vector database?

They answer different questions. A vector index answers _"what text is similar to this text"_. The
graph answers _"what supports this claim, how strongly, and can I audit the path?"_ Corroboration —
the number of **independent** source kinds behind a skill — is a graph property that no embedding
similarity can express: two files in one repository are one source, a file and a commit are two.
Recency, authority and specificity are node attributes that compose along edges. And the answer has
to be clickable: a recruiter can start at "FreeRTOS" and end at the commit that proves it.

The vector store is still there — it is one of the two retrieval arms feeding the graph's evidence
lookup.

## Q12 — Your hybrid retrieval scores worse than BM25. Why didn't you fix it?

Measured on the 59-query corpus: Hit@5 — keyword-only **0.9831**, hybrid **0.9661**, dense-only
0.8983; one fusion loss, zero fusion wins. Equal-weight RRF (k=60) lets a strong lexical hit get
outvoted by a weak dense one on exact-identifier queries.

I did not "fix" it because the honest fixes are structural, not numerical: fit RRF weights (which on
59 queries is overfitting with extra steps), or grow the corpus until the comparison means
something. Both are real work with a real cost, and neither belongs in a phase whose job was to
measure. The number is in `reports/README.md` and in the interview notes — a benchmark you tune
until it flatters you is not a benchmark.

## Q13 — What is the unsafe support rate, and why does it get its own metric?

It is the share of claims that should **not** have been called supported but were — 2 of 40 in the
current corpus, **0.0500**. The symmetric error, refusing to confirm an honest bullet, costs the
candidate a review: they add a link and move on. Accepting an invented achievement writes fiction
onto their CV, in their own voice, and they may never find out.

Accuracy averages those two together; a résumé gate cannot. So the report carries a full confusion
matrix, the fabricated-measurement rate is gated at exactly **0.00**, and the unsupported→supported
cell currently reads **0**.

The number was 0.10 before the evaluation existed in this form. It is now 0.05, and the remaining
two cases are named individually.

## Q14 — Why does confidence need calibration rather than just a threshold?

A threshold answers "is this good enough to ship"; calibration answers "does 0.8 mean 80%". They are
different questions, and only the second one tells you whether the number on screen is information
or decoration.

Measured: **ECE 0.0166**, Brier 0.1034. The 0.8–0.9 bucket is calibrated to ±0.001 across 45 cases;
the 0.9–1.0 bucket is over-confident by 0.063, which is exactly the region a résumé gate operates
in — high confidence, occasional error. ECE alone would have hidden that, so the reliability table is
published beside it.

## Q15 — Why does `structured_output` need to record tokens?

Because most agent work goes through it, and it returned only the parsed schema — the provider's
usage envelope was dropped on the floor. On a paid deployment the cost page would therefore report
zero tokens for every agent while looking authoritative. "Zero" and "we were not told" are different
facts; the fix is a usage envelope with an explicit `unavailable` status, so the UI can print
"unavailable" instead of a number that reads as free.

(This is the kind of defect a correctness test cannot catch: every response was correct, and the
observability was quietly wrong.)

## Q16 — Why does a _failed_ request need a run trace?

Because that is when you need it most. The tracker wrote inside the request transaction, which rolls
back on any exception, so a failed AI request left **no row at all** — contradicting the executor's
own comment that observability is never lost. An operator diagnosing an outage would find an empty
table.

The fix has to survive the rollback (a separate short-lived session, or an explicit nested commit),
and it has to sanitize: no API keys, no auth headers, no full résumé or JD text in the stored error.

## Q17 — Node smoke tests passed 25/25 while the browser was completely blocked. How?

Because Node's `fetch` does not implement CORS — it is a browser security policy, not a server one.
Two origins on different ports are different origins, and the API's `CORS_ORIGINS` listed only the
default dev origin. Every Node-level check was green and every browser request failed.

The regression test now runs from page context, asserts a real authenticated fetch succeeds, and
asserts a non-allowed origin is _not_ granted — including an explicit refusal of `*`, since a
wildcard would make the test pass while disabling the protection it exists to check. It was verified
to fail on a deliberately wrong configuration before being trusted.

## Q18 — And why couldn't jsdom see the drawer covering itself?

Because jsdom has no layout and no stacking context: it knows an element exists and that its styles
say `z-index: 50`, not that another element with `z-index: 60` is painted on top of it and swallows
pointer events. The component test passed, the DOM was correct, and the sidebar was unusable below
768 px.

Only a real browser at 375 px could see it — which is why the mobile Playwright project exists, and
why it was promoted from opt-in to the default CI run after it had already found one real defect.

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
