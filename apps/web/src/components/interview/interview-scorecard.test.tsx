import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { InterviewScorecardView } from '@/components/interview/interview-scorecard';
import { DIMENSION_KEYS } from '@/components/interview/interview-labels';
import { SESSION_ID, scorecard } from '@/components/interview/interview-fixtures';

/**
 * The scorecard, against the real payload.
 *
 * Three behaviours are load-bearing, and all three exist because the API can be less complete than
 * a dashboard would like:
 *
 * 1. **The dimension list is the payload's list.** All seven keys the backend defines are rendered
 *    with the labels it sent; a shorter payload is reported as short rather than padded with zeros.
 * 2. **`duration_seconds: 0` is shown as unavailable.** The scorecard builder hard-codes it, so
 *    "0s" would be a fabricated measurement — and this project treats `null`/unmeasured as a
 *    distinct thing from zero everywhere.
 * 3. **An unanswered question is not "mixed".** `_scorecard` gives the final, unanswered question
 *    `verdict=mixed`; the row says 未作答 and keeps the raw value visible in mono, so neither the
 *    reader nor a reviewer is misled in either direction.
 */

function renderCard(overrides = {}) {
  const onNewSession = vi.fn();
  render(
    <InterviewScorecardView
      scorecard={scorecard(overrides)}
      sessionId={SESSION_ID}
      isDemo={false}
      onNewSession={onNewSession}
    />,
  );
  return { onNewSession };
}

describe('the scorecard', () => {
  it('renders every dimension key the backend defines, with its own label', () => {
    renderCard();

    for (const key of DIMENSION_KEYS) {
      expect(screen.getByText(key)).toBeInTheDocument();
    }
    for (const label of ['技术准确性', '表达沟通', '技术深度', '问题解决', '工程思维', '自信度']) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    // `证据一致性` is both a dimension label and the cross-check card's title.
    expect(screen.getAllByText('证据一致性').length).toBeGreaterThan(0);
    expect(screen.getByText('66.9')).toBeInTheDocument();
    expect(screen.getByText('scorecard@1.0.0')).toBeInTheDocument();
    expect(screen.getByText('口述内容与证据图谱一致')).toBeInTheDocument();
  });

  it('reports a short dimension list instead of padding it with zeros', () => {
    renderCard({ dimensions: scorecard().dimensions.slice(0, 5) });

    expect(screen.getByText(/缺少/)).toBeInTheDocument();
    expect(screen.getByText(/confidence \/ evidence_consistency/)).toBeInTheDocument();
    // Nothing invented for the missing two.
    expect(screen.queryByText('自信度')).toBeNull();
  });

  it('shows the hard-coded duration as unavailable, not as 0 seconds', () => {
    renderCard();

    expect(screen.getByText('不可用')).toBeInTheDocument();
    expect(screen.queryByText('0s')).toBeNull();
    expect(screen.getByText(/这不是「耗时 0 秒」的测量值/)).toBeInTheDocument();
  });

  it('marks the unanswered question as unanswered while keeping the raw verdict', () => {
    renderCard();

    // The answered question is judged on the API's verdict…
    const answered = screen.getByText(/turn_index=0 · verdict=strong/).closest('details');
    expect(answered).not.toBeNull();
    expect(within(answered as HTMLElement).getByText('强')).toBeInTheDocument();

    // …and the one nobody answered says so, with `verdict=mixed` still on screen.
    const unanswered = screen.getByText(/turn_index=2 · verdict=mixed/).closest('details');
    expect(unanswered).not.toBeNull();
    expect(within(unanswered as HTMLElement).getByText('未作答')).toBeInTheDocument();
    expect(
      within(unanswered as HTMLElement).getByText('本次会话没有这道题的回答记录'),
    ).toBeInTheDocument();
  });

  it('lists strengths, gaps and follow-ups, and says when a list is empty', () => {
    renderCard({ strengths: [], weaknesses: [], followUpTopics: [] });

    expect(screen.getByText(/各轮评价没有给出 strong_points/)).toBeInTheDocument();
    expect(screen.getByText(/没有低于 45 分的轮次/)).toBeInTheDocument();
    expect(screen.getByText(/各轮评价没有给出追问方向/)).toBeInTheDocument();
  });

  it('renders evidence conflicts as conflicts, with severity and advice', () => {
    renderCard({
      evidenceConflicts: [
        {
          statement: '我用过 Kafka 做订单链路解耦',
          evidenceState: '你在回答中提到了这些技术，但证据图谱中没有支撑材料：kafka',
          severity: 'medium',
          advice: '面试前补齐相关代码或文档，或调整表述范围',
        },
      ],
    });

    expect(screen.getByText(/severity=medium（中）/)).toBeInTheDocument();
    expect(screen.getByText(/我用过 Kafka 做订单链路解耦/)).toBeInTheDocument();
    expect(screen.getByText(/证据图谱中没有支撑材料/)).toBeInTheDocument();
  });

  it('offers the way out: start a new session', async () => {
    const { onNewSession } = renderCard();
    await userEvent.click(screen.getByRole('button', { name: '开始新的会话' }));
    expect(onNewSession).toHaveBeenCalledTimes(1);
  });
});
