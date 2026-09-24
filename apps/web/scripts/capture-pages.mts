/**
 * Capture the authenticated pages in a real browser, with no test-runner dependency.
 *
 * Playwright arrives with PHASE 12/13; this script exists because the phase gates ask for the pages
 * to be *looked at* at several widths, and "it rendered in jsdom" is not that. It drives an already
 * installed Chrome/Edge over the DevTools Protocol (`--remote-debugging-port`) using Node's global
 * `WebSocket`, so nothing new is installed and nothing is downloaded.
 *
 * What it does, per page and per viewport:
 *
 *   1. signs in through the real `POST /auth/demo`, then injects the session into `localStorage`
 *      before any page script runs — the app's guard is client-side, so this is how a real session
 *      is established without automating a form;
 *   2. navigates, then **waits for real data to appear** (a selector the page only renders once the
 *      API answered), so a screenshot of an empty shell cannot pass as success;
 *   3. saves the PNG and prints `document.body.innerText`, which is the part a reviewer can grep.
 *
 * Usage (API on :8317, `next start` on :3317):
 *
 *     node --experimental-strip-types scripts/capture-pages.mts
 *     PAGES_BASE_URL=http://127.0.0.1:3317 API_BASE_URL=http://127.0.0.1:8317/api/v1 \
 *       node --experimental-strip-types scripts/capture-pages.mts
 */

import { mkdir, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { spawn } from 'node:child_process';
import path from 'node:path';

const pagesBase = process.env['PAGES_BASE_URL']?.trim() || 'http://127.0.0.1:3317';
const apiBase = process.env['API_BASE_URL']?.trim() || 'http://127.0.0.1:8317/api/v1';
const outDir = process.env['CAPTURE_OUT_DIR']?.trim() || 'reports/screenshots';
const port = Number(process.env['CDP_PORT'] ?? 9333);

const BROWSERS = [
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
];

interface Page {
  name: string;
  path: string;
  /** A selector that only exists once the API's data has rendered. */
  readySelector: string;
  /** Assertions on the rendered text — the part a screenshot cannot be diffed against. */
  expectText: string[];
  /** Text that only the wide layout has (a table header the card layout replaces with a label). */
  wideOnlyText?: string[];
}

const PAGES: Page[] = [
  {
    name: 'ai-runs',
    path: '/app/ai-runs',
    readySelector: '[data-run]',
    expectText: ['AI 运行记录', 'jd_analysis', 'agent_runs / llm_calls'],
    // The narrow layout is a card list: it says `0 tok` where the table has a `Tokens` header.
    wideOnlyText: ['Tokens', 'Latency', 'Status'],
  },
  {
    name: 'costs',
    path: '/app/costs',
    readySelector: '[data-total]',
    expectText: ['AI 成本', '日预算护栏', '缓存命中率', '每日成本'],
  },
];

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
  private pending = new Map<number, { resolve: (value: unknown) => void; reject: (error: Error) => void }>();

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
    const payload = JSON.stringify(sessionId ? { id, method, params, sessionId } : { id, method, params });
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

async function readJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) throw new Error(`${url} → HTTP ${response.status}`);
  return (await response.json()) as T;
}

async function demoSession(): Promise<Record<string, unknown>> {
  const envelope = await readJson<{ data: Record<string, unknown> }>(`${apiBase}/auth/demo`, {
    method: 'POST',
  });
  return { ...envelope.data, storedAt: Date.now() };
}

async function main(): Promise<void> {
  await mkdir(outDir, { recursive: true });
  const session = await demoSession();
  const email = (session['user'] as { email?: string } | undefined)?.email ?? 'unknown';
  console.log(`signed in as ${email} via ${apiBase}`);

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
        version = await readJson<{ webSocketDebuggerUrl: string }>(`http://127.0.0.1:${port}/json/version`);
      } catch {
        version = null;
      }
    }
    if (!version) throw new Error('the browser never opened its debugging port');

    const cdp = await connect(version.webSocketDebuggerUrl);
    let failures = 0;

    for (const viewport of VIEWPORTS) {
      for (const page of PAGES) {
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
          { width: viewport.width, height: viewport.height, deviceScaleFactor: 1, mobile: viewport.width < 500 },
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

        await cdp.send(
          'Page.navigate',
          { url: `${pagesBase}${page.path}` },
          sessionId,
        );

        let rendered = false;
        const renderDeadline = Date.now() + 20_000;
        while (!rendered && Date.now() < renderDeadline) {
          await sleep(300);
          const probe = await cdp.send<{ result: { value?: unknown } }>(
            'Runtime.evaluate',
            { expression: `Boolean(document.querySelector(${JSON.stringify(page.readySelector)}))`, returnByValue: true },
            sessionId,
          );
          rendered = probe.result.value === true;
        }

        const text = await cdp.send<{ result: { value?: string } }>(
          'Runtime.evaluate',
          { expression: 'document.body.innerText', returnByValue: true },
          sessionId,
        );
        const body = text.result.value ?? '';
        const expected = [
          ...page.expectText,
          ...(viewport.width >= 500 ? (page.wideOnlyText ?? []) : []),
        ];
        const missing = expected.filter((needle) => !body.includes(needle));

        const shot = await cdp.send<{ data: string }>(
          'Page.captureScreenshot',
          { format: 'png', captureBeyondViewport: true },
          sessionId,
        );
        const file = path.join(outDir, `${page.name}-${viewport.label}.png`);
        await writeFile(file, Buffer.from(shot.data, 'base64'));

        const status = rendered && missing.length === 0 ? 'ok  ' : 'FAIL';
        if (status === 'FAIL') failures += 1;
        console.log(
          `  ${status} ${page.path} @${viewport.label} → ${file} ` +
            `(${Math.round(shot.data.length * 0.75 / 1024)} KiB)` +
            (rendered ? '' : ' [data never rendered]') +
            (missing.length ? ` [missing text: ${missing.join(' | ')}]` : ''),
        );
        console.log(
          `       text: ${body
            .split('\n')
            .map((line) => line.trim())
            .filter(Boolean)
            .slice(0, 12)
            .join(' ⏐ ')}`,
        );

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
