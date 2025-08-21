// packages/infra/eslint.config.mjs
import nx from '@nx/eslint-plugin';
import typescriptEslint from '@typescript-eslint/eslint-plugin';
import typescriptParser from '@typescript-eslint/parser';

export default [
  {
    ignores: [
      '**/cdk.out/**',
      '**/.aws-cdk/**',
      '**/dist/**',
      '**/.nx/**',
      '**/node_modules/**',
      '**/*.tsbuildinfo',
      '**/backup/**',
      'test-*.sh',
      'deploy.sh',
      'destroy-and-deploy.sh',
    ],
  },
  {
    files: ['**/*.ts', '**/*.tsx'],
    languageOptions: {
      parser: typescriptParser,
      parserOptions: {
        ecmaVersion: 'latest',
        sourceType: 'module',
      },
    },
    plugins: {
      '@nx': nx,
      '@typescript-eslint': typescriptEslint,
    },
    rules: {
      '@typescript-eslint/no-unused-vars': 'warn',
      '@typescript-eslint/no-explicit-any': 'off',
    },
  },
];