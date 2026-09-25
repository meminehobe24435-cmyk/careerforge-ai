/**
 * Capture the authenticated pages in a real browser, with no test-runner dependency.
 *
 * Playwright covers the *assertions* (`apps/web/e2e/**`); this script exists because the phase gates
 * ask for the pages to be *looked at* at several widths, and "an assertion passed" is not that. It
 * drives an already installed Chrome/Edge over the DevTools Protocol (`--remote-debugging-port`)
 * using Node's global `WebSocket`, so nothing new is installed and nothing is downloaded.
 *
 * What it does, per page and per viewport:
 *
 *   1. signs in through the real `POST /auth/demo`, then injects the session into `localStorage`
 *      before any page script runs — the app's guard is client-side, so this is how a real session
 *      is established without automating a form;
 *   2. navigates, optionally **drives the page** (the validator's verdict and the interview's
 *      evaluation exist only after a real interaction), then **waits for real data to appear** — a
 *      selector the page only renders once the API answered — so a screenshot of an empty shell
 *      cannot pass as success;
 *   3. saves the PNG as `<name>-<width>.png` and prints `document.body.innerText`, which is the
 *      part a reviewer can grep. The full text of every capture is also written to
 *      `.tmp/capture-text/`, so a reviewer can grep a whole page rather than a truncated log line.
 *
 * The account is populated **before** anything is captured (`prepareAccount`): a résumé through
 * `POST /profile/import` and `POST /documents` + `POST /documents/{id}/analyze`, a manual evidence
 * row, two analysed documents, a posting that is parsed and matched, four tracked applications and
 * a published candidate page. Every capture is of a page with data on it; where a region is still
 * empty (a list the account genuinely has nothing for) the captured text says so rather than the
 * screenshot passing as a populated view.
 *
 * Usage (API on :8318, `next start` on :3318, built against that API base URL):
 *
 *     node --experimental-strip-types scripts/capture-pages.mts
 *     PAGES_BASE_URL=http://127.0.0.1:3318 API_BASE_URL=http://127.0.0.1:8318/api/v1 \
 *       node --experimental-strip-types scripts/capture-pages.mts
 */

