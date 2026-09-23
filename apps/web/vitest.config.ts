import { fileURLToPath } from 'node:url';

import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

/**
 * Vitest for the web client.
 *
 * The two workspace packages (`@careerforge/shared`, `@careerforge/ui`) publish TypeScript
 * *source* through their `exports` map, and pnpm symlinks them out of `node_modules` — so
 * Vite sees them as ordinary project files and transpiles them like the app's own code.
 * That is deliberate: there is no build step between writing a contract type and a test
 * asserting against it, which is the point of putting the contract in a package.
 *
 * `jsdom` rather than `happy-dom`: the board's keyboard path is verified through real DOM
 * events (focus, key sequences) and dnd-kit reads layout metrics, so the environment that
 * behaves most like a browser wins over the faster one.
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    // A component test that silently renders nothing is worse than a failing one.
    restoreMocks: true,
  },
});
