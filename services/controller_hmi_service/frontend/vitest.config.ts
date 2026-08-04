import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    include: ['src/**/*.test.ts'],
    environment: 'node', // pure-logic tests; switch per-file to happy-dom when DOM is needed
  },
});