import { mkdir, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { spawn } from 'node:child_process';
import path from 'node:path';

const pagesBase = process.env['PAGES_BASE_URL']?.trim() || 'http://127.0.0.1:3318';
const apiBase = process.env['API_BASE_URL']?.trim() || 'http://127.0.0.1:8318/api/v1';

/**
 * Output paths are resolved against the **repository root**, not the current directory.
 *
 * `pnpm --filter @careerforge/web capture:pages` runs this with `apps/web` as the working directory,
 * so a relative default would drop the artefacts in `apps/web/docs/assets/screenshots` — which is
 * what happened on the first run of this version, and is exactly the kind of quiet misplacement
 * that leaves the README pointing at files nobody can find.
 */
const repoRoot = path.resolve(import.meta.dirname, '../../..');
const fromRoot = (value: string | undefined, fallback: string): string =>
  path.resolve(repoRoot, value?.trim() || fallback);

const outDir = fromRoot(process.env['CAPTURE_OUT_DIR'], 'docs/assets/screenshots');
const textDir = fromRoot(process.env['CAPTURE_TEXT_DIR'], '.tmp/capture-text');
const port = Number(process.env['CDP_PORT'] ?? 9333);

const BROWSERS = [
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
];

/** The material the pages are populated from — the same fixture the e2e specs use. */
const RESUME = `教育经历
某某大学 电子信息工程 本科 2019-2023

实习经历
某某科技 嵌入式软件实习生 2022-07 至 2022-12
使用 STM32 与 FreeRTOS 开发电机控制固件，负责 CAN 总线节点通信调试。

项目经历
平衡小车 2022
基于 STM32 的 PID 平衡控制，使用 FreeRTOS 任务调度与 CAN 通信。
`;

const PROJECT_NOTES = `平衡小车项目记录
- motor_control.c：STM32 上以 FreeRTOS 任务运行电机控制固件，PID 控制环，CAN 总线节点通信调试。
- 传感器通过 I2C 读取，调试数据经 UART 上报。
`;

const JOB_DESCRIPTION = `岗位名称：嵌入式软件工程师（电机控制方向）
公司：某某智能科技
工作地点：上海

岗位职责：
1. 负责基于 STM32 的无刷电机控制固件开发与调试；
2. 使用 FreeRTOS 设计多任务实时调度，保证控制周期稳定；
3. 负责 CAN 总线通信协议实现与整车联调；
4. 参与 PID 控制算法整定与性能优化。

任职要求：
1. 本科及以上学历，电子、自动化、计算机相关专业；
2. 熟练使用 C 语言，熟悉 STM32 系列 MCU 与外设驱动；
3. 熟悉 FreeRTOS 或同类 RTOS，理解任务调度与优先级反转；
4. 熟悉 CAN、UART、SPI 等通信协议；
5. 有 Docker 与 CI/CD 经验者优先。
`;

/** A sentence the stored résumé states almost verbatim — what the validator page is for. */
const SUPPORTED_CLAIM = '使用 STM32 与 FreeRTOS 开发电机控制固件，负责 CAN 总线节点通信调试。';

const INTERVIEW_ANSWER =
  '我先按控制回路划分 FreeRTOS 任务：采样、PID 计算、CAN 收发各一个任务，用队列传递数据，' +
  '并为 PID 任务设最高优先级。这样做的好处是控制周期稳定，代价是内存占用更高。';

interface Prepared {
  slug: string;
  jobId: string;
  email: string;
}

interface Page {
  name: string;
  path: string | ((ctx: Prepared) => string);
  /** A CSS selector that only exists once the API's data has rendered. */
  readySelector: string;
  /** Extra readiness: text that only appears once a second read has landed. */
  readyText?: string;
  /** Assertions on the rendered text — the part a screenshot cannot be diffed against. */
  expectText: string[];
  /** Text that only the wide layout has (a table header the card layout replaces with a label). */
  wideOnlyText?: string[];
  /** Steps that require a real interaction; run after navigation, before the ready wait. */
  act?: (driver: Driver, ctx: Prepared) => Promise<void>;
}

const VIEWPORTS = [
  { label: '1440', width: 1440, height: 900 },
  { label: '375', width: 375, height: 812 },
];

function findBrowser(): string {
  const found = BROWSERS.find((candidate) => existsSync(candidate));
  if (!found) throw new Error('no Chrome/Edge found; set one of BROWSERS by hand');
  return found;
}

async function sleep(ms: number): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

/** Minimal CDP client: one browser websocket, one attached page session. */
class Cdp {
  private socket: WebSocket;
  private nextId = 1;
  private pending = new Map<
    number,
    { resolve: (value: unknown) => void; reject: (error: Error) => void }
  >();

  constructor(socket: WebSocket) {
    this.socket = socket;
    socket.addEventListener('message', (event: MessageEvent) => {
      const message = JSON.parse(String(event.data)) as {
        id?: number;
        result?: unknown;
        error?: { message: string };
      };
      if (message.id === undefined) return;
      const waiter = this.pending.get(message.id);
      if (!waiter) return;
      this.pending.delete(message.id);
      if (message.error) waiter.reject(new Error(message.error.message));
      else waiter.resolve(message.result);
    });
  }

  send<T>(method: string, params: Record<string, unknown> = {}, sessionId?: string): Promise<T> {
    const id = this.nextId++;
    const payload = JSON.stringify(
      sessionId ? { id, method, params, sessionId } : { id, method, params },
    );
    return new Promise<T>((resolve, reject) => {
      this.pending.set(id, { resolve: resolve as (value: unknown) => void, reject });
      this.socket.send(payload);
    });
  }

  close(): void {
    this.socket.close();
  }
}

async function connect(url: string): Promise<Cdp> {
  const socket = new WebSocket(url);
  await new Promise<void>((resolve, reject) => {
    socket.addEventListener('open', () => resolve(), { once: true });
    socket.addEventListener('error', () => reject(new Error(`cannot open ${url}`)), { once: true });
  });
  return new Cdp(socket);
}

/**
 * Driving the page from CDP.
 *
 * `Runtime.evaluate` is enough for a click and a field edit as long as React sees a *native* event:
 * an assignment to `.value` has to go through the prototype's own setter, otherwise React's value
 * tracker suppresses the change event and the component never updates. That is the one subtlety
 * here, and it is why the page loop is not a row of one-line `element.click()` calls.
 */
class Driver {
  // Plain fields rather than constructor parameter properties: this script runs under
  // `node --experimental-strip-types`, which strips types without compiling them, and that mode
  // rejects parameter properties (`SyntaxError: TypeScript parameter property is not supported in
  // strip-only mode`).
  private readonly cdp: Cdp;
  private readonly sessionId: string;

  constructor(cdp: Cdp, sessionId: string) {
    this.cdp = cdp;
    this.sessionId = sessionId;
  }

  async evaluate<T>(expression: string): Promise<T | null> {
    const result = await this.cdp.send<{ result: { value?: unknown } }>(
      'Runtime.evaluate',
      { expression, returnByValue: true, awaitPromise: true },
      this.sessionId,
    );
    return (result.result.value ?? null) as T | null;
  }

  async text(): Promise<string> {
    return (await this.evaluate<string>('document.body.innerText')) ?? '';
  }

  /** Wait for a selector, so a failure names what was missing rather than a bare timeout. */
  async waitForSelector(selector: string, timeoutMs = 20_000): Promise<void> {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const found = await this.evaluate<boolean>(
        `Boolean(document.querySelector(${JSON.stringify(selector)}))`,
      );
      if (found) return;
      await sleep(200);
    }
    throw new Error(`selector ${selector} never appeared`);
  }

  async waitForText(needle: string, timeoutMs = 20_000): Promise<void> {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      if ((await this.text()).includes(needle)) return;
      await sleep(200);
    }
    throw new Error(`text ${JSON.stringify(needle)} never appeared`);
  }

  /** Set a field's value the way a keystroke would, so React's onChange fires. */
  async setValue(selector: string, value: string): Promise<void> {
    const expression = `(() => {
      const el = document.querySelector(${JSON.stringify(selector)});
      if (!el) return 'missing';
      const isSelect = el.tagName === 'SELECT';
      const prototype = isSelect ? HTMLSelectElement.prototype : HTMLTextAreaElement.prototype;
      Object.getOwnPropertyDescriptor(prototype, 'value').set.call(el, ${JSON.stringify(value)});
      el.dispatchEvent(new Event(isSelect ? 'change' : 'input', { bubbles: true }));
      return 'ok';
    })()`;
    if ((await this.evaluate<string>(expression)) !== 'ok') {
      throw new Error(`cannot fill ${selector}`);
    }
  }

  /** Click a button by its visible label — these pages have no ids on their primary actions. */
  async clickButton(label: string): Promise<void> {
    const expression = `(() => {
      const button = [...document.querySelectorAll('button')]
        .find((candidate) => (candidate.textContent ?? '').includes(${JSON.stringify(label)}));
      if (!button) return 'missing';
      button.click();
      return 'ok';
    })()`;
    if ((await this.evaluate<string>(expression)) !== 'ok') {
      throw new Error(`no button labelled ${label}`);
    }
  }

  async click(selector: string): Promise<void> {
    const outcome = await this.evaluate<string>(
      `(() => { const el = document.querySelector(${JSON.stringify(selector)}); if (!el) return 'missing'; el.click(); return 'ok'; })()`,
    );
    if (outcome !== 'ok') throw new Error(`cannot click ${selector}`);
  }
}

