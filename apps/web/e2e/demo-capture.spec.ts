import { mkdir, readdir, unlink } from 'node:fs/promises';
import path from 'node:path';

import { clickCanvasNode } from './helpers/pages';
import { expect, test, type Locator } from './helpers/fixtures';

/**
 * Frame capture for the README GIF (`docs/assets/evidence-graph-demo.gif`).
 *
 * This spec is not an assertion suite — it is the *source* of the demo animation. It walks the
 * evidence-graph interaction on the live app and writes numbered PNGs; `scripts/make_demo_gif.py`
 * then encodes them and nothing else. Nothing here draws, composites or retouches a screenshot: a
 * demo GIF that shows something the product does not do is the same lie as a fabricated metric.
 *
 * It runs as part of the normal desktop suite, on purpose. A capture step that has to be remembered
 * is a capture step that goes stale, and the interaction is asserted as it walks, so the frames
 * cannot silently stop matching the app. Encoding stays a separate, deliberate step:
 *
 *     pnpm --filter @careerforge/web capture:gif           # rewrite the frames
 *     python scripts/make_demo_gif.py --frames .tmp/graph-frames \
 *       --out docs/assets/evidence-graph-demo.gif
 *
 * The frames are taken at the desktop viewport (the canvas is `hidden lg:block`, so at 375px there
 * would be no graph to show), with reduced motion so a CSS transition cannot land mid-frame and
 * make the animation flicker.
 */
const FRAME_DIR = path.resolve(process.cwd(), '../../.tmp/graph-frames');

/** Clear last run's frames — the encoder globs `*.png`, so a stale frame would be spliced in. */
async function clearFrames(): Promise<void> {
  await mkdir(FRAME_DIR, { recursive: true });
  for (const entry of await readdir(FRAME_DIR)) {
    if (entry.endsWith('.png')) await unlink(path.join(FRAME_DIR, entry));
  }
}

test.describe('Demo frames', () => {
  test('the evidence-graph interaction, frame by frame', async ({
    api,
    evidenceBase,
    signedInPage: page,
  }) => {
    await clearFrames();
    // A stable frame: without this the drawer's slide-in can be captured half-way.
    await page.emulateMedia({ reducedMotion: 'reduce' });

    expect(evidenceBase.total).toBeGreaterThan(0);
    const graph = await api.evidenceGraph('?depth=2');
    const nodeIds = new Set(graph.nodes.map((node) => node.id));
    const evidenceOf = (skillId: string): string[] =>
      graph.edges
        .filter((edge) => edge.relation === 'EVIDENCED_BY' && edge.source === skillId)
        .map((edge) => edge.target)
        .filter((id) => nodeIds.has(id));
    const skill =
      graph.nodes.find((node) => node.type === 'skill' && evidenceOf(node.id).length > 0) ??
      graph.nodes.find((node) => node.type === 'skill');
    if (!skill) throw new Error('GET /evidence-graph returned no skill node to demonstrate');

    let frame = 0;
    const shoot = async (name: string): Promise<void> => {
      frame += 1;
      const file = path.join(FRAME_DIR, `${String(frame).padStart(2, '0')}-${name}.png`);
      await page.screenshot({ path: file });
      console.log(`  frame ${String(frame).padStart(2, '0')} → ${file}`);
    };

    /**
     * Scroll a drawer section into the drawer's own scroll container.
     *
     * `locator.scrollIntoViewIfNeeded()` is not enough here: the drawer body is the scroller, so a
     * section below the fold still has a non-empty bounding box and Playwright's visibility check
     * passes, which makes it skip the scroll entirely. Measured — three consecutive frames came out
     * byte-identical. `Element.scrollIntoView` walks the ancestor scroll containers, which is what
     * a reader's own scroll does.
     */
    const reveal = async (locator: Locator): Promise<void> => {
      await locator.evaluate((element) => element.scrollIntoView({ block: 'center' }));
    };

    await page.goto('/app/evidence-graph');
    // Every node the canvas draws, settled, before the first frame.
    await expect(page.getByTestId('graph-node')).toHaveCount(graph.nodes.length);
    await shoot('graph-loaded');

    // ── focus a skill node: the drawer opens on it ─────────────────────────────────────────────
    // The card's `aria-pressed` is *not* asserted here: it is wired to xyflow's `selected` prop,
    // and the canvas sets `elementsSelectable={false}`, so xyflow never marks a node selected and
    // the attribute stays `false` even while the node is the current selection. That is a real
    // (small) accessibility gap in `components/graph/graph-canvas.tsx` and it is reported rather
    // than asserted as if it were correct.
    await clickCanvasNode(page, skill.id);

    // ── the drawer opens on that node ─────────────────────────────────────────────────────────
    const drawer = page.getByTestId('node-drawer');
    await expect(drawer).toBeVisible();
    await expect(drawer.getByRole('heading', { level: 2 })).toHaveText(skill.label);
    await shoot('node-selected');

    // ── the evidence behind the skill ─────────────────────────────────────────────────────────
    const evidenceSection = drawer.locator('section', { hasText: 'Evidence sources' }).first();
    await reveal(evidenceSection);
    await shoot('evidence-sources');

    const sources = evidenceSection.getByRole('button');
    const sourceCount = await sources.count();
    expect(sourceCount, 'the demo needs a skill with evidence behind it').toBeGreaterThan(0);
    await sources.first().click();

    // ── the evidence node, and the excerpt it rests on ────────────────────────────────────────
    // The excerpt is asserted but not given its own frame: on this width it is already inside the
    // drawer's visible area when the evidence node opens, so a separate screenshot came out
    // byte-identical to the one above (measured) and would only pad the GIF.
    await expect(drawer.getByRole('heading', { level: 2 })).not.toHaveText(skill.label);
    const excerptSection = drawer.locator('section', { hasText: 'Excerpt' }).first();
    await expect(excerptSection).toContainText(/characters|Excerpt unavailable/);
    await shoot('evidence-node');

    // ── the confidence breakdown, which is the "why" of the number ────────────────────────────
    const breakdown = drawer.locator('section', { hasText: 'Confidence breakdown' }).first();
    await expect(breakdown).toBeVisible();
    await reveal(breakdown);
    await shoot('confidence-breakdown');

    // ── back to the picture ───────────────────────────────────────────────────────────────────
    await drawer.getByRole('button', { name: 'Close details' }).click();
    await expect(page.getByTestId('node-drawer')).toHaveCount(0);
    await shoot('drawer-closed');

    expect(frame, 'the encoder needs at least three frames').toBeGreaterThanOrEqual(3);
  });
});
