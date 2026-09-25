'use client';

import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  ErrorState,
  Label,
  Textarea,
  Tooltip,
} from '@careerforge/ui';
import { isApiError } from '@careerforge/shared';
import { RefreshCw, Send, SkipForward, Square } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import { SessionContext } from '@/components/interview/session-context';
import { TurnEvaluationPanel } from '@/components/interview/turn-evaluation';
import {
  SKIP_ANSWER,
  formatScore,
  levelLabel,
  statusLabel,
} from '@/components/interview/interview-labels';
import type { InterviewController } from '@/hooks/use-interview';
import type { RecordedTarget } from '@/hooks/use-interview-setup';
import { API_BASE_URL } from '@/lib/api';
import type { InterviewSession } from '@/lib/interview-api';

/**
 * The interview workspace — not a chat.
 *
 * The main column is the question, the answer form and the result of the last answer; the session
 * column is the state that makes the answers legible (difficulty ladder, topics covered, the plan
 * the questions came from, the target role). The narrow layout stacks them, so on a phone the
 * context lands *below* the answer box and the textarea stays where the keyboard is.
 */

export interface InterviewWorkspaceProps {
  session: InterviewSession;
  target: RecordedTarget | null;
  isDemo: boolean;
  controller: InterviewController;
}

const MAX_ANSWER = 8000;

