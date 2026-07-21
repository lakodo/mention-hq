import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';
import { fileURLToPath, URL } from 'node:url';

export default defineConfig({
  plugins: [
    react(),
    // Only in a real build — under vitest the service worker has nothing to do and would
    // only add noise. autoUpdate rolls a new build straight through: no "reload to update"
    // prompt, which is what you want for a tool you keep open and rebuild often.
    ...(process.env.VITEST
      ? []
      : [
          VitePWA({
            registerType: 'autoUpdate',
            injectRegister: 'auto',
            includeAssets: ['icon.svg', 'icon-maskable.svg'],
            manifest: {
              name: 'Personal HQ',
              short_name: 'HQ',
              description:
                'Your activity across GitHub, Linear, Slack, Notion and local files, grouped by subject.',
              start_url: '/',
              scope: '/',
              display: 'standalone',
              theme_color: '#ffffff',
              background_color: '#f8f9fa',
              icons: [
                { src: 'icon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any' },
                {
                  src: 'icon-maskable.svg',
                  sizes: 'any',
                  type: 'image/svg+xml',
                  purpose: 'maskable',
                },
              ],
            },
            workbox: {
              globPatterns: ['**/*.{js,css,html,svg,woff,woff2}'],
              // The API is data, never the app shell: a client-side route falls back to
              // index.html, but an /api path must always reach the backend over the network.
              navigateFallbackDenylist: [/^\/api\//],
            },
          }),
        ]),
  ],
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
    // One fork per core (15 here) oversubscribes badly: each runs jsdom + msw, and the GC
    // pauses starve a Mantine Menu's open at click time — its dropdown never mounts within the
    // findBy ceiling and a row-menu test flakes. Capping workers keeps real parallelism while
    // leaving each one enough CPU to render a portal promptly. Also steadier on CI's fewer cores.
    maxWorkers: 4,
    minWorkers: 1,
    // Headroom for a test that chains several portalled transitions (open menu, pick, confirm),
    // each a findBy wait — so a brief contention spike can't trip vitest's default 5s ceiling.
    testTimeout: 20000,
    // The app reads this for its API base; an absolute value keeps msw matching on a full
    // URL, which its onUnhandledRequest:'error' guard needs.
    env: {
      VITE_API_URL: 'http://localhost:8000/api',
    },
  },
});