async function readJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) throw new Error(`${url} → HTTP ${response.status} ${await response.text()}`);
  return (await response.json()) as T;
}

async function demoSession(): Promise<Record<string, unknown>> {
  const envelope = await readJson<{ data: Record<string, unknown> }>(`${apiBase}/auth/demo`, {
    method: 'POST',
  });
  return { ...envelope.data, storedAt: Date.now() };
}

/** An authenticated JSON call against the live API, unwrapping the envelope. */
async function apiCall<T>(
  token: string,
  method: 'GET' | 'POST',
  route: string,
  body?: unknown,
): Promise<T> {
  const envelope = await readJson<{ data: T }>(`${apiBase}${route}`, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/json',
      ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  return envelope.data;
}

/**
 * Populate the account so every capture is of a page with data on it.
 *
 * **Read first, write only what is missing — and that is a hard requirement, not tidiness.**
 * `POST /profile/import`, `POST /documents` and `POST /documents/{id}/analyze` all draw on the
 * `upload` rate-limit bucket, which is **20 requests per hour per user** (`middleware/ratelimit.py`).
 * The first version of this script re-imported and re-analysed on every run, which spent the whole
 * hourly budget in two runs and then failed with
 * `429 RATE_LIMITED … retry in 121s` — a documentation script that can only run twice an hour is
 * worse than one that does nothing. So: the profile import only happens when the account has no
 * evidence at all, the documents are only uploaded when they are absent, `analyze` only runs for a
 * document whose chunks are missing, and the manual row and the four applications are only created
 * when the account does not already have them.
 *
 * The manual row is read-then-written for a second reason: `evidence` has a unique constraint on
 * `(user_id, kind, content_hash)` and `EvidenceService.add_manual` inserts without honouring it, so
 * a second identical `POST /evidence` is a `500 INTERNAL_ERROR` rather than an updated row. That is
 * a backend bug, reported as one.
 */
async function prepareAccount(token: string, email: string): Promise<Prepared> {
  const before = await apiCall<{ items: Array<{ kind: string }> }>(
    token,
    'GET',
    '/evidence?limit=200',
  );
  const kinds = new Set(before.items.map((item) => item.kind));

  if (kinds.size === 0) {
    await apiCall(token, 'POST', '/profile/import', { text: RESUME });
  }

  // ── documents → evidence (a résumé plus a second source, so the graph has depth) ────────────
  if (!kinds.has('document_chunk')) {
    const existing = await apiCall<{ items: Array<{ id: string; filename: string }> }>(
      token,
      'GET',
      '/documents?limit=20',
    );
    for (const upload of [
      { filename: 'resume.md', kind: 'resume', text: RESUME },
      { filename: 'project-notes.md', kind: 'project_doc', text: PROJECT_NOTES },
    ]) {
      let documentId = existing.items.find((item) => item.filename === upload.filename)?.id ?? null;
      if (!documentId) {
        const form = new FormData();
        form.append('file', new Blob([upload.text], { type: 'text/markdown' }), upload.filename);
        form.append('kind', upload.kind);
        const response = await fetch(`${apiBase}/documents`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' },
          body: form,
        });
        const envelope = (await response.json()) as { data?: { documentId?: string } };
        if (!response.ok || !envelope.data?.documentId) {
          throw new Error(`POST /documents (${upload.filename}) → HTTP ${response.status}`);
        }
        documentId = envelope.data.documentId;
        // The worker ingests asynchronously; `analyze` on a half-parsed document produces nothing.
        for (let attempt = 0; attempt < 30; attempt += 1) {
          const detail = await apiCall<{ parseStatus: string }>(
            token,
            'GET',
            `/documents/${documentId}`,
          );
          if (['parsed', 'parsed_with_warnings', 'failed'].includes(detail.parseStatus)) break;
          await sleep(500);
        }
      }
      await apiCall(token, 'POST', `/documents/${documentId}/analyze`);
    }
  }

  // A manual row is a second evidence *kind*: the claim gate can only reach `supported` with two.
  if (!kinds.has('manual')) {
    await apiCall(token, 'POST', '/evidence', {
      title: '嵌入式固件代码片段',
      snippet:
        'motor_control.c：STM32 上以 FreeRTOS 任务运行电机控制固件，负责 CAN 总线节点通信调试与 PID 控制环。',
      locator: { path: 'motor_control.c', line: 42 },
    });
  }

  // ── a stored posting: the jobs result, the interview target and one application need it ─────
  const job = await apiCall<{ id: string }>(token, 'POST', '/jobs/analyze', {
    text: JOB_DESCRIPTION,
    source: 'paste',
  });
  await apiCall(token, 'POST', `/jobs/${job.id}/match`);

  // ── tracked applications, so `/app/analytics` draws a funnel instead of an empty state ─────
  const tracked = await apiCall<unknown[]>(token, 'GET', '/applications');
  if (tracked.length < 4) {
    await apiCall(token, 'POST', '/applications', { jobId: job.id, status: 'applied' });
    await apiCall(token, 'POST', '/applications', {
      company: '某机器人公司',
      role: '嵌入式实习生',
      status: 'interview',
    });
    await apiCall(token, 'POST', '/applications', {
      company: '某汽车电子',
      role: '控制算法工程师',
      status: 'offer',
    });
    await apiCall(token, 'POST', '/applications', {
      company: '某半导体',
      role: '固件工程师',
      status: 'wishlist',
    });
  }

  const published = await apiCall<{ slug: string | null }>(token, 'POST', '/public/publish', {
    published: true,
  });
  if (!published.slug) throw new Error('publishing returned no slug — the candidate page has no URL');

  return { slug: published.slug, jobId: job.id, email };
}

