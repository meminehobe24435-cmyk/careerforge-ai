import '@testing-library/jest-dom/vitest';

import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

/**
 * jsdom does not implement the APIs dnd-kit needs to measure a drag, so they are stubbed
 * here rather than mocked away per test. Each stub returns a *plausible* rectangle instead
 * of zeros: a zero-sized rectangle makes every droppable equidistant and turns a layout bug
 * into a passing test.
 */
const RECT = { width: 120, height: 64, top: 0, left: 0, right: 120, bottom: 64, x: 0, y: 0 };

Object.defineProperty(HTMLElement.prototype, 'getBoundingClientRect', {
  configurable: true,
  value: () => ({ ...RECT, toJSON: () => RECT }),
});

if (!('ResizeObserver' in globalThis)) {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}

// jsdom's `matchMedia` is missing, and the app's theme provider asks for it on mount.
if (!window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

// `scrollIntoView` is called by Radix's focus management, which jsdom does not implement.
Element.prototype.scrollIntoView = vi.fn();

/**
 * Pointer Events, which jsdom does not implement at all.
 *
 * Radix (the dropdown menu on every card) and dnd-kit's pointer sensor both speak pointer
 * events, and `user-event` refuses to synthesise them without a constructor. Aliasing
 * `PointerEvent` to `MouseEvent` is the standard shim: the fields the libraries read
 * (`clientX`, `clientY`, `button`, `isPrimary`) either exist on `MouseEvent` or are added
 * below, and nothing in these tests depends on pressure/tilt.
 */
if (!('PointerEvent' in window)) {
  // The cast is needed because TypeScript narrows `window` to `never` inside this branch —
  // the check itself is the reason the property is unknown to the type system.
  (window as unknown as Record<string, unknown>)['PointerEvent'] = MouseEvent;
}
Object.defineProperty(MouseEvent.prototype, 'isPrimary', {
  configurable: true,
  get: () => true,
});
for (const method of ['setPointerCapture', 'releasePointerCapture'] as const) {
  if (!Element.prototype[method]) {
    Object.defineProperty(Element.prototype, method, { configurable: true, value: () => {} });
  }
}
if (!Element.prototype.hasPointerCapture) {
  Object.defineProperty(Element.prototype, 'hasPointerCapture', {
    configurable: true,
    value: () => false,
  });
}

afterEach(() => {
  cleanup();
});
