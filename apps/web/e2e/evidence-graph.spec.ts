import { clickCanvasNode, ensureEvidenceBase } from './helpers/pages';
import { expect, test } from './helpers/fixtures';

/**
 * E2E 3 · The evidence graph explorer (`/app/evidence-graph`).
 *
 * The PHASE 12 version of this file could not click a node: the route did not exist, so it proved
 * the *API* built a graph and then drove the public candidate page instead. Both halves are real
 * now, and the spec exercises three surfaces of the one page:
 *
 * 1. **the canvas** (≥1024px) — a node is a `role="button"` card carrying its kind, label and
 *    readout; clicking it opens the drawer;
 * 2. **the node index** — the same nodes as a real list of buttons, which is the accessible
 *    equivalent and the primary view below 1024px (the canvas is `hidden lg:block`). The second
 *    test drives it with the keyboard alone;
 * 3. **the drawer** — the chain the product is about. A skill's drawer lists its evidence sources;
 *    clicking one moves the selection to the evidence node, whose drawer prints the excerpt. That
 *    is Claim → Evidence → Confidence → Source in two clicks, both on screen.
 *
 * The graph is built by the API from a locally uploaded résumé (`POST /profile/import`,
 * `POST /documents`, `POST /documents/{id}/analyze`), so the data is real, and the spec fails
 * loudly if the graph comes back empty rather than passing on nothing.
 *
 * No `waitForTimeout` anywhere: every wait is Playwright's auto-waiting on a real element.
 */
