'use client';

import {
  Badge,
  Button,
  Card,
  CardContent,
  Input,
  Label,
  Separator,
  Tooltip,
} from '@careerforge/ui';
import type { LoginResponse } from '@careerforge/shared';
import { isApiError } from '@careerforge/shared';
import { useMutation } from '@tanstack/react-query';
import { ArrowRight, ShieldCheck } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { toast } from 'sonner';

import { API_BASE_URL, api } from '@/lib/api';
import { saveSession } from '@/lib/auth';

/** Honest error reporting: message + code + requestId (docs/UI.md §6.1, §9). */
function reportAuthError(error: unknown, action: string): void {
  const apiError = isApiError(error) ? error : null;

  if (!apiError) {
    toast.error(`${action}失败`, {
      description: error instanceof Error ? error.message : '未知错误',
      duration: 8000,
    });
    return;
  }

  toast.error(apiError.isNetworkError ? `${action}失败：后端不可达` : apiError.message, {
    description: [
      `code: ${apiError.code}`,
      `requestId: ${apiError.requestId ?? '—'}`,
      apiError.isNetworkError ? `API: ${API_BASE_URL}` : null,
      apiError.isNetworkError ? '请先启动后端（pnpm --filter api dev）后重试' : null,
    ]
      .filter((line): line is string => Boolean(line))
      .join(' · '),
    duration: 10_000,
  });
}

export interface LoginPanelProps {
  /** `?demo=1` — the hero's "View Demo" CTA lands here with the demo path highlighted. */
  demoIntent: boolean;
}

/**
 * Login surface (docs/UI.md §5.2).
 *
 * Primary CTA is one-click demo login (`POST /auth/demo`); the email/password form posts
 * to `/auth/login` and is expected to fail while no backend is running — that failure is
 * surfaced as a toast carrying the `requestId`, never as a crash.
 */
export function LoginPanel({ demoIntent }: LoginPanelProps) {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  const completeLogin = (data: LoginResponse | null, label: string) => {
    if (!data?.accessToken) {
      toast.error(`${label}：响应缺少 accessToken`, {
        description: `收到的字段：${data ? Object.keys(data).join(', ') || '（空对象）' : 'data 为 null'}`,
        duration: 9000,
      });
      return;
    }
    saveSession(data);
    toast.success(`欢迎回来，${data.user.displayName}`);
    router.replace('/app/dashboard');
  };

  const demoMutation = useMutation({
    mutationFn: () => api.demoLogin(),
    onSuccess: (data) => completeLogin(data, 'Demo 登录'),
    onError: (error) => reportAuthError(error, 'Demo 登录'),
  });

  const loginMutation = useMutation({
    mutationFn: (payload: { email: string; password: string }) => api.login(payload),
    onSuccess: (data) => completeLogin(data, '登录'),
    onError: (error) => reportAuthError(error, '登录'),
  });

  const demoLoading = demoMutation.isPending;

  return (
    <Card className={demoIntent ? 'border-brand/40 ring-brand/20 shadow-md ring-1' : undefined}>
      <CardContent className="flex flex-col gap-5 p-5 sm:p-6">
        <div className="flex flex-col gap-1">
          <h1 className="text-primary text-lg font-semibold tracking-tight">登录 CareerForge</h1>
          <p className="text-secondary text-xs leading-relaxed">
            一键进入 Demo 账号，或使用邮箱登录。当前阶段 API
            未启动时，登录会明确报错而不是静默失败。
          </p>
        </div>

        <div className="flex flex-col gap-2">
          <Button
            size="lg"
            onClick={() => demoMutation.mutate()}
            loading={demoLoading}
            className="w-full"
          >
            {demoLoading ? null : <ArrowRight className="size-4" aria-hidden="true" />}
            Enter Demo
          </Button>
          <p className="text-tertiary font-mono text-[11px]">
            demo@careerforge.ai · 已预置完整候选人数据
          </p>
          <Tooltip
            content={
              <span className="font-mono text-[11px]">
                POST {API_BASE_URL}/auth/demo → accessToken / refreshToken / expiresIn / user
              </span>
            }
          >
            <span className="text-tertiary w-fit cursor-help font-mono text-[11px]">
              POST /auth/demo
            </span>
          </Tooltip>
        </div>

        <div className="flex items-center gap-3">
          <Separator className="flex-1" />
          <span className="text-tertiary font-mono text-[10px] uppercase tracking-wider">
            或使用邮箱登录
          </span>
          <Separator className="flex-1" />
        </div>

        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            loginMutation.mutate({ email, password });
          }}
        >
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="login-email">邮箱</Label>
            <Input
              id="login-email"
              type="email"
              name="email"
              autoComplete="email"
              placeholder="you@example.com"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="login-password">密码</Label>
            <Input
              id="login-password"
              type="password"
              name="password"
              autoComplete="current-password"
              placeholder="••••••••"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </div>

          <Button type="submit" variant="secondary" loading={loginMutation.isPending}>
            登录
          </Button>
        </form>

        <div className="border-subtle flex flex-wrap items-center gap-2 border-t pt-4">
          <ShieldCheck className="text-tertiary size-3.5" aria-hidden="true" />
          <Badge variant="outline">JWT HS256 · access 30min</Badge>
          <Badge variant="outline">refresh 7d</Badge>
        </div>
      </CardContent>
    </Card>
  );
}
