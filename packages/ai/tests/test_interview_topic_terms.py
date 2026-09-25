"""The interview evaluator must receive the topic, not just be *told* about it in the prompt.

``handlers_interview._TOPIC_TERMS`` is a topic-keyed vocabulary: an answer about FreeRTOS is
expected to mention priorities, queues, scheduling and semaphores, and the deterministic evaluator
scores coverage of those terms. The topic was passed to the evaluator as a **prompt variable**, which
a language model reads and a deterministic handler does not — so on the zero-key path the vocabulary
was unreachable and the same answer scored 5/7 through the API versus 12/14 in a direct call.

PHASE 13's interview page surfaced it; these two tests are the regression. The first is the plumbing
(topic in ``context``), the second the observable consequence (topic words earn credit), because a
fix that restores the plumbing without changing the score would mean the plumbing was not the
problem.
"""

from __future__ import annotations

from careerforge_ai.agents.interview import InterviewAgent
from careerforge_ai.providers.heuristic.handlers_interview import evaluate_turn
from careerforge_ai.schemas.common import InterviewMode

#: An answer that covers the FreeRTOS vocabulary: 任务/优先级/队列/信号量/中断.
_TOPIC_ANSWER = (
    "我在项目里按优先级划分任务，用队列在任务和中断之间传递数据，并用信号量保护共享资源。"
)

#: An answer of the same length that covers none of it.
_PLAIN_ANSWER = (
    "我把这部分做完了，过程比较顺利，中间也遇到过一些问题，后来都解决了，整体效果还可以。"
)


def test_the_topic_vocabulary_changes_the_score() -> None:
    """The handler applies the vocabulary only when the topic reaches it."""
    without_topic = evaluate_turn(_TOPIC_ANSWER, {"answer": _TOPIC_ANSWER})
    with_topic = evaluate_turn(_TOPIC_ANSWER, {"answer": _TOPIC_ANSWER, "topic": "free_rtos"})

    assert with_topic.strong_points, "a topic answer must earn credit for its topic terms"
    assert with_topic.technical_accuracy > without_topic.technical_accuracy
    # And an answer with no topic terms must not be rewarded for one it never mentioned: the
    # vocabulary is a check, not a bonus for the topic being hard.
    plain_with_topic = evaluate_turn(_PLAIN_ANSWER, {"answer": _PLAIN_ANSWER, "topic": "free_rtos"})
    assert plain_with_topic.technical_accuracy < with_topic.technical_accuracy


async def test_a_workflow_turn_scores_with_its_topic(iv_exec, iv_job, iv_profile, iv_graph) -> None:
    """End to end through the agent: the answer's evaluation reflects the planned topic."""
    agent = InterviewAgent()
    started = await agent.start(
        iv_exec,
        mode=InterviewMode.TECHNICAL,
        job=iv_job,
        profile=iv_profile,
        graph=iv_graph,
    )
    session = started.value
    assert session is not None and session.turns, "the session must open with a question"

    answered = await agent.answer(
        iv_exec,
        session=session,
        answer=_TOPIC_ANSWER,
        job=iv_job,
        profile=iv_profile,
        graph=iv_graph,
    )
    updated = answered.value
    assert updated is not None

    # The evaluated turn is the answer's; the next question was appended after it.
    evaluations = [turn.evaluation for turn in updated.turns if turn.evaluation is not None]
    assert evaluations, "answering must produce an evaluation"
    evaluation = evaluations[0]
    assert evaluation is not None
    # Strong points come from expected-term hits, so a non-empty list is evidence that the
    # topic-keyed vocabulary reached the evaluator through the workflow, not only in isolation.
    assert evaluation.strong_points or evaluation.missing_knowledge, (
        "the evaluator reported neither strengths nor gaps: the expected-term vocabulary did not "
        "reach it, which is how the topic was silently dropped before"
    )
