import { openPopulatedPage } from './helpers/pages';
import { expect, test } from './helpers/fixtures';

/**
 * The horizontal-overflow guard, at 375 / 768 / 1440.
 *
 * **The historical bug this prevents.** In PHASE 11 `/app/costs` rendered a nine-column table whose
 * `Daily cost` column was pushed past the right edge of a 375px viewport: the page scrolled
 * sideways, so the number the page exists to show was off screen and looked absent. Nothing in the
 * test suite could see it — a table wider than its container is perfectly valid DOM, and jsdom has
 * no layout at all, so `scrollWidth` there is always 0. The fix was the card-list layout below
 * `md` (`run-table.tsx`), and this spec is the guard that keeps the fix from being undone by the
 * next wide panel somebody adds.
 *
 * **Why `documentElement.scrollWidth`.** A page that overflows horizontally makes the *root*
 * element wider than the viewport, which is exactly the quantity a user experiences as "the page
 * slides sideways". Comparing it to `window.innerWidth` catches overflow wherever it comes from —
 * a table, a `min-w-` on a flex child, a negative margin, an absolutely-positioned popover that is
 * never closed — without the spec having to guess which element is at fault.
 *
 * **Why the +2 slack.** `innerWidth` is an integer and `scrollWidth` is rounded differently by the
 * engine at fractional device-pixel ratios, so a 1px disagreement is a rounding artefact rather
 * than a layout bug. Two pixels is the smallest tolerance that does not produce false positives;
 * the PHASE 11 regression was dozens of pixels wide, not two.
 *
 * **Why the widest offender is reported.** "scrollWidth 812 > 375" is a failed assertion; naming
 * the element that is 812px wide, with its text, is a bug report. When the assertion fails, the
 * spec walks the DOM for the elements whose right edge is past the viewport and prints them.
 *
 * **Why the page is driven once and then only resized.** Each page is mounted at the narrowest
 * width, populated through the UI, and then *resized* — not reloaded — for the other two
 * measurements. Reloading would lose the state two of these pages keep in the component
 * (`/app/validator`'s verdict, `/app/jobs`' computed match), so the populated layout — the one that
 * overflowed — would never be measured; and re-driving the page three times costs three
 * `POST /jobs/analyze` + `POST /jobs/{id}/match` calls against the per-minute `ai` bucket for no
 * extra evidence. Resizing is also what the reader does when they rotate a phone.
 *
 * The spec runs in the desktop project only: it sets all three viewports itself, so running it in
 * both projects would repeat every measurement and double-count the same assertion.
 */
const WIDTHS = [
  { width: 375, height: 812 },
  { width: 768, height: 900 },
  { width: 1440, height: 900 },
] as const;

const PAGES = [
  'dashboard',
  'jobs',
  'evidence-graph',
  'validator',
  'interview',
  'ai-runs',
  'costs',
] as const;

/**
 * The elements sticking out past the right edge, widest first.
 *
 * Deliberately excludes elements a reader can never scroll to: `position: fixed`/`absolute`
 * descendants of a *closed* dialog (Radix keeps them mounted with `pointer-events: none`), hidden
 * elements, and anything inside `aria-hidden`.
 */
async function widestOffenders(
  page: import('@playwright/test').Page,
  viewport: number,
): Promise<string[]> {
  return page.evaluate((limit: number) => {
    const offenders: Array<{ width: number; what: string }> = [];
    for (const element of Array.from(document.querySelectorAll('body *'))) {
      const box = element.getBoundingClientRect();
      if (box.width === 0 || box.height === 0) continue;
      if (box.right <= limit + 2 && box.left >= -2) continue;
      const style = getComputedStyle(element);
      if (style.visibility === 'hidden' || style.display === 'none') continue;
      if (style.pointerEvents === 'none') continue;
      if (element.closest('[aria-hidden="true"]')) continue;
      const label = (element.textContent ?? '').trim().replace(/\s+/g, ' ').slice(0, 60);
      offenders.push({
        width: Math.round(box.width),
        what: `<${element.tagName.toLowerCase()}${element.className ? ` class="${String(element.className).slice(0, 60)}"` : ''}> ${label}`,
      });
    }
    return offenders
      .sort((a, b) => b.width - a.width)
      .slice(0, 5)
      .map((entry) => `${entry.width}px wide — ${entry.what}`);
  }, viewport);
}

test.describe('Horizontal overflow', () => {
  for (const name of PAGES) {
    test(`${name} does not overflow horizontally at 375, 768 or 1440`, async ({
      evidenceBase,
      jobId,
      signedInPage: page,
    }) => {
      // The account's data is prepared once per worker by the fixtures; the layout is what changes
      // between the three measurements. Asserted so a measurement of an empty account is visible
      // as such rather than passing quietly.
      expect(evidenceBase.total).toBeGreaterThan(0);
      expect(jobId.length).toBeGreaterThan(0);

      // Mount at the narrowest width first, so the mobile layout is the one that goes through the
      // normal first paint rather than through a resize.
      const narrow = WIDTHS[0];
      await page.setViewportSize({ width: narrow.width, height: narrow.height });
      await openPopulatedPage(page, jobId, name);

      for (const size of WIDTHS) {
        await page.setViewportSize({ width: size.width, height: size.height });
        // `innerWidth` can lag a frame behind `setViewportSize`; measuring before it settles would
        // compare the scroll width of one viewport against the width of another.
        await expect
          .poll(async () => page.evaluate(() => window.innerWidth), { timeout: 5000 })
          .toBe(size.width);

        const { scrollWidth, innerWidth } = await page.evaluate(() => ({
          scrollWidth: document.documentElement.scrollWidth,
          innerWidth: window.innerWidth,
        }));

        const offenders = await widestOffenders(page, size.width);
        expect(
          scrollWidth,
          `${name} @${size.width}px: documentElement.scrollWidth ${scrollWidth} > ` +
            `window.innerWidth ${innerWidth} + 2.\n` +
            (offenders.length > 0
              ? `Widest elements past the right edge:\n  ${offenders.join('\n  ')}`
              : 'No single element was found past the edge; check for a negative margin.'),
        ).toBeLessThanOrEqual(size.width + 2);
      }
    });
  }
});
