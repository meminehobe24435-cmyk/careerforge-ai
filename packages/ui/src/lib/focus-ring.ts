/**
 * The 2px brand focus ring, as one class string the primitives compose.
 *
 * docs/UI.md §9 requires "2px 品牌色 focus ring（`outline-offset: 2px`），不依赖 `:hover`" on every
 * interactive element. This constant exists because the obvious way to write that in Tailwind v4 is
 * silently broken, and it was broken everywhere:
 *
 * ```tsx
 * // WRONG — renders no ring at all
 * 'outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand'
 * ```
 *
 * Tailwind v4's `outline-none` sets a custom property *on the element* and the width utility reads
 * that same property back (verbatim from the generated CSS):
 *
 * ```css
 * .outline-none { --tw-outline-style: none; outline-style: none }
 * .focus-visible\:outline-2:focus-visible { outline-style: var(--tw-outline-style); outline-width: 2px }
 * ```
 *
 * so `outline-style` resolves to `none` and the ring never appears — while `:focus-visible` *does*
 * match. Measured in the browser on the PHASE 14 build: `element.matches(':focus-visible')` was
 * `true` and `getComputedStyle(element).outlineStyle` was `'none'` on every Button, IconButton,
 * sidebar link and tooltip trigger. axe cannot see this (axe-core has no focus-visible rule), and no
 * component test can either — jsdom computes no styles. Only a real browser reading a real computed
 * value finds it, which is why the fix is a shared constant rather than the same literal repeated:
 * the next person to write a focus style should not have to rediscover the trap.
 *
 * Dropping `outline-none` is the whole fix. While unfocused, `outline-style` sits at its initial
 * value (`none`), and on `:focus-visible` the utilities below draw the ring — `outline-style`
 * resolves through `--tw-outline-style`, whose registered initial value is `solid`. The identical
 * ring also comes from the `:focus-visible` rule in the app's `globals.css`; keeping it explicit
 * here means a component carries its own focus contract instead of depending on a global.
 */
export const focusRing =
  'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand';
