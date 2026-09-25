import type { Metadata } from 'next';

import { InterviewView } from '@/components/interview/interview-view';

export const metadata: Metadata = {
  title: '模拟面试',
  description:
    '用真实岗位要求驱动的自适应面试：逐题提问与评估、按得分调整难度，最后生成七维评分卡。全部数字来自 /ai/interview/*。',
};

/**
 * `/app/interview` — the session id lives in `?session=<id>`, so a refresh resumes
 * (`GET /ai/interview/{id}`) instead of starting over.
 */
export default function InterviewPage() {
  return <InterviewView />;
}