export function InterviewWorkspace({
  session,
  target,
  isDemo,
  controller,
}: InterviewWorkspaceProps) {
  const [answer, setAnswer] = useState('');
  const textarea = useRef<HTMLTextAreaElement>(null);

  const questions = session.turns.filter((turn) => turn.role === 'interviewer');
  const candidates = session.turns.filter((turn) => turn.role === 'candidate');
  const current = questions[questions.length - 1] ?? null;
  const last = candidates[candidates.length - 1] ?? null;
  const history = candidates.slice(0, -1);
  const busy = controller.busy;
  const answering = busy === 'answer';
  const turnFailed = controller.pendingAnswer !== null;

  // After a turn lands, the next question is what the cursor should be on — on a phone that also
  // scrolls the answer box back into view.
  useEffect(() => {
    if (!answering && !turnFailed) textarea.current?.focus();
  }, [current?.turnIndex, answering, turnFailed]);

  async function submit() {
    const text = answer.trim();
    if (!text) return;
    if (await controller.submitAnswer(text)) setAnswer('');
  }

  async function skip() {
    if (await controller.submitAnswer(SKIP_ANSWER)) setAnswer('');
  }

  return (
    <div className="flex flex-col gap-4" data-interview-workspace="">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <h1 className="text-primary flex flex-wrap items-center gap-2 text-lg font-semibold tracking-tight">
            模拟面试
            <Badge variant="outline">{statusLabel(session.status)}</Badge>
            <Badge variant="outline">mode={session.mode}</Badge>
            <Badge variant="signal">{levelLabel(session.currentLevel)}</Badge>
            {isDemo ? <Badge variant="weak">Demo session</Badge> : null}
          </h1>
          <p className="text-tertiary truncate font-mono text-[11px]" title={session.sessionId}>
            GET {API_BASE_URL}/ai/interview/{session.sessionId}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={controller.refetch}
            loading={controller.isFetching}
            aria-label="重新读取会话"
          >
            <RefreshCw className="size-3.5" aria-hidden="true" />
            刷新
          </Button>
          {controller.demoRunning ? (
            <Button variant="secondary" size="sm" onClick={controller.cancelDemo}>
              <Square className="size-3.5" aria-hidden="true" />
              停止演示
            </Button>
          ) : (
            <AbandonDialog onConfirm={controller.abandon} busy={busy === 'finish'} />
          )}
        </div>
      </header>

      {isDemo ? (
        <p className="border-subtle bg-surface text-secondary rounded-md border px-3 py-2 text-[11px] leading-relaxed">
          <span className="text-primary font-medium">Demo session</span>
          ：示例岗位由 POST /jobs/analyze 实时解析，脚本化答案通过 POST /ai/interview/{'{id}'}
          /answer 提交 —— 题目、评价、难度变化与评分卡都由后端状态机产生，不是回放。
          {controller.demoRunning ? ' 正在按脚本推进，每轮之间间隔约 1.2 秒。' : ''}
        </p>
      ) : null}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,20rem)]">
        <div className="flex min-w-0 flex-col gap-4">
          {turnFailed ? (
            <ErrorState
              title="本轮回答没有提交成功"
              error={controller.actionError}
              code={isApiError(controller.actionError) ? controller.actionError.code : 'UNKNOWN'}
              requestId={
                isApiError(controller.actionError) ? controller.actionError.requestId : null
              }
              onRetry={controller.retryTurn}
              retryLabel="重试这一轮"
              retrying={answering}
              statusHref="/system"
              details={
                <p className="leading-relaxed">
                  会话没有丢失：已经答完的轮次、难度和题目计划都还在（下面显示的就是后端最后一次确认的状态）。
                  重试前会先重新读取会话，如果那次请求其实已经成功，就不会重复提交同一段回答。
                </p>
              }
            />
          ) : controller.actionError ? (
            <ErrorState
              title="操作失败"
              error={controller.actionError}
              code={isApiError(controller.actionError) ? controller.actionError.code : 'UNKNOWN'}
              requestId={
                isApiError(controller.actionError) ? controller.actionError.requestId : null
              }
              onRetry={controller.clearActionError}
              retryLabel="知道了"
              statusHref="/system"
              details={
                <p className="leading-relaxed">
                  会话仍在进行中（下面显示的就是后端最后一次确认的状态）：可以继续手动回答，或直接「结束面试」生成评分卡。
                  Demo session 连续调用 AI 端点，若触发 20 次/分钟的限额，等一分钟后重开会话即可。
                </p>
              }
            />
          ) : null}

          <Card className="min-w-0">
            <CardHeader>
              <div className="flex flex-wrap items-center gap-2">
                <CardTitle>第 {questions.length} 题</CardTitle>
                {current?.level ? (
                  <Badge variant="signal">{levelLabel(current.level)}</Badge>
                ) : null}
                {current?.topic ? <Badge variant="outline">{current.topic}</Badge> : null}
              </div>
              <CardDescription>
                计划 {session.plan.length} 个主题 · 当前难度 {levelLabel(session.currentLevel)} ·
                数据来自后端状态机
              </CardDescription>
            </CardHeader>
            <CardContent>
              {current ? (
                <p className="text-primary text-sm leading-relaxed" data-question="">
                  {current.content}
                </p>
              ) : (
                <p className="text-secondary text-sm">
                  本次会话还没有题目纪录 —— 后端未返回面试官轮次。
                </p>
              )}
            </CardContent>
          </Card>

          <Card className="min-w-0">
            <CardHeader>
              <CardTitle>你的回答</CardTitle>
              <CardDescription>
                提交后由后端评估并推进到下一题；<span className="font-mono">Enter</span>{' '}
                换行，不做自动发送。
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <Label htmlFor="interview-answer" className="sr-only">
                你的回答
              </Label>
              <Textarea
                id="interview-answer"
                ref={textarea}
                rows={6}
                value={answer}
                maxLength={MAX_ANSWER}
                disabled={answering || controller.demoRunning}
                onChange={(event) => setAnswer(event.target.value)}
                placeholder="写下你的思路、取舍和验证方式。答案越长越具体，评估里的缺失要点越少。"
              />
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  onClick={submit}
                  loading={answering && !turnFailed}
                  disabled={!answer.trim() || controller.demoRunning || busy === 'demo'}
                >
                  <Send className="size-3.5" aria-hidden="true" />
                  提交回答
                </Button>
                <Tooltip content="后端没有单独的跳过接口：跳过会以「未作答」提交，由评估器打分并推进到下一题。">
                  <Button
                    variant="secondary"
                    onClick={skip}
                    disabled={controller.demoRunning || busy !== null}
                  >
                    <SkipForward className="size-3.5" aria-hidden="true" />
                    跳过
                  </Button>
                </Tooltip>
                <Tooltip content="POST /ai/interview/{id}/finish —— 停止提问并生成七维评分卡。">
                  <Button
                    variant="outline"
                    onClick={controller.finish}
                    loading={busy === 'finish'}
                    disabled={controller.demoRunning || busy === 'answer'}
                  >
                    结束面试
                  </Button>
                </Tooltip>
                <span className="text-tertiary ml-auto font-mono text-[11px] tabular-nums">
                  {answer.length} / {MAX_ANSWER}
                </span>
              </div>
            </CardContent>
          </Card>

          {last ? (
            <TurnEvaluationPanel
              evaluation={last.evaluation ?? null}
              change={last.difficultyChange ?? null}
              scoreOnly={last.score}
              label={`第 ${Math.max(1, questions.length - 1)} 题的回答`}
            />
          ) : (
            <p className="text-tertiary px-1 text-[11px]">
              还没有已回答的轮次，因此没有评价可显示（不显示占位分数）。
            </p>
          )}

          {history.length > 0 ? (
            <details className="border-default bg-surface rounded-lg border">
              <summary className="text-secondary cursor-pointer px-4 py-3 text-xs">
                对话记录（已回答 {candidates.length} 轮 / 已问 {questions.length} 题）
              </summary>
              <div className="flex flex-col gap-3 px-4 pb-4">
                {history.map((turn, index) => (
                  <div key={turn.turnIndex} className="flex flex-col gap-1">
                    <p className="text-secondary flex flex-wrap items-center gap-2 text-[11px]">
                      <span className="font-mono">#{index + 1}</span>
                      {turn.topic ? <Badge variant="outline">{turn.topic}</Badge> : null}
                      <span>
                        得分{' '}
                        <span className="text-primary font-mono tabular-nums">
                          {formatScore(turn.score)}
                        </span>
                      </span>
                      {turn.difficultyChange &&
                      turn.difficultyChange.fromLevel !== turn.difficultyChange.toLevel ? (
                        <span className="text-signal">
                          难度 {levelLabel(turn.difficultyChange.fromLevel)} →{' '}
                          {levelLabel(turn.difficultyChange.toLevel)}
                        </span>
                      ) : null}
                    </p>
                    <p className="text-tertiary line-clamp-2 text-[11px] leading-relaxed">
                      {turn.content}
                    </p>
                    {turn.evaluation?.feedback ? (
                      <p className="text-secondary text-[11px] leading-relaxed">
                        {turn.evaluation.feedback}
                      </p>
                    ) : null}
                  </div>
                ))}
                <p className="text-tertiary text-[11px] leading-relaxed">
                  GET /ai/interview/{'{id}'} 的每轮只保留
                  score，所以刷新后这里只有得分；完整评价在评分卡的逐题复盘里。
                </p>
              </div>
            </details>
          ) : null}
        </div>

        <SessionContext session={session} target={target} />
      </div>
    </div>
  );
}

/** `DELETE /ai/interview/{id}` behind a named dialog — abandoning is irreversible. */
function AbandonDialog({ onConfirm, busy }: { onConfirm: () => void; busy: boolean }) {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="ghost" size="sm">
          放弃会话
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>放弃这次会话</DialogTitle>
          <DialogDescription>
            调用 DELETE /ai/interview/{'{id}'}，会话会从后端进程内存储中移除，链接无法再恢复。
            想保留成绩的话，请先「结束面试」生成评分卡。
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="secondary" size="sm">
              保留会话
            </Button>
          </DialogClose>
          <DialogClose asChild>
            <Button variant="danger" size="sm" loading={busy} onClick={onConfirm}>
              放弃并离开
            </Button>
          </DialogClose>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