const PAGES: Page[] = [
  {
    name: 'dashboard',
    path: '/app/dashboard',
    readySelector: 'section[aria-labelledby="dash-strength-heading"]',
    expectText: ['Profile Strength', '最近岗位', '本页所有数字均直接来自'],
  },
  {
    // `?job=<id>` loads the stored analysis, which is the populated state. The form on its own
    // (`[data-jobs-empty]`) is the empty state, and that is not what this artefact is for — the
    // ready selector is the results half of the page.
    name: 'jobs',
    path: (ctx) => `/app/jobs?job=${encodeURIComponent(ctx.jobId)}`,
    readySelector: '[data-conclusions]',
    readyText: 'Match figures',
    expectText: ['JD Intelligence', 'JD Skill Tree', 'Required skills', 'Gaps', 'Next steps'],
  },
  {
    name: 'evidence-graph',
    path: '/app/evidence-graph',
    readySelector: '[data-testid="node-index-row"]',
    expectText: ['Career Evidence Graph', 'Node index'],
  },
  {
    // The verdict lives in component state, so the page has to be driven: type the sentence, press
    // the gate's own button, and capture whatever it decided.
    name: 'validator',
    path: '/app/validator',
    readySelector: '[data-testid="validator-result"]',
    expectText: ['Resume Claim Validator', 'Verdict', 'Confidence', 'Suggested rewrite'],
    act: async (driver) => {
      await driver.waitForSelector('#claim-text');
      await driver.setValue('#claim-text', SUPPORTED_CLAIM);
      await driver.click('[data-testid="validate-claim"]');
    },
  },
  {
    // A session started and one answer submitted through the setup screen: the workspace only
    // renders an evaluation after a real turn, and the evaluation is the point of the page.
    name: 'interview',
    path: '/app/interview',
    readySelector: '[data-evaluation]',
    expectText: ['模拟面试', '你的回答', '题的回答'],
    act: async (driver, ctx) => {
      await driver.waitForSelector('#target-job');
      await driver.setValue('#target-job', ctx.jobId);
      await driver.clickButton('开始面试');
      await driver.waitForSelector('[data-interview-workspace]');
      await driver.setValue('#interview-answer', INTERVIEW_ANSWER);
      await driver.clickButton('提交回答');
    },
  },
  {
    name: 'ai-runs',
    path: '/app/ai-runs',
    readySelector: '[data-run]',
    expectText: ['AI 运行记录', 'agent_runs / llm_calls'],
    // The narrow layout is a card list: it says `0 tok` where the table has a `Tokens` header.
    wideOnlyText: ['Tokens', 'Latency', 'Status'],
  },
  {
    name: 'costs',
    path: '/app/costs',
    readySelector: '[data-total]',
    expectText: ['AI 成本', '日预算护栏', '缓存命中率', '每日成本'],
  },
  {
    // Populated by the four applications above; `[data-stage]` is a funnel bar, which the empty
    // state does not draw at all.
    name: 'analytics',
    path: '/app/analytics',
    readySelector: '[data-stage]',
    expectText: ['求职分析', '投递漏斗'],
  },
  {
    // The public recruiter view. It renders with a session installed — the page ignores it — so it
    // is captured in the same pass rather than in a second script.
    name: 'candidate',
    path: (ctx) => `/candidate/${encodeURIComponent(ctx.slug)}`,
    readySelector: 'section[aria-labelledby="skills-heading"]',
    expectText: ['Evidence-backed Skills', 'Verified by evidence'],
  },
];

