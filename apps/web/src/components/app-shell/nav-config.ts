import {
  Activity,
  Bot,
  Briefcase,
  FileText,
  FolderGit2,
  Gauge,
  LayoutDashboard,
  Layers,
  Network,
  Radar,
  ShieldCheck,
  Target,
  UserRound,
  Zap,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

/**
 * Sidebar information architecture — nav groups copied from docs/UI.md §3.2
 * (Overview / Career / Intelligence / Interview / Ops).
 *
 * `live: false` means the route is specified in docs/UI.md §4 but not shipped in PHASE 1.
 * Those entries render as non-interactive, clearly-badged items on purpose: a scaffold
 * must not pretend a page exists.
 */
export interface NavItem {
  href: string;
  label: string;
  /** English/technical name, rendered in mono next to the Chinese label. */
  en: string;
  icon: LucideIcon;
  /** `g d` style chord, mirrored in the command palette. */
  shortcut?: string;
  live: boolean;
  /** Phase that will ship the route (shown in the disabled tooltip). */
  phase?: string;
}

export interface NavGroup {
  id: string;
  title: string;
  items: NavItem[];
}

export const navGroups: NavGroup[] = [
  {
    id: 'overview',
    title: 'Overview',
    items: [
      {
        href: '/app/dashboard',
        label: '总览',
        en: 'Dashboard',
        icon: LayoutDashboard,
        shortcut: 'g d',
        live: true,
      },
      {
        href: '/app/profile',
        label: '职业画像',
        en: 'Career Profile',
        icon: UserRound,
        phase: 'PHASE 3',
        live: false,
      },
    ],
  },
  {
    id: 'career',
    title: 'Career',
    items: [
      {
        href: '/app/evidence-graph',
        label: '证据图谱',
        en: 'Evidence Graph',
        icon: Network,
        shortcut: 'g e',
        phase: 'PHASE 6',
        live: false,
      },
      {
        href: '/app/evidence',
        label: '证据库',
        en: 'Evidence',
        icon: Layers,
        phase: 'PHASE 6',
        live: false,
      },
      {
        href: '/app/github',
        label: 'GitHub',
        en: 'GitHub Intelligence',
        icon: FolderGit2,
        phase: 'PHASE 5',
        live: false,
      },
    ],
  },
  {
    id: 'intelligence',
    title: 'Intelligence',
    items: [
      {
        href: '/app/jobs',
        label: '岗位与匹配',
        en: 'Jobs & Match',
        icon: Briefcase,
        shortcut: 'g j',
        phase: 'PHASE 4',
        live: false,
      },
      {
        href: '/app/resume',
        label: '简历 Copilot',
        en: 'Resume Copilot',
        icon: FileText,
        phase: 'PHASE 7',
        live: false,
      },
      {
        href: '/app/validator',
        label: '断言验证',
        en: 'Claim Validator',
        icon: Zap,
        phase: 'PHASE 6',
        live: false,
      },
      {
        href: '/app/analytics',
        label: '数据分析',
        en: 'Analytics',
        icon: Activity,
        phase: 'PHASE 9',
        live: false,
      },
    ],
  },
  {
    id: 'interview',
    title: 'Interview',
    items: [
      {
        href: '/app/interview',
        label: '模拟面试',
        en: 'Interview Simulator',
        icon: Bot,
        phase: 'PHASE 8',
        live: false,
      },
    ],
  },
  {
    id: 'ops',
    title: 'Ops',
    items: [
      {
        href: '/app/applications',
        label: '投递看板',
        en: 'Applications',
        icon: Target,
        phase: 'PHASE 9',
        live: false,
      },
      {
        href: '/app/ai-runs',
        label: 'AI 运行记录',
        en: 'AI Runs',
        icon: Radar,
        phase: 'PHASE 10',
        live: false,
      },
      {
        href: '/app/costs',
        label: '成本',
        en: 'Costs',
        icon: Gauge,
        phase: 'PHASE 10',
        live: false,
      },
      {
        href: '/app/settings',
        label: '设置',
        en: 'Settings',
        icon: ShieldCheck,
        phase: 'PHASE 11',
        live: false,
      },
    ],
  },
];

/** Routes outside `/app` that are reachable today (public, read-only). */
export const publicNav: NavItem[] = [
  {
    href: '/system',
    label: '系统状态',
    en: 'System Health',
    icon: Radar,
    live: true,
  },
];

export interface Breadcrumb {
  label: string;
  href?: string;
}

/** Pathname → breadcrumb trail + page title, used by the top bar and `<title>`s. */
export function describeRoute(pathname: string): { title: string; crumbs: Breadcrumb[] } {
  if (pathname.startsWith('/app')) {
    const withinApp = pathname.slice('/app'.length);
    if (withinApp === '' || withinApp === '/') {
      return { title: '总览', crumbs: [{ label: 'App', href: '/app/dashboard' }] };
    }
    const match = navGroups.flatMap((group) => group.items).find((item) => item.href === pathname);
    if (match) {
      const group = navGroups.find((candidate) =>
        candidate.items.some((item) => item.href === pathname),
      );
      return {
        title: match.label,
        crumbs: [
          { label: group?.title ?? 'App' },
          { label: match.label, href: match.live ? match.href : undefined },
        ],
      };
    }
    const segments = withinApp.split('/').filter(Boolean);
    return {
      title: segments[segments.length - 1] ?? 'App',
      crumbs: segments.map((segment) => ({ label: segment })),
    };
  }

  const pageTitles: Record<string, string> = {
    '/': 'CareerForge AI',
    '/login': '登录',
    '/system': '系统状态',
  };

  return { title: pageTitles[pathname] ?? 'CareerForge AI', crumbs: [] };
}
