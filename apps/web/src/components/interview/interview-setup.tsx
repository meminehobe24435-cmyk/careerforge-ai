'use client';

import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  EmptyState,
  ErrorState,
  Label,
  Skeleton,
  Textarea,
} from '@careerforge/ui';
import { isApiError } from '@careerforge/shared';
import { Bot, Info, Play, Sparkles } from 'lucide-react';
import { useState } from 'react';

import { demoSession } from '@/components/interview/demo-script';
import {
  LEVEL_DESCRIPTION,
  LEVEL_LABEL,
  LEVEL_ORDER,
  MODE_LABELS,
  formatScore,
} from '@/components/interview/interview-labels';
import { useInterviewSetup, useSkillTree } from '@/hooks/use-interview-setup';
import type { InterviewBusy, StartInput } from '@/hooks/use-interview';
import { API_BASE_URL } from '@/lib/api';
import { INTERVIEW_MODES } from '@/lib/interview-api';
import type { InterviewModeValue } from '@/lib/interview-api';

/**
 * `/app/interview` — the setup screen.
 *
 * Everything on it is a real choice the backend honours: the target job decides the topic plan
 * (`_plan_topics`), the mode is `InterviewMode`, and the level is `StartInterviewRequest.difficulty`.
 * There is deliberately **no free-text "focus"** field: `StartInterviewRequest` has no such
 * parameter, so a focus box would be decoration. What replaces it is the selected posting's
 * requirement list — read from `GET /jobs/{id}/skill-tree` — which is what the questions are
 * actually drawn from.
 */

export interface InterviewSetupProps {
  busy: InterviewBusy;
  actionError: unknown;
  onDismissError: () => void;
  onStart: (input: StartInput) => void;
  onDemo: () => void;
}

