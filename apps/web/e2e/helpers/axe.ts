import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

import { expect, type Page, type TestInfo } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

/**
 * The result shapes, derived from `AxeBuilder` rather than imported from `axe-core`.
 *
 * `axe-core` is a transitive dependency of `@axe-core/playwright`, and pnpm's node_modules layout
 * does not hoist it into `apps/web` — so importing `axe-core` directly would typecheck here only by
 * accident of the store layout. Deriving the types from the builder keeps this file honest about
 * what it actually depends on.
 */
type AxeResults = Awaited<ReturnType<AxeBuilder['analyze']>>;
type AxeResult = AxeResults['violations'][number];
type AxeNode = AxeResult['nodes'][number];

/**
 * The accessibility gate: axe-core over the real pages, failing on `critical` and `serious` only.
 *
 * Two decisions shape this file.
 *
 * **The impact split is deliberate.** `critical` and `serious` are the levels that make a control
 * unusable — a button with no accessible name, an unlabelled input, a contrast ratio that fails
 * outright. `moderate` and `minor` are reported in the test output and do **not** fail the build,
 * because a gate that fails on a heading-order nit is a gate somebody disables. The counters are
 * printed for every page on every run so the numbers are visible whether or not they are red.
 *
 * **Nothing is excluded.** An earlier draft skipped `.react-flow__*` (the graph canvas) and the
 * `sr-only` class; both exclusions would have hidden real findings behind a rule that reads like
 * noise. The canvas is a genuinely hard surface — it is absolutely-positioned divs with
 * `role="button"` — so instead of excusing it, `assertAccessibleNodeIndex` below checks that the
 * page provides a real equivalent: a list of the same nodes, as focusable buttons with names.
 *
 * **Every finding is written out, not truncated.** A `color-contrast` violation on the shell has
 * *dozens* of failing nodes, and a message that prints five of them and says "…and 119 more" is not
 * a bug report anybody can act on. The full axe result for each page is written to
 * `.tmp/a11y/<page>-<project>.json`, the console gets a per-rule count plus a sample of distinct
 * failing selectors, and the assertion message names the rule and the file to read for the rest.
 *
 * `axe-core` itself is never mocked or stubbed: a page with an error panel passes axe happily, so
 * every caller waits for a ready selector before running it.
 */
export interface PageAxeReport {
  page: string;
  critical: AxeResult[];
  serious: AxeResult[];
  moderate: AxeResult[];
  minor: AxeResult[];
  passes: number;
  incomplete: number;
  /** Path of the JSON with the complete results, for a reviewer who wants every node. */
  reportPath: string;
}

const REPORT_DIR = path.resolve(process.cwd(), '../../.tmp/a11y');

/** One failing node, rendered so the message names the element rather than a rule id alone. */
function describeNode(node: AxeNode): string {
  const target = node.target.map((entry) => String(entry)).join(' ');
  const html = node.html.length > 160 ? `${node.html.slice(0, 157)}…` : node.html;
  return `      ${target}\n        ${html}`;
}

/** Rule id · impact · help URL, plus a bounded sample of the failing nodes. */
export function describeViolations(violations: AxeResult[]): string {
  return violations
    .map((violation) => {
      const nodes = violation.nodes.slice(0, 5).map(describeNode).join('\n');
      const more =
        violation.nodes.length > 5 ? `\n      …and ${violation.nodes.length - 5} more node(s)` : '';
      return (
        `  [${violation.impact ?? 'unknown'}] ${violation.id} — ${violation.help} ` +
        `(${violation.nodes.length} node(s))\n` +
        `    ${violation.helpUrl}\n${nodes}${more}`
      );
    })
    .join('\n\n');
}