test.describe('Evidence graph', () => {
  test('clicking a skill node opens its drawer, and its evidence is one click further', async ({
    api,
    signedInPage: page,
  }) => {
    const evidenceBase = await ensureEvidenceBase(api);
    expect(
      evidenceBase.kinds['document_chunk'] ?? 0,
      'POST /documents/{id}/analyze must create evidence for the fixture résumé',
    ).toBeGreaterThan(0);

    // ── the payload the page is about to draw ──────────────────────────────────────────────────
    const graph = await api.evidenceGraph('?depth=2');
    expect(graph.nodeCount).toBeGreaterThan(1);
    expect(graph.edgeCount).toBeGreaterThan(1);

    const nodeIds = new Set(graph.nodes.map((node) => node.id));
    const relations = new Set(graph.edges.map((edge) => edge.relation));
    expect(relations.has('DEMONSTRATES')).toBe(true);
    expect(relations.has('EVIDENCED_BY')).toBe(true);
    // Every edge points at a node that is actually in the payload — a dangling edge draws nothing.
    for (const edge of graph.edges) {
      expect(nodeIds.has(edge.source) && nodeIds.has(edge.target), `edge ${edge.id}`).toBe(true);
    }

    // Pick the skill the spec will open. Preferring one that has evidence makes the second half of
    // the flow reachable; the fallback still exercises the drawer's honest empty list.
    const evidenceOf = (skillId: string): string[] =>
      graph.edges
        .filter((edge) => edge.relation === 'EVIDENCED_BY' && edge.source === skillId)
        .map((edge) => edge.target)
        .filter((id) => nodeIds.has(id));
    const skillNodes = graph.nodes.filter((node) => node.type === 'skill');
    expect(skillNodes.length, 'the graph must contain skill nodes to click').toBeGreaterThan(0);
    const skill = skillNodes.find((node) => evidenceOf(node.id).length > 0) ?? skillNodes[0];
    if (!skill) throw new Error('the graph returned no skill node');

    await page.goto('/app/evidence-graph');
    await expect(
      page.getByRole('heading', { level: 1, name: 'Career Evidence Graph' }),
    ).toBeVisible();

    // ── the accessible node list: the same nodes, as named buttons ─────────────────────────────
    await expect(page.getByTestId('node-index')).toBeVisible();
    // The index draws every node the payload carries — it is the accessible equivalent of the
    // canvas, not a summary of it. (`limit: 500` on both sides: the page and this spec ask the API
    // for the identical slice.)
    await expect(page.getByTestId('node-index-row')).toHaveCount(graph.nodes.length);
    await expect(
      page.locator(`[data-testid="node-index-row"][data-node-id="${skill.id}"]`),
    ).toHaveCount(1);

    // ── open the node ──────────────────────────────────────────────────────────────────────────
    if (test.info().project.name === 'mobile') {
      // At 375px the canvas is `hidden lg:block` and the list is the primary view, so driving the
      // list keeps the flow identical to what a phone user actually does.
      await expect(page.getByTestId('graph-canvas')).toBeHidden();
      await page.locator(`[data-testid="node-index-row"][data-node-id="${skill.id}"]`).click();
    } else {
      // The two surfaces have to agree: one drawn card per listed row, or one of them is lying.
      await expect(page.getByTestId('graph-node')).toHaveCount(graph.nodes.length);
      // On the canvas, a node card is a `role=button` whose accessible name is
      // `<kind> <label>. <metric>.` — the click is on the drawn node, not on a list row.
      const canvasNode = page.locator(`[data-testid="graph-node"][data-node-id="${skill.id}"]`);
      await expect(canvasNode).toHaveAttribute('role', 'button');
      await expect(canvasNode).toHaveAttribute('aria-label', new RegExp(skill.label));
      await clickCanvasNode(page, skill.id);
    }

    const drawer = page.getByTestId('node-drawer');
    await expect(drawer).toBeVisible();
    // The drawer is named after the node it describes — a generic title would leave the reader
    // guessing which of thirty nodes they opened.
    await expect(drawer.getByRole('heading', { level: 2 })).toHaveText(skill.label);
    // The selection lives in the URL, so a refresh and a shared link restore the same node.
    expect(page.url()).toMatch(/[?&](skill|node)=/);

    // ── the chain: what backs this skill ───────────────────────────────────────────────────────
    const evidenceSection = drawer.locator('section', { hasText: 'Evidence sources' }).first();
    await expect(evidenceSection).toBeVisible();
    const expectedEvidence = evidenceOf(skill.id);

    if (expectedEvidence.length > 0) {
      // The drawer lists exactly the sources the `EVIDENCED_BY` edges point at: the page does not
      // invent a list, and it does not drop one either.
      await expect(evidenceSection.getByRole('button')).toHaveCount(expectedEvidence.length);
      await evidenceSection.getByRole('button').first().click();

      // The evidence drawer's own section — the excerpt the source rests on.
      await expect(drawer.getByRole('heading', { name: 'Excerpt' })).toBeVisible();
      const excerptSection = drawer.locator('section', { hasText: 'Excerpt' }).first();
      // Either the stored excerpt, or the honest statement that `GET /evidence/{id}` did not
      // return. A blank panel is not an option.
      await expect(excerptSection).toContainText(/characters|Excerpt unavailable/);
      // The excerpt is non-empty whenever the detail read succeeded — the fixture résumé is what
      // the evidence came from, so its words have to be on screen.
      await expect(excerptSection).toContainText(/STM32|FreeRTOS|嵌入式|电机/);
      // The drawer now names the evidence node, not the skill it started from.
      await expect(drawer.getByRole('heading', { level: 2 })).not.toHaveText(skill.label);
    } else {
      // A skill with no evidence is an absence, not a score of zero — the drawer says so.
      await expect(drawer.getByText(/No evidence supports this skill yet/)).toBeVisible();
      await expect(drawer.getByText(/unavailable rather than 0/)).toBeVisible();
    }

    // ── closing returns to the graph, with the selection removed from the URL ──────────────────
    await drawer.getByRole('button', { name: 'Close details' }).click();
    await expect(page.getByTestId('node-drawer')).toHaveCount(0);
    expect(page.url()).not.toMatch(/[?&](skill|node)=/);
  });

  test('the node index is operable from the keyboard alone', async ({
    api,
    signedInPage: page,
  }) => {
    expect((await ensureEvidenceBase(api)).manual.kind).toBe('manual');
    await page.goto('/app/evidence-graph');

    const firstRow = page.getByTestId('node-index-row').first();
    await firstRow.waitFor();
    await firstRow.focus();
    await expect(firstRow).toBeFocused();
    await page.keyboard.press('Enter');

    await expect(page.getByTestId('node-drawer')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByTestId('node-drawer')).toHaveCount(0);
  });
});
