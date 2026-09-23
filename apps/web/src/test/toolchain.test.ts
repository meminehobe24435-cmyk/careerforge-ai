import { describe, expect, it } from 'vitest';

import { APPLICATION_STATUSES, isApplicationBoard } from '@careerforge/shared';

/**
 * Toolchain canary.
 *
 * The board's real tests live beside their components; this file exists so that a broken
 * transform/resolution path (esbuild's service, a workspace `exports` change, jsdom) fails
 * with one obvious name instead of twenty confusing ones.
 */
describe('web test toolchain', () => {
  it('resolves the shared contract package as TypeScript source', () => {
    expect(APPLICATION_STATUSES).toHaveLength(7);
    expect(APPLICATION_STATUSES[0]).toBe('wishlist');
  });

  it('rejects a payload that is not a board', () => {
    expect(isApplicationBoard(null)).toBe(false);
    expect(isApplicationBoard({ columns: 'nope' })).toBe(false);
  });
});