export function InterviewSetup({
  busy,
  actionError,
  onDismissError,
  onStart,
  onDemo,
}: InterviewSetupProps) {
  const setup = useInterviewSetup();
  const [jobId, setJobId] = useState<string | null>(null);
  const [mode, setMode] = useState<InterviewModeValue>('technical');
  const [difficulty, setDifficulty] = useState(1);
  const [jdText, setJdText] = useState('');
  const skillTree = useSkillTree(jobId);

  const jobs = setup.jobs.data?.items ?? [];
  const total = setup.jobs.data?.total ?? 0;
  const selected = jobs.find((job) => job.id === jobId) ?? setup.lastAnalysed ?? null;
  const capabilities = setup.capabilities.data ?? null;
  const provider = capabilities?.provider ?? null;
  const starting = busy === 'start';
  const demoBusy = busy === 'demo';

  return (
    <div className="flex flex-col gap-5" data-interview-setup="">
      <header className="flex flex-col gap-1">
        <h1 className="text-primary text-lg font-semibold tracking-tight">
          模拟面试{' '}
          <span className="text-tertiary font-mono text-xs font-normal">Interview Simulator</span>
        </h1>
        <p className="text-secondary max-w-3xl text-xs leading-relaxed">
          用真实岗位要求驱动一次自适应面试：后端按岗位技能生成主题计划，逐题提问、逐题评估，
          按得分上下调整难度，最后汇总七维评分卡。所有数字来自 API，界面不补默认值。
        </p>
        <p className="text-tertiary font-mono text-[11px]">
          POST {API_BASE_URL}/ai/interview/start
        </p>
      </header>

      {actionError ? (
        <ErrorState
          title="无法开始会话"
          error={actionError}
          code={isApiError(actionError) ? actionError.code : 'UNKNOWN'}
          requestId={isApiError(actionError) ? actionError.requestId : null}
          onRetry={onDismissError}
          retryLabel="知道了"
          statusHref="/system"
        />
      ) : null}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
        <div className="flex min-w-0 flex-col gap-4">
          <Card className="min-w-0">
            <CardHeader>
              <CardTitle>会话设置</CardTitle>
              <CardDescription>
                目标岗位决定题目计划；模式与起始难度由后端解释，界面只传递，不推断。
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-5">
              {setup.jobs.isPending ? (
                <div className="flex flex-col gap-2">
                  <Skeleton className="h-3 w-20" />
                  <Skeleton className="h-9 w-full" />
                </div>
              ) : null}

              {setup.jobs.error ? (
                <ErrorState
                  title="岗位列表加载失败"
                  error={setup.jobs.error}
                  code={isApiError(setup.jobs.error) ? setup.jobs.error.code : 'UNKNOWN'}
                  requestId={isApiError(setup.jobs.error) ? setup.jobs.error.requestId : null}
                  onRetry={() => void setup.jobs.refetch()}
                  retrying={setup.jobs.isFetching}
                  statusHref="/system"
                />
              ) : null}

              {setup.jobs.data && jobs.length > 0 ? (
                <div className="flex flex-col gap-2">
                  <Label htmlFor="target-job">目标岗位</Label>
                  <select
                    id="target-job"
                    value={jobId ?? ''}
                    onChange={(event) => setJobId(event.target.value || null)}
                    aria-describedby="target-job-hint"
                    className="border-default bg-base text-primary h-9 w-full min-w-0 rounded-md border px-3 text-sm max-md:h-11"
                  >
                    <option value="">— 选择一个已解析岗位 —</option>
                    {jobs.map((job) => (
                      <option key={job.id} value={job.id}>
                        {job.role}
                        {job.company ? ` · ${job.company}` : ''}（必备 {job.requiredCount} · 优先{' '}
                        {job.preferredCount}）
                      </option>
                    ))}
                  </select>
                  <p id="target-job-hint" className="text-tertiary font-mono text-[11px]">
                    GET {API_BASE_URL}/jobs?limit=20 · 本页 {jobs.length} 项 / 账号共 {total} 个岗位
                  </p>
                </div>
              ) : null}

              {setup.jobs.data && jobs.length === 0 ? (
                <EmptyState
                  icon={<Bot className="size-5" />}
                  title="选择一个岗位并开始一次会话"
                  description="Choose a role and start a session. 还没有已解析的岗位（GET /jobs → 0），所以先粘贴一段岗位描述：解析由后端 JobAgent 真实执行，解析结果会入库并成为本次会话的题目依据。"
                  hint={`GET ${API_BASE_URL}/jobs → items: []`}
                />
              ) : null}

              <div className="flex flex-col gap-2">
                <Label htmlFor="jd-text">粘贴岗位描述（解析后加入目标岗位）</Label>
                <Textarea
                  id="jd-text"
                  rows={5}
                  value={jdText}
                  onChange={(event) => setJdText(event.target.value)}
                  placeholder="把招聘网站上的岗位描述整段粘贴进来…"
                  aria-describedby="jd-hint"
                />
                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    loading={setup.isAnalysing}
                    disabled={jdText.trim().length < 20}
                    onClick={async () => {
                      const job = await setup.analyse(jdText);
                      if (job) setJobId(job.id);
                    }}
                  >
                    解析并选择岗位
                  </Button>
                  <span id="jd-hint" className="text-tertiary font-mono text-[11px]">
                    POST {API_BASE_URL}/jobs/analyze · 至少 20 字
                  </span>
                </div>
                {setup.analyseError ? (
                  <ErrorState
                    title="岗位解析失败"
                    error={setup.analyseError}
                    code={isApiError(setup.analyseError) ? setup.analyseError.code : 'UNKNOWN'}
                    requestId={isApiError(setup.analyseError) ? setup.analyseError.requestId : null}
                    onRetry={() => setup.clearAnalyseError()}
                    retryLabel="知道了"
                    statusHref="/system"
                  />
                ) : null}
              </div>

              <fieldset className="flex flex-col gap-3">
                <legend className="text-secondary text-xs font-medium">
                  面试类型（InterviewMode）
                </legend>
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {INTERVIEW_MODES.map((value) => (
                    <label
                      key={value}
                      className="border-default hover:border-strong flex cursor-pointer items-start gap-2 rounded-md border p-3"
                    >
                      <input
                        type="radio"
                        name="interview-mode"
                        value={value}
                        checked={mode === value}
                        onChange={() => setMode(value)}
                        className="accent-brand mt-0.5 size-4"
                      />
                      <span className="flex min-w-0 flex-col gap-0.5">
                        <span className="text-primary flex items-center gap-2 text-sm">
                          {MODE_LABELS[value].label}
                          <Badge variant="outline">mode={value}</Badge>
                        </span>
                        <span className="text-tertiary text-[11px] leading-relaxed">
                          {MODE_LABELS[value].note}
                        </span>
                      </span>
                    </label>
                  ))}
                </div>
                <p className="text-tertiary text-[11px] leading-relaxed">
                  不提供 Mixed：后端 <span className="font-mono">InterviewMode</span> 没有 mixed
                  取值。
                  {provider === 'heuristic'
                    ? ' 当前 provider=heuristic：只有 hr 模式有独立题库，其余模式共用按主题分级的题库；模式差异在模型路径才生效。'
                    : ''}
                </p>
              </fieldset>

              <fieldset className="flex flex-col gap-3">
                <legend className="text-secondary text-xs font-medium">起始难度</legend>
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                  {LEVEL_ORDER.map((level, index) => (
                    <label
                      key={level}
                      className="border-default hover:border-strong flex cursor-pointer items-start gap-2 rounded-md border p-3"
                    >
                      <input
                        type="radio"
                        name="start-difficulty"
                        value={index + 1}
                        checked={difficulty === index + 1}
                        onChange={() => setDifficulty(index + 1)}
                        className="accent-brand mt-0.5 size-4"
                      />
                      <span className="flex min-w-0 flex-col gap-0.5">
                        <span className="text-primary text-sm">{LEVEL_LABEL[level]}</span>
                        <span className="text-tertiary text-[11px]">
                          {LEVEL_DESCRIPTION[level]}
                        </span>
                      </span>
                    </label>
                  ))}
                </div>
                <p className="text-tertiary text-[11px]">
                  后端从该层开始，每答完一题按得分上下调整一层（≥75 提升，≤45 回退）。
                </p>
              </fieldset>

              <div className="flex flex-wrap items-center gap-2">
                <Button
                  onClick={() => selected && onStart({ jobId: selected.id, mode, difficulty })}
                  disabled={!selected || busy !== null}
                  loading={starting}
                >
                  <Play className="size-3.5" aria-hidden="true" />
                  开始面试
                </Button>
                <Button
                  variant="secondary"
                  onClick={onDemo}
                  loading={demoBusy}
                  disabled={busy !== null && !demoBusy}
                  data-demo-start=""
                >
                  <Sparkles className="size-3.5" aria-hidden="true" />
                  Demo session（示例会话）
                </Button>
                {!selected ? (
                  <span className="text-tertiary text-[11px]">先选择或解析一个目标岗位。</span>
                ) : null}
              </div>
            </CardContent>
          </Card>

          <Card className="min-w-0">
            <CardHeader>
              <CardTitle>Demo session 是什么</CardTitle>
              <CardDescription>
                不是录播，也不是假会话：示例岗位会被真实解析，3 段脚本化答案通过同一个
                <span className="font-mono"> POST /ai/interview/{'{id}'}/answer </span>
                提交，难度变化与评分卡都由后端状态机产生。
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-2">
              <ol className="text-secondary flex flex-col gap-1 text-xs leading-relaxed">
                {demoSession.outline.map((line) => (
                  <li key={line} className="flex gap-2">
                    <span className="text-tertiary font-mono text-[11px]">·</span>
                    <span>{line}</span>
                  </li>
                ))}
              </ol>
              <p className="text-tertiary text-[11px] leading-relaxed">
                每次运行都会重新提交同一段示例岗位描述（后端按文本去重，不会产生重复岗位）。
              </p>
            </CardContent>
          </Card>
        </div>

        <aside className="flex min-w-0 flex-col gap-4">
          <Card className="min-w-0">
            <CardHeader>
              <CardTitle>目标岗位</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-2 text-xs">
              {selected ? (
                <>
                  <p className="text-primary text-sm">{selected.role}</p>
                  <p className="text-secondary">{selected.company ?? '公司未在 JD 中识别'}</p>
                  <dl className="flex flex-col gap-1 font-mono text-[11px]">
                    <div className="flex justify-between gap-2">
                      <dt className="text-tertiary">job</dt>
                      <dd className="text-secondary truncate" title={selected.id}>
                        {selected.id}
                      </dd>
                    </div>
                    <div className="flex justify-between gap-2">
                      <dt className="text-tertiary">解析置信度</dt>
                      <dd className="text-secondary tabular-nums">
                        {formatScore(selected.parseConfidence * 100, 0)}%
                      </dd>
                    </div>
                    <div className="flex justify-between gap-2">
                      <dt className="text-tertiary">parseStatus</dt>
                      <dd className="text-secondary">{selected.parseStatus}</dd>
                    </div>
                    <div className="flex justify-between gap-2">
                      <dt className="text-tertiary">匹配分</dt>
                      <dd className="text-secondary tabular-nums">
                        {selected.matchScore === null
                          ? '— 未匹配'
                          : formatScore(selected.matchScore)}
                      </dd>
                    </div>
                  </dl>
                  <p className="text-tertiary text-[11px] leading-relaxed">
                    题目依据（GET /jobs/{'{id}'}/skill-tree）
                  </p>
                  {skillTree.isPending ? <Skeleton className="h-16" /> : null}
                  {skillTree.data ? (
                    <ul className="flex flex-col gap-1.5">
                      {[
                        ...skillTree.data.required.map((item) => ['必备', item] as const),
                        ...skillTree.data.preferred.map((item) => ['优先', item] as const),
                        ...skillTree.data.bonus.map((item) => ['加分', item] as const),
                      ].map(([kind, item]) => (
                        <li key={`${kind}-${item.rawText}`} className="flex items-center gap-2">
                          <Badge variant={kind === '必备' ? 'signal' : 'default'}>{kind}</Badge>
                          <span className="text-secondary truncate" title={item.rawText}>
                            {item.rawText}
                          </span>
                          {item.canonicalId ? null : <Badge variant="outline">未归一化</Badge>}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  {skillTree.data && skillTree.data.unmatchedCount > 0 ? (
                    <p className="text-tertiary text-[11px]">
                      {skillTree.data.unmatchedCount} 项要求未能映射到技能本体，面试中不会成为主题。
                    </p>
                  ) : null}
                </>
              ) : (
                <p className="text-secondary">尚未选择岗位，因此没有题目依据可显示 —— 这里不猜。</p>
              )}
            </CardContent>
          </Card>

          <Card className="min-w-0">
            <CardHeader>
              <CardTitle>本次会话的已知边界</CardTitle>
              <CardDescription>
                来自 GET /ai/capabilities 与请求结构本身，不是猜测。
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-2 text-[11px] leading-relaxed">
              <p className="text-secondary flex items-start gap-2">
                <Info className="text-tertiary mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
                <span>
                  <span className="font-mono">StartInterviewRequest</span> 只接受 mode / job /
                  profile / difficulty —— 因此没有「关注方向」输入框；关注方向由岗位技能计划决定。
                </span>
              </p>
              <p className="text-secondary">
                <span className="font-mono">job</span> 必须是 JD 解析结果：本页用{' '}
                <span className="font-mono">GET /jobs/{'{id}'}</span> 的 analysis，而不是 analyze
                的响应（后者多一个 warnings 键，会被 extra=forbid 拒绝）。
              </p>
              {capabilities ? (
                <dl className="border-subtle bg-base flex flex-col gap-1 rounded-md border px-3 py-2 font-mono text-[11px]">
                  <div className="flex justify-between gap-2">
                    <dt className="text-tertiary">provider</dt>
                    <dd className="text-secondary">{capabilities.provider}</dd>
                  </div>
                  <div className="flex justify-between gap-2">
                    <dt className="text-tertiary">degraded</dt>
                    <dd className="text-secondary">{String(capabilities.degraded)}</dd>
                  </div>
                  <div className="flex justify-between gap-2">
                    <dt className="text-tertiary">session_store</dt>
                    <dd className="text-secondary">{capabilities.sessionStore}</dd>
                  </div>
                  <div className="flex justify-between gap-2">
                    <dt className="text-tertiary">retrieval</dt>
                    <dd className="text-secondary">
                      {capabilities.retrievalAvailable ? 'available' : 'unavailable'}
                    </dd>
                  </div>
                </dl>
              ) : null}
              {capabilities && capabilities.sessionStore === 'in-process' ? (
                <p className="text-weak">
                  会话保存在后端进程内：重启 API 后 <span className="font-mono">?session=</span>{' '}
                  会失效，页面会告知而不是静默新建。
                </p>
              ) : null}
              {capabilities?.limitations.map((line) => (
                <p key={line} className="text-tertiary">
                  · {line}
                </p>
              ))}
            </CardContent>
          </Card>
        </aside>
      </div>
    </div>
  );
}