async function main(): Promise<void> {
  await mkdir(outDir, { recursive: true });
  await mkdir(textDir, { recursive: true });
  const session = await demoSession();
  const token = String(session['accessToken'] ?? '');
  if (!token) throw new Error('POST /auth/demo returned no accessToken');
  const email = (session['user'] as { email?: string } | undefined)?.email ?? 'unknown';
  const prepared = await prepareAccount(token, email);
  console.log(`signed in as ${prepared.email} via ${apiBase}; pages from ${pagesBase}`);
  console.log(`candidate slug ${prepared.slug} · job ${prepared.jobId}`);

  const userDataDir = path.resolve('.tmp/chrome-capture');
  const browser = spawn(
    findBrowser(),
    [
      '--headless=new',
      `--remote-debugging-port=${port}`,
      `--user-data-dir=${userDataDir}`,
      '--no-first-run',
      '--no-default-browser-check',
      '--disable-extensions',
      '--hide-scrollbars',
      '--force-device-scale-factor=1',
      'about:blank',
    ],
    { stdio: 'ignore' },
  );

  try {
    const deadline = Date.now() + 30_000;
    let version: { webSocketDebuggerUrl: string } | null = null;
    while (!version && Date.now() < deadline) {
      await sleep(400);
      try {
        version = await readJson<{ webSocketDebuggerUrl: string }>(
          `http://127.0.0.1:${port}/json/version`,
        );
      } catch {
        version = null;
      }
    }
    if (!version) throw new Error('the browser never opened its debugging port');

    const cdp = await connect(version.webSocketDebuggerUrl);
    let failures = 0;

    for (const viewport of VIEWPORTS) {
      for (const page_ of PAGES) {
        const { targetId } = await cdp.send<{ targetId: string }>('Target.createTarget', {
          url: 'about:blank',
        });
        const { sessionId } = await cdp.send<{ sessionId: string }>('Target.attachToTarget', {
          targetId,
          flatten: true,
        });

        await cdp.send('Page.enable', {}, sessionId);
        await cdp.send('Runtime.enable', {}, sessionId);
        await cdp.send(
          'Emulation.setDeviceMetricsOverride',
          {
            width: viewport.width,
            height: viewport.height,
            deviceScaleFactor: 1,
            mobile: viewport.width < 500,
          },
          sessionId,
        );
        // Before any page script runs: the session the app's guard reads, plus the API base the
        // bundle was built with (belt and braces — the build already inlines it).
        await cdp.send(
          'Page.addScriptToEvaluateOnNewDocument',
          {
            source: `window.localStorage.setItem('careerforge.session', ${JSON.stringify(
              JSON.stringify(session),
            )});`,
          },
          sessionId,
        );

        const driver = new Driver(cdp, sessionId);
        const route = typeof page_.path === 'function' ? page_.path(prepared) : page_.path;
        let failed = false;

        try {
          await cdp.send('Page.navigate', { url: `${pagesBase}${route}` }, sessionId);
          if (page_.act) await page_.act(driver, prepared);
          await driver.waitForSelector(page_.readySelector);
          if (page_.readyText) await driver.waitForText(page_.readyText);
          // One settle beat, so a panel that arrives just after the ready selector is in the shot.
          await sleep(600);

          const body = await driver.text();
          const expected = [
            ...page_.expectText,
            ...(viewport.width >= 500 ? (page_.wideOnlyText ?? []) : []),
          ];
          const missing = expected.filter((needle) => !body.includes(needle));

          const shot = await cdp.send<{ data: string }>(
            'Page.captureScreenshot',
            { format: 'png', captureBeyondViewport: true },
            sessionId,
          );
          const file = path.join(outDir, `${page_.name}-${viewport.label}.png`);
          await writeFile(file, Buffer.from(shot.data, 'base64'));
          await writeFile(
            path.join(textDir, `${page_.name}-${viewport.label}.txt`),
            `${pagesBase}${route}\n\n${body}\n`,
            'utf8',
          );

          if (missing.length > 0) failed = true;
          console.log(
            `  ${failed ? 'FAIL' : 'ok  '} ${route} @${viewport.label} → ${file} ` +
              `(${Math.round((shot.data.length * 0.75) / 1024)} KiB)` +
              (missing.length ? ` [missing text: ${missing.join(' | ')}]` : ''),
          );
          console.log(
            `       text: ${body
              .split('\n')
              .map((line) => line.trim())
              .filter(Boolean)
              .slice(0, 40)
              .join(' ⏐ ')}`,
          );
        } catch (error) {
          failed = true;
          console.log(`  FAIL ${route} @${viewport.label} → ${String(error)}`);
        }

        if (failed) failures += 1;
        await cdp.send('Target.closeTarget', { targetId });
      }
    }

    cdp.close();
    if (failures > 0) {
      throw new Error(`${failures} capture(s) failed`);
    }
    console.log(`\nall captures rendered real data; PNGs in ${outDir}`);
  } finally {
    browser.kill();
  }
}

await main();
