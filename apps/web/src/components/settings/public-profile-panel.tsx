'use client';

import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Separator,
  cn,
} from '@careerforge/ui';
import { getErrorMessage, type PublicSettingsResponse } from '@careerforge/shared';
import { Copy, Eye, Globe, Lock, RefreshCw } from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { api } from '@/lib/api';
import { queryKeys } from '@/lib/query-keys';

/** Section switches, with the copy the candidate actually reads. */
const SECTION_COPY: { key: string; label: string; hint: string }[] = [
  { key: 'summary', label: '概述', hint: '帮你写的公开简介' },
  { key: 'skills', label: '技能', hint: '技能列表（不含引用）' },
  { key: 'evidence', label: '证据引用', hint: '点击技能后展开的具体来源' },
  { key: 'projects', label: '项目', hint: '项目名称、技术栈与链接' },
  { key: 'highlights', label: '工程亮点', hint: '3–5 条由证据支撑的亮点' },
  { key: 'interview_topics', label: '面试话题', hint: '面试官可以深入提问的方向' },
  { key: 'contact', label: '联系方式与链接', hint: 'GitHub / 个人主页（默认关闭）' },
  { key: 'resume_file', label: '简历文件下载', hint: '原始文件下载（默认关闭）' },
];

/**
 * The candidate's control panel for their public page (docs/UI.md §5.16).
 *
 * Three things this panel insists on, all of which are about informed consent:
 *
 * 1. the **share link is visible before it works** — the candidate sees exactly what a recruiter
 *    will open, not a claim that a page exists somewhere;
 * 2. every switch says what it covers, because "evidence" and "skills" sound similar and mean
 *    different things to a reader deciding what to expose;
 * 3. what was **masked is reported** — a page that quietly removed a phone number is
 *    indistinguishable from one that never had it, and the candidate is the one who should know.
 */
