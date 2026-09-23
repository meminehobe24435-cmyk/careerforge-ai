import tseslint from 'typescript-eslint';

/**
 * `@careerforge/ui` lint config: typescript-eslint recommended (no type-aware rules —
 * the packages are type-checked separately by `pnpm typecheck`) plus the design-token
 * guard from docs/UI.md §2.1.
 */
export default tseslint.config(
  { ignores: ['node_modules/**', 'dist/**'] },
  ...tseslint.configs.recommended,
  {
    files: ['**/*.{ts,tsx}'],
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
);
