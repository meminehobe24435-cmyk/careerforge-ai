import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Suspense } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { EvidenceGraphView } from '@/components/graph/evidence-graph-view';
import {
  emptyGraphFixture,
  evidenceItems,
  graphFixture,
  ids,
  profileFixture,
  traceFixture,
} from '@/components/graph/graph-fixtures';
import { api } from '@/lib/api';

/**
 * The graph page's contract with its reader.
 *
 * Every case here is a behaviour the brief names, asserted through the DOM rather than through a
 * snapshot: search **dims** and never deletes, the drawer opens with the *source and the
 * confidence* (not just a title), Escape closes it, the URL restores a selection, the node index
 * is a real operable list, and the empty state says the sentence it has to say.
 *
 * jsdom applies no CSS and no layout, so nothing here asserts geometry. The canvas is asserted
 * through `data-dimmed` on its node cards, which is the same fact the opacity conveys.
 */

/* ── a URL that behaves like a URL ─────────────────────────────────────────── */

let search = '';
const listeners = new Set<() => void>();

function applySearch(next: string): void {
  search = next;
  const url = next ? `/app/evidence-graph?${next}` : '/app/evidence-graph';
  window.history.replaceState({}, '', url);
  for (const listener of listeners) listener();
}

vi.mock('next/navigation', async () => {
  const React = await import('react');
  return {
    useSearchParams: () => {
      React.useSyncExternalStore(
        (listener: () => void) => {
          listeners.add(listener);
          return () => listeners.delete(listener);
        },
        () => search,
        () => search,
      );
      return new URLSearchParams(search);
    },
    useRouter: () => ({
      replace: (url: string) => {
        const index = url.indexOf('?');
        applySearch(index === -1 ? '' : url.slice(index + 1));
      },
      push: () => {},
      prefetch: () => {},
    }),
    usePathname: () => '/app/evidence-graph',
  };
});

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return {
    ...actual,
    api: {
      ...actual.api,
      get: vi.fn(),
      post: vi.fn(),
      request: vi.fn(),
    },
  };
});

const mocked = vi.mocked(api);

/** The *latest* graph query — earlier calls are the unfiltered reads that preceded it. */
function graphCall(): Record<string, unknown> | null {
  const calls = mocked.get.mock.calls.filter(([path]) => path === '/evidence-graph');
  const call = calls[calls.length - 1];
  return (call?.[1] as { query?: Record<string, unknown> } | undefined)?.query ?? null;
}

beforeEach(() => {
  search = '';
  window.history.replaceState({}, '', '/app/evidence-graph');
  listeners.clear();
  mocked.get.mockImplementation(async (path: string) => {
    if (path === '/evidence-graph') return graphFixture();
    if (path === '/evidence') return { items: evidenceItems, total: evidenceItems.length };
    if (path === '/profile') return profileFixture;
    if (path.endsWith('/trace')) return traceFixture;
    if (path.startsWith('/evidence/')) return evidenceItems[0];
    throw new Error(`unexpected GET ${path}`);
  });
});

function renderView() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const user = userEvent.setup();
  render(
    <QueryClientProvider client={client}>
      <Suspense fallback={<p>loading</p>}>
        <EvidenceGraphView />
      </Suspense>
    </QueryClientProvider>,
  );
  return user;
}

async function renderReady() {
  const user = renderView();
  await screen.findByTestId('node-index');
  return user;
}

function indexRow(nodeId: string): HTMLElement {
  const row = document.querySelector(`[data-testid="node-index-row"][data-node-id="${nodeId}"]`);
  expect(row).not.toBeNull();
  return row as HTMLElement;
}

/** The canvas cards, if the dynamic import has resolved in this environment. */
function canvasCards(): HTMLElement[] {
  return [...document.querySelectorAll<HTMLElement>('[data-testid="graph-node"]')];
}

