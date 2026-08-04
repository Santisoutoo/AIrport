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
    rules: {
      'no-empty': ['error', { allowEmptyCatch: true }],
    },
  }
);