export async function runAxe(page: Page, label: string, info: TestInfo): Promise<PageAxeReport> {
  const results = await new AxeBuilder({ page }).analyze();
  const byImpact = (impact: string | null): AxeResult[] =>
    results.violations.filter((violation) => violation.impact === impact);

  await mkdir(REPORT_DIR, { recursive: true });
  const reportPath = path.join(REPORT_DIR, `${label}-${info.project.name}.json`);
  await writeFile(
    reportPath,
    `${JSON.stringify(
      {
        page: label,
        url: page.url(),
        project: info.project.name,
        viewport: page.viewportSize(),
        violations: results.violations.map((violation) => ({
          id: violation.id,
          impact: violation.impact,
          help: violation.help,
          helpUrl: violation.helpUrl,
          nodes: violation.nodes.map((node) => ({
            target: node.target.map((entry) => String(entry)).join(' '),
            html: node.html,
            failureSummary: node.failureSummary,
          })),
        })),
        incomplete: results.incomplete.map((entry) => ({
          id: entry.id,
          impact: entry.impact,
          nodes: entry.nodes.length,
        })),
      },
      null,
      2,
    )}\n`,
    'utf8',
  );

  return {
    page: label,
    critical: byImpact('critical'),
    serious: byImpact('serious'),
    moderate: byImpact('moderate'),
    minor: [...byImpact('minor'), ...byImpact(null)],
    passes: results.passes.length,
    incomplete: results.incomplete.length,
    reportPath,
  };
}

/**
 * Assert the page is free of `critical`/`serious` violations, and *report* the rest.
 *
 * The moderate/minor report goes to stdout (which the `list` reporter prints inline) and to a test
 * annotation, so it survives in the run output without turning into a failure. The summary line is
 * printed unconditionally: a page that is clean should say "0 / 0" rather than say nothing.
 */
export async function expectNoBlockingViolations(
  report: PageAxeReport,
  info: TestInfo,
): Promise<void> {
  const blocking = [...report.critical, ...report.serious];
  const soft = [...report.moderate, ...report.minor];

  const summarise = (violations: AxeResult[]): string =>
    violations
      .map((violation) => `${violation.id}(${violation.impact}, ${violation.nodes.length} nodes)`)
      .join(', ');

  console.log(
    `  axe ${report.page}: ${report.critical.length} critical · ${report.serious.length} serious · ` +
      `${report.moderate.length} moderate · ${report.minor.length} minor ` +
      `(${report.passes} passed checks, ${report.incomplete} incomplete) → ${report.reportPath}`,
  );
  if (blocking.length > 0) console.log(`  axe ${report.page}: BLOCKING — ${summarise(blocking)}`);
  if (soft.length > 0) {
    console.log(`  axe ${report.page}: non-blocking — ${summarise(soft)}`);
    info.annotations.push({
      type: 'a11y-moderate-minor',
      description: `${report.page}: ${summarise(soft)}`,
    });
  }

  expect(
    blocking.length,
    `${report.page} has ${report.critical.length} critical and ${report.serious.length} serious ` +
      `axe violations (every failing node is in ${report.reportPath}):\n` +
      `${describeViolations(blocking)}\n`,
  ).toBe(0);
}

/**
 * The graph's accessible equivalent, asserted rather than assumed.
 *
 * The canvas cannot be made fully accessible as an interaction surface — it is a pannable,
 * zoomable picture — so the requirement the page has to meet is that the *same* information and the
 * *same* selection are reachable without it. That is the node index: one focusable button per node,
 * each carrying its label and kind as text, all of them in the tab order, and pressing one opens
 * exactly the drawer the canvas opens.
 *
 * This is checked here (not only in `evidence-graph.spec.ts`) so the a11y gate is self-contained:
 * if the canvas ever loses its equivalent, the gate that is supposed to notice has the assertion.
 */
export async function assertAccessibleNodeIndex(page: Page): Promise<void> {
  const rows = page.getByTestId('node-index-row');
  const count = await rows.count();
  expect(count, 'the graph must expose its nodes outside the canvas').toBeGreaterThan(0);

  for (let index = 0; index < count; index += 1) {
    const row = rows.nth(index);
    await expect(row).toHaveRole('button');
    // Named, not decorative: the empty string is what an icon-only row would give.
    const name = (await row.evaluate((node) => node.textContent ?? '')).trim();
    expect(name.length, `node index row ${index} has no text`).toBeGreaterThan(0);
    // Reachable by keyboard: a real button is tabbable, and `tabindex="-1"` would take it out.
    await expect(row).not.toHaveAttribute('tabindex', '-1');
  }

  // …and operating one really does what the canvas does.
  await rows.first().click();
  await expect(page.getByTestId('node-drawer')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('node-drawer')).toHaveCount(0);
}
