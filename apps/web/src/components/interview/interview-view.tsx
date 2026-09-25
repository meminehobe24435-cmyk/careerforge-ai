'use client';

import { Button, ErrorState, Skeleton } from '@careerforge/ui';
import { isApiError } from '@careerforge/shared';

import { demoSession } from '@/components/interview/demo-script';
import { InterviewScorecardView } from '@/components/interview/interview-scorecard';
import { InterviewSetup } from '@/components/interview/interview-setup';
import { InterviewWorkspace } from '@/components/interview/interview-workspace';
import { useInterviewController, useSessionParam } from '@/hooks/use-interview';
import { isDemoSession, recallTarget } from '@/hooks/use-interview-setup';
import { API_BASE_URL } from '@/lib/api';

/**
 * `/app/interview` — one page, four states.
 *
 * The URL decides which one: `?session=<id>` means there is a session to resume, and an absent id
 * means the setup screen. That is what makes a refresh behave like a refresh rather than like a
 * reset — `GET /ai/interview/{id}` rehydrates the transcript, the level, the plan and (after
 * `finish`) the scorecard from the server, and the only thing held locally is which target job the
 * session was started with, which the payload does not carry.
 *
 * The session store is in-process (`session_store: "in-process"` in `GET /ai/capabilities`), so a
 * restarted API turns a valid-looking link into a 404. That case is stated on screen with the
 * request id, and one click starts a new session — an expired link must not look like a broken page.
 */
export function InterviewView() {
  const [sessionId, setSessionId] = useSessionParam();
  const controller = useInterviewController(sessionId, setSessionId);

  if (!sessionId) {
    return (
      <InterviewSetup
        busy={controller.busy}
        actionError={controller.busy === null ? controller.actionError : null}
        onDismissError={controller.clearActionError}
        onStart={(input) => void controller.start(input)}
        onDemo={() => void controller.runDemo(demoSession)}
      />
    );
  }

  if (controller.isPending && !controller.session) return <WorkspaceSkeleton />;

  if (!controller.session) {
    const error = controller.loadError;
    const apiError = isApiError(error) ? error : null;
    const gone = apiError?.status === 404 || apiError?.code === 'NOT_FOUND';

    if (!error) return <WorkspaceSkeleton />;

    return (
      <div className="flex flex-col gap-4">
        <ErrorState
          title={gone ? '这个会话已经不在后端了' : '会话加载失败'}
          error={error}
          code={apiError?.code ?? 'UNKNOWN'}
          requestId={apiError?.requestId ?? null}
          onRetry={gone ? undefined : controller.refetch}
          retrying={controller.isFetching}
          statusHref="/system"
          details={
            gone ? (
              <p className="leading-relaxed">
                会话保存在后端进程内（GET /ai/capabilities 的 session_store=in-process）：API
                重启后旧链接会失效。成绩没有别的副本可读，所以这里不会假装恢复。
              </p>
            ) : (
              <p className="font-mono text-[11px]">
                GET {API_BASE_URL}/ai/interview/{sessionId}
              </p>
            )
          }
        />
        <Button variant="secondary" size="sm" onClick={() => setSessionId(null)}>
          开始新的会话
        </Button>
      </div>
    );
  }

  const target = recallTarget(controller.session.sessionId);
  const isDemo = isDemoSession(controller.session.sessionId);

  if (controller.session.scorecard) {
    return (
      <InterviewScorecardView
        scorecard={controller.session.scorecard}
        sessionId={controller.session.sessionId}
        isDemo={isDemo}
        onNewSession={() => setSessionId(null)}
      />
    );
  }

  return (
    <InterviewWorkspace
      session={controller.session}
      target={target}
      isDemo={isDemo}
      controller={controller}
    />
  );
}

/** A skeleton shaped like the workspace, so the answer box does not jump into place. */
function WorkspaceSkeleton() {
  return (
    <div className="flex flex-col gap-4" aria-busy="true" aria-live="polite">
      <Skeleton className="h-6 w-56" />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,20rem)]">
        <div className="flex flex-col gap-4">
          <Skeleton className="h-32" />
          <Skeleton className="h-52" />
        </div>
        <div className="flex flex-col gap-4">
          <Skeleton className="h-40" />
          <Skeleton className="h-56" />
        </div>
      </div>
    </div>
  );
}