describe('the Career Evidence Graph page', () => {
  it('dimms the nodes that do not match a search instead of deleting them', async () => {
    const user = await renderReady();
    const before = document.querySelectorAll('[data-testid="node-index-row"]').length;
    expect(before).toBeGreaterThan(0);

    await user.type(screen.getByLabelText('Search nodes'), 'linux');

    // Every row is still there: search narrows the *contrast*, not the data.
    expect(document.querySelectorAll('[data-testid="node-index-row"]').length).toBe(before);
    expect(indexRow(ids.linux)).toHaveAttribute('data-dimmed', 'false');
    expect(indexRow(ids.freeRtos)).toHaveAttribute('data-dimmed', 'true');
    expect(within(indexRow(ids.freeRtos)).getByText('dimmed')).toBeInTheDocument();
    expect(within(indexRow(ids.linux)).getByText('match')).toBeInTheDocument();

    // The canvas carries the same state on the same nodes: dimmed, not removed. It is a dynamic
    // import, so this waits for it to land rather than assuming it already has.
    await waitFor(() => expect(canvasCards().length).toBe(before));
    const card = (id: string) =>
      document.querySelector(`[data-testid="graph-node"][data-node-id="${id}"]`);
    expect(card(ids.linux)).toHaveAttribute('data-dimmed', 'false');
    expect(card(ids.freeRtos)).toHaveAttribute('data-dimmed', 'true');
    // The candidate stays lit next to the hit: the hit and its neighbours are the readable core.
    expect(card(ids.candidate)).toHaveAttribute('data-dimmed', 'false');
  });

  it('opens the evidence drawer with the source, the excerpt and the confidence arithmetic', async () => {
    const user = await renderReady();

    await user.click(indexRow(ids.resume));

    const drawer = await screen.findByTestId('node-drawer');
    expect(within(drawer).getByText('resume.txt')).toBeInTheDocument();
    // Source type, the source itself, and where inside it.
    expect(within(drawer).getByText('Document chunk')).toBeInTheDocument();
    expect(within(drawer).getByText(/chars 0–406/)).toBeInTheDocument();
    // The excerpt is monospace and clipped, with the full length stated.
    expect(within(drawer).getByText(/使用 STM32 与 FreeRTOS 开发电机控制固件/)).toBeInTheDocument();
    expect(within(drawer).getByText(/characters/)).toBeInTheDocument();
    // Confidence, and the five factors it is made of.
    expect(within(drawer).getAllByText('0.80').length).toBeGreaterThan(0);
    expect(within(drawer).getByText('Source authority')).toBeInTheDocument();
    // The factor column adds up to the stored score, and the drawer prints both.
    expect(within(drawer).getAllByText('0.800').length).toBeGreaterThanOrEqual(2);
    expect(
      within(drawer).getByText('confidence@1.0.0 — weight × factor, added up.'),
    ).toBeInTheDocument();
    // The reverse-provenance half of the chain.
    // Named as a citing skill, and also inside the excerpt itself.
    expect(within(drawer).getAllByText('FreeRTOS').length).toBeGreaterThan(0);
  });

  it('closes the drawer on Escape and leaves the graph in place', async () => {
    const user = await renderReady();
    await user.click(indexRow(ids.freeRtos));
    await screen.findByTestId('node-drawer');

    await user.keyboard('{Escape}');

    await waitFor(() => expect(screen.queryByTestId('node-drawer')).not.toBeInTheDocument());
    expect(screen.getByTestId('node-index')).toBeInTheDocument();
    expect(indexRow(ids.freeRtos)).toBeInTheDocument();
  });

  it('restores the selection and the canvas scope from ?skill=', async () => {
    applySearch('skill=free_rtos');
    renderView();

    const drawer = await screen.findByTestId('node-drawer');
    // Named as a citing skill, and also inside the excerpt itself.
    expect(within(drawer).getAllByText('FreeRTOS').length).toBeGreaterThan(0);
    // The deep link is also a scope: the API is asked for that node's neighbourhood.
    await waitFor(() => expect(graphCall()?.['focus']).toBe('skill:free_rtos'));
    // A skill shows its sources, its declared strength and the project that demonstrates it.
    expect(within(drawer).getByText('Sources in this view')).toBeInTheDocument();
    expect(within(drawer).getByText('strong')).toBeInTheDocument();
    expect(within(drawer).getAllByText('Balance Robot 2022').length).toBeGreaterThan(0);
    expect(within(drawer).getByText('Projects demonstrating it')).toBeInTheDocument();
  });

  it('puts a clicked skill in the URL by its canonical id, so the link is shareable', async () => {
    const user = await renderReady();
    await user.click(indexRow(ids.freeRtos));
    await waitFor(() => expect(search).toBe('skill=free_rtos'));
    expect(search).toContain('skill=free_rtos');
  });

  it('offers the node index as a real, operable list and reflects the selection in it', async () => {
    const user = await renderReady();

    const list = document.querySelector('[data-testid="node-index"] ul');
    expect(list).not.toBeNull();
    expect(screen.getAllByRole('listitem').length).toBe(7);
    // The row *is* the button — the list is a real list of operable controls, not a table of
    // labels with a link somewhere inside it.
    const row = indexRow(ids.can);
    expect(row.tagName).toBe('BUTTON');
    expect(row).toHaveAccessibleName(/CAN/);

    row.focus();
    await user.keyboard('{Enter}');

    await screen.findByTestId('node-drawer');
    await waitFor(() => expect(indexRow(ids.can)).toHaveAttribute('aria-current', 'true'));
  });

  it('says the empty-state sentence and offers the action that fixes it', async () => {
    mocked.get.mockImplementation(async (path: string) => {
      if (path === '/evidence-graph') return emptyGraphFixture();
      if (path === '/evidence') return { items: [], total: 0 };
      if (path === '/profile') return profileFixture;
      throw new Error(`unexpected GET ${path}`);
    });
    renderView();

    expect(
      await screen.findByText(
        'Your graph is built from your resume, projects and repositories. Import a profile to start connecting evidence.',
      ),
    ).toBeInTheDocument();
    // The action is real, not a link to a route that does not exist.
    expect(screen.getByRole('button', { name: /Import and analyse/ })).toBeInTheDocument();
    expect(screen.getByLabelText('Profile text')).toBeInTheDocument();
  });

  it('sends the node-kind filter to the API instead of hiding nodes locally', async () => {
    const user = await renderReady();
    expect(graphCall()?.['types']).toBeUndefined();

    await user.click(screen.getByRole('button', { name: 'Filter' }));
    const panel = await screen.findByRole('dialog', { name: 'Filter' });
    await user.click(within(panel).getByRole('button', { name: /Project/ }));

    await waitFor(() => expect(graphCall()?.['types']).toBeTruthy());
    const types = String(graphCall()?.['types']).split(',');
    expect(types).not.toContain('project');
    expect(types).toContain('skill');
    expect(search).toContain('hide=project');
  });

  it('never prints 0.00 for a confidence nobody measured', async () => {
    mocked.get.mockImplementation(async (path: string) => {
      if (path === '/evidence-graph') {
        const base = graphFixture();
        return {
          ...base,
          nodes: base.nodes.map((node) => ({ ...node, confidence: null })),
          stats: { ...base.stats, mean_confidence: 0, high_confidence: 0, low_confidence: 0 },
        };
      }
      if (path === '/evidence') return { items: [], total: 0 };
      if (path === '/profile') return profileFixture;
      if (path.endsWith('/trace')) return { evidenceId: ids.resume, citedBy: [] };
      return evidenceItems[0];
    });
    renderView();
    await screen.findByTestId('node-index');

    expect(screen.getByText('Mean confidence')).toBeInTheDocument();
    const strip = screen.getByText('Mean confidence').parentElement as HTMLElement;
    expect(strip.textContent).toContain('—');
    expect(strip.textContent).not.toContain('0.00');
  });

  it('reads a stale ?skill= as a stale link rather than as an error', async () => {
    applySearch('skill=does_not_exist');
    renderView();
    await screen.findByTestId('node-index');

    expect(screen.getByRole('status').textContent).toContain('?skill=does_not_exist');
    expect(screen.queryByTestId('node-drawer')).not.toBeInTheDocument();
    // The view still renders: a stale bookmark is not a failure.
    expect(screen.getByText('Career Evidence Graph')).toBeInTheDocument();
  });

  it('shows a failed read with its code and request id instead of an empty canvas', async () => {
    const { ApiError } = await import('@/lib/api');
    mocked.get.mockRejectedValue(
      new ApiError({
        code: 'INTERNAL_ERROR',
        message: 'boom',
        requestId: 'req_graph',
        status: 500,
        body: null,
      }),
    );
    renderView();

    expect(await screen.findByText('INTERNAL_ERROR', {}, { timeout: 5_000 })).toBeInTheDocument();
    expect(screen.getByText('req_graph')).toBeInTheDocument();
    expect(screen.queryByTestId('node-index')).not.toBeInTheDocument();
  });
});