export function PublicProfilePanel() {
  const queryClient = useQueryClient();
  const settings = useQuery({
    queryKey: queryKeys.publicProfile.settings(),
    queryFn: () => api.publicSettings(),
    retry: 1,
  });

  const publish = useMutation<PublicSettingsResponse, unknown, boolean>({
    mutationFn: (published) => api.publishPublicProfile({ published }),
    onSuccess: (data) => {
      toast.success(data.isPublished ? '公开页已发布' : '已取消发布');
      void queryClient.invalidateQueries({ queryKey: queryKeys.publicProfile.settings() });
    },
    onError: (error) => toast.error('操作失败', { description: getErrorMessage(error) }),
  });

  const update = useMutation<
    PublicSettingsResponse,
    unknown,
    { sections?: Record<string, boolean>; hiddenSkills?: string[] }
  >({
    mutationFn: (payload) => api.updatePublicSettings(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.publicProfile.settings() });
    },
    onError: (error) => toast.error('设置未保存', { description: getErrorMessage(error) }),
  });

  if (settings.isPending) {
    return <Card className="h-40 animate-pulse" />;
  }

  if (settings.isError || !settings.data) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>公开页与隐私</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <p className="text-secondary text-xs">读取设置失败：{getErrorMessage(settings.error)}</p>
          <Button variant="secondary" size="sm" onClick={() => void settings.refetch()}>
            <RefreshCw className="size-3.5" aria-hidden="true" />
            重试
          </Button>
        </CardContent>
      </Card>
    );
  }

  const data = settings.data;
  const shareUrl =
    typeof window !== 'undefined' && data.url ? `${window.location.origin}${data.url}` : data.url;

  return (
    <Card className="min-w-0">
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle>公开页与隐私</CardTitle>
        <div className="flex items-center gap-2">
          {data.isPublished ? (
            <Badge variant="signal">
              <Globe className="mr-1 size-3" aria-hidden="true" />
              已发布
            </Badge>
          ) : (
            <Badge variant="outline">
              <Lock className="mr-1 size-3" aria-hidden="true" />
              未发布
            </Badge>
          )}
          {data.isPublished ? (
            <span className="text-tertiary inline-flex items-center gap-1 font-mono text-[11px]">
              <Eye className="size-3" aria-hidden="true" />
              {data.viewCount}
            </span>
          ) : null}
        </div>
      </CardHeader>

      <CardContent className="flex flex-col gap-4">
        {!data.canPublish ? (
          <p className="text-danger text-xs leading-relaxed">
            当前账号是本地模式（<span className="font-mono">storage_scope=local</span>）：
            数据不出本机与公开 URL 互相矛盾，因此无法发布。切换到云端模式后才能发布。
          </p>
        ) : null}

        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            variant={data.isPublished ? 'ghost' : 'secondary'}
            onClick={() => publish.mutate(!data.isPublished)}
            loading={publish.isPending}
            disabled={!data.canPublish && !data.isPublished}
          >
            {data.isPublished ? '取消发布' : '发布公开页'}
          </Button>
          {shareUrl ? (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                void navigator.clipboard?.writeText(shareUrl);
                toast.success('分享链接已复制');
              }}
            >
              <Copy className="size-3.5" aria-hidden="true" />
              复制分享链接
            </Button>
          ) : null}
          <Button
            size="sm"
            variant="ghost"
            onClick={() => void settings.refetch()}
            loading={settings.isFetching}
            aria-label="刷新公开页设置"
          >
            <RefreshCw className="size-3.5" aria-hidden="true" />
          </Button>
        </div>

        {shareUrl ? (
          <p className="text-tertiary break-all font-mono text-[11px]">{shareUrl}</p>
        ) : (
          <p className="text-tertiary text-[11px]">
            发布后这里会出现可分享的链接。未发布时该链接返回 404，陌生人无法通过猜测访问。
          </p>
        )}

        <Separator />

        <div className="flex flex-col gap-2">
          <h3 className="text-primary text-xs font-semibold">逐项可见性</h3>
          <ul className="flex flex-col gap-2">
            {SECTION_COPY.map((section) => {
              const on = data.sections[section.key] ?? false;
              return (
                <li key={section.key} className="flex items-center justify-between gap-3 text-xs">
                  <span className="flex min-w-0 flex-col">
                    <span className="text-primary">{section.label}</span>
                    <span className="text-tertiary text-[11px]">{section.hint}</span>
                  </span>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={on}
                    aria-label={`${section.label}可见`}
                    onClick={() => update.mutate({ sections: { [section.key]: !on } })}
                    className={cn(
                      'border-subtle relative h-5 w-9 shrink-0 rounded-full border transition-colors',
                      on ? 'bg-signal/60' : 'bg-sunken',
                    )}
                  >
                    <span
                      className={cn(
                        'bg-surface absolute top-0.5 size-3.5 rounded-full transition-all',
                        on ? 'left-[18px]' : 'left-0.5',
                      )}
                    />
                  </button>
                </li>
              );
            })}
          </ul>
          <p className="text-tertiary text-[11px] leading-relaxed">
            开关立即生效：改动后下一次打开公开页就是新状态，不需要重新发布。
          </p>
        </div>

        {data.hiddenSkills.length > 0 ? (
          <>
            <Separator />
            <div className="flex flex-col gap-2">
              <h3 className="text-primary text-xs font-semibold">
                已隐藏的技能（{data.hiddenSkills.length}）
              </h3>
              <div className="flex flex-wrap gap-1.5">
                {data.hiddenSkills.map((skill) => (
                  <Badge key={skill} variant="outline">
                    {skill}
                  </Badge>
                ))}
              </div>
            </div>
          </>
        ) : null}

        {data.piiFindings.length > 0 ? (
          <>
            <Separator />
            <div className="flex flex-col gap-1">
              <h3 className="text-primary text-xs font-semibold">
                发布时已脱敏 {data.piiFindings.length} 处
              </h3>
              <ul className="text-tertiary flex flex-col gap-0.5 font-mono text-[10px]">
                {data.piiFindings.slice(0, 6).map((finding, index) => (
                  <li key={`${String(finding['kind'])}-${index}`}>
                    {String(finding['kind'] ?? 'pii')} → {String(finding['masked'] ?? '***')}
                  </li>
                ))}
              </ul>
              <p className="text-tertiary text-[11px] leading-relaxed">
                脱敏发生在服务端：邮箱与电话不会进入公开页，也不会出现在接口响应里。
              </p>
            </div>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
