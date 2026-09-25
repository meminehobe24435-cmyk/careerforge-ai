import { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

import { FlatCompat } from '@eslint/eslintrc';

const __dirname = dirname(fileURLToPath(import.meta.url));
const compat = new FlatCompat({ baseDirectory: __dirname });

/**
 * ESLint 9 flat config for the web app.
 *
 * `eslint-config-next@15` still ships the eslintrc format, so it is bridged with
 * `FlatCompat`. On top of it sits this repository's own rule: colours must come from
 * design tokens (docs/UI.md §2.1) — a raw hex literal in a component fails the lint.
 *
 * The `ignores` pattern covers every `.next*` directory rather than only `.next`: a verification
 * run that builds with a custom `distDir` (`.next-p14`, `.next-a11y`) leaves a second compiled
 * output in the tree, and linting a webpack bundle produced 14,840 findings about `require()` calls
 * in minified code while saying nothing about the source. Compiled output is never source.
 */
export default [
  {
    ignores: ['.next*/**', 'node_modules/**', 'next-env.d.ts', 'eslint.config.mjs'],
  },
  ...compat.extends('next/core-web-vitals', 'next/typescript'),
  {
    files: ['src/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-syntax': [
        'error',
        {
          selector:
            'Literal[value=/^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/]',
          message:
            'Raw hex colour detected. Colours must come from design tokens (docs/UI.md §2.1) via Tailwind utilities such as bg-surface / text-evidence.',
        },
      ],
    },
  },
];
