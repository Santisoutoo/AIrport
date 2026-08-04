import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import prettier from 'eslint-config-prettier';

export default tseslint.config(
  js.configs.recommended,
  ...tseslint.configs.recommended,
  prettier,
  {
    languageOptions: {
      globals: {
        window: 'readonly',
        document: 'readonly',
        location: 'readonly',
        localStorage: 'readonly',
        fetch: 'readonly',
        navigator: 'readonly',
        crypto: 'readonly',
        console: 'readonly',
        setTimeout: 'readonly',
        clearTimeout: 'readonly',
        setInterval: 'readonly',
        clearInterval: 'readonly',
        requestAnimationFrame: 'readonly',
        cancelAnimationFrame: 'readonly',
        WebSocket: 'readonly',
        MediaRecorder: 'readonly',
        AudioContext: 'readonly',
        FormData: 'readonly',
        Blob: 'readonly',
        Uint8Array: 'readonly',
      },
    },
  },
  {
    // Pre-migration vanilla JS: rules that would force rewrites are relaxed
    // here and removed file-by-file as each module is converted to TS
    // (epic #59, Phase 2).
    files: ['src/legacy/**/*.js'],
    rules: {
      'no-var': 'off',
      'prefer-const': 'off',
      'no-empty': ['error', { allowEmptyCatch: true }],
      'no-unused-vars': 'off',
      '@typescript-eslint/no-unused-vars': ['warn', { args: 'none' }],
      '@typescript-eslint/no-unused-expressions': 'off',
    },
  }
);
