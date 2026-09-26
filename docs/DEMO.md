# Three-minute demo script

For a live walkthrough (screen share or in person). Timings are targets, not rules; the order is the
argument. Everything here runs on the zero-key deterministic provider — **no API key, no spend, no
network flakiness** — which is why it can be run on any machine, twice in a row, with the same
result.

**Before you start:** `docker compose up` (or the two commands in README's Quick Start), open
`http://localhost:3000`, and sign in with the demo account. Have the JD text from §Appendix on your
clipboard. Close your other tabs — the graph deserves the whole screen.

---

## 00:00 — Dashboard: the claim

**Say:** _"This is a career platform, but the interesting part is not that it uses an LLM. It's that
every sentence it writes about you has to be traceable to evidence you actually have. So instead of
opening with a chat box, it opens with an evidence ledger."_

Point at Profile Strength and Evidence Coverage, then the recent jobs row. Do **not** click through
the stat cards — they are a summary, not the product.

## 00:20 — Jobs: what the role actually asks for

Open **Jobs**, click **Load demo JD**, then **Analyze**.

**Say:** _"Parsing a JD is table stakes. What matters is the three-way distinction: the skills the
role requires, the ones I can actually back with evidence, and the ones we don't know about yet.
That third category is where most tools quietly guess."_

When it lands, click **Why 84%?**.

**Say:** _"The score is not a model's opinion. It's five weighted dimensions — skills 40%,
experience 25%, projects 20%, education 5%, evidence strength 10% — and each one shows its own
arithmetic. The LLM never produces a number in this system; it produces a judgement that the
arithmetic then weighs."_

Point at a **Matched** skill with its evidence count, then at an **Unknown** one.

**Say:** _"Matched, Partial, Missing, Unknown — four different things. 'We have no evidence' is not
the same as 'you don't have it', and collapsing them is how a tool starts lying to you."_

## 00:50 — Evidence Graph: the hero

Click any skill → it opens `/app/evidence-graph?skill=…` with that node focused and its drawer open.

**Say:** _"This is the whole project in one screen. The claim 'I know FreeRTOS' is not a string in a
database — it's connected to the project that used it, the repository that contains it, and the
specific files that evidence it, each with a confidence computed from five factors: who wrote it,
how recent it is, how specific it is, how many independent sources corroborate it, and how it was
extracted."_

Click an **evidence** node and show the drawer: source type, source, excerpt, confidence, and _why it
matters_.

**Say:** _"A recruiter can click through from a skill to the commit that proves it. That is the
difference between a résumé and a case file."_

Search for `FreeRTOS` — everything else dims.

**Say:** _"Search dims rather than hides, so you never lose the shape of the graph while you look."_

## 01:10 — Validator: where it refuses

Open **Validator**. Click the **Unsupported** demo claim (the one asserting a technology the profile
never mentions), then **Validate**.

**Say:** _"Now the part that actually matters. This sentence reads perfectly. It is also unsupported —
so the gate refuses it, and tells you which rule fired and what evidence would be needed."_

Expand **Why was this rejected?** and point at the rule codes.

**Say:** _"Deterministic rules run before the model: a quantified result with no measurement anywhere
is rejected without spending a token. The model is only asked to judge support — never to produce a
number, never to decide on its own."_

Then run the **Partial** claim and show the suggested rewrite.

**Say:** _"Here the work is real but the wording overstates it — 'led' where the evidence says
'participated'. The rewrite keeps what is true and drops what isn't, and it refuses to soften a
claim by deleting the number while keeping the technology name."_

## 01:40 — Interview: the same standard, applied live

Open **Interview**, click **Demo session** (3–4 turns, ~60 seconds).

**Say:** _"The interview planner works off the same evidence graph, so it asks about what the job
wants and what the evidence shows — and it deliberately probes the gaps it found in the JD analysis.
Difficulty adapts by rule, not by vibes: above 75 it goes deeper, below 45 it steps back."_

Let it finish and show the scorecard.

**Say:** _"It reports dimensions and evidence consistency, not a personality verdict. No 'you're an
excellent candidate' — that sentence would be worthless in a tool meant for decisions."_

## 02:10 — AI Runs: everything above is measurable

Open **AI Runs**. Expand the newest run.

**Say:** _"Every one of those operations is a traced run: agent, workflow, step chain, provider,
prompt version, tokens, latency, cost, and whether it came from cache. This is the part most
AI-feature demos cannot show, because the plumbing was never built."_

Open **Costs** briefly.

**Say:** _"On this deployment the spend is genuinely zero — the provider is a local rule engine — and
the page says so instead of pretending. Point it at DeepSeek and the same page reports real tokens
per agent."_

## 02:40 — `/system`: the honest slide

Scroll to **Evaluation snapshot**.

**Say:** _"And because a demo that only shows the happy path is marketing, here are the real
numbers from the committed evaluation: evidence-validation macro F1 0.83, RAG Hit@5 0.97, and the
one I'd bring up myself — an unsafe support rate of 5%. That is the share of unsupported claims the
gate wrongly accepted. It was 10% before the evaluation found two specific defects in the decision
policy, and I'd rather show you the remaining 5% than hide it."_

**Close with:** _"1,385 tests, four evaluation suites, confidence calibration, and none of it needs
an API key to reproduce. `python evals/run.py` on a fresh clone gives you the same table."_

---

## If you have five minutes instead of three

Insert after 00:50 (the graph): open **Data Analysis** and show the funnel with its Wilson intervals
and the "insufficient sample" labelling — _"the analytics engine refuses to draw a conclusion from
four applications, and says so on the chart"_. Then continue as above.

## If you are asked to go deeper (questions you will get)

| question                                             | the thirty-second answer                                                                                                                                                                                                                        |
| ---------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| "Why not just ask GPT to write the résumé?"          | Because the failure mode is invisible. A generated sentence that sounds right and is false is the one thing a résumé tool must never ship, so generation is gated behind deterministic rules and retrieval, and the gate is evaluated.          |
| "Isn't the graph just a vector DB with extra steps?" | A vector index answers "what is similar"; the graph answers "what supports this claim, and how strongly" — corroboration across independent source kinds, recency, authority, and a path a human can audit.                                     |
| "Your hybrid retrieval is worse than BM25 — why?"    | Because on a 59-query corpus equal-weight RRF loses one query the lexical arm found, and tuning weights on 59 queries is overfitting with extra steps. It is in the report, and the countermeasure is a larger corpus, not a smaller threshold. |
| "Why is confidence 0.8 trustworthy?"                 | Calibration: ECE 0.017, and the 0.8–0.9 bucket is accurate to ±0.001. The top bucket is over-confident by 6 points, which is why it is on the page.                                                                                             |
| "What did your tests actually catch?"                | Three UI defects a thousand passing tests couldn't see (375 px clipping, browser CORS, a drawer under its own overlay), plus two gate defects from the evaluation. The details are in `docs/QUALITY.md` §1 and §5.                              |

---

## Appendix — demo JD (paste this)

```
智远科技 · 嵌入式软件工程师（上海）

岗位职责
1. 负责电机控制固件的开发与调试；
2. 参与 CAN 总线通信协议栈的实现与测试；
3. 配合硬件完成传感器（SPI/I2C）驱动开发。

任职要求
1. 本科及以上学历，电子信息/自动化相关专业；
2. 3 年以上嵌入式开发经验，熟悉 C 语言；
3. 熟悉 STM32 平台，有 FreeRTOS 实际项目经验；
4. 熟悉 CAN、SPI、I2C 等通信协议。

加分项
- 了解 AUTOSAR 架构；
- 有 PID 闭环控制调参经验。
```

Why this JD: it names three things the demo profile genuinely has evidence for (STM32, FreeRTOS,
SPI), one it does not (CAN), and one bonus item that exists nowhere in the profile (AUTOSAR) — so
the Skills panel shows all four states in a single screen, and the Validator's unsupported demo
claim ("led the AUTOSAR architecture design") lines up with what the graph says.
