import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import { fileURLToPath, URL } from 'node:url';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 13001,
    strictPort: true,
    // Whatever local name you front the app with (via the Caddy proxy) reaches Vite as an
    // unknown Host, which it blocks by default. This is a single-user dev server on
    // loopback, so accept any name rather than hardcode one.
    allowedHosts: true,
    // Plain `task dev` has no Caddy in front, so Vite forwards the API itself. Same-origin
    // as the page, so no CORS — matching how Caddy and the built-SPA server behave.
    proxy: {
      '/api': 'http://localhost:13000',
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    // The app reads this for its API base; an absolute value keeps msw matching on a full
    // URL, which its onUnhandledRequest:'error' guard needs.
    env: {
      VITE_API_URL: 'http://localhost:8000/api',
    },
  },
});
