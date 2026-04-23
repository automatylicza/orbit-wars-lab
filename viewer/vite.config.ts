import { defineConfig } from 'vite';

// NOTE (Task 2): production `pnpm build` is blocked until Task 14 — the
// vendored `@kaggle-environments/core` ships TypeScript source without
// pre-built dist/. Dev mode works fine via the `development` export
// condition (resolves to web/core/src/index.ts). Task 14 will add a
// prebuild script invoking `pnpm --filter @kaggle-environments/core build`.
export default defineConfig({
  optimizeDeps: {
    // Skip Vite's CJS pre-bundle — @kaggle-environments/core is ESM-first TS source.
    exclude: ['@kaggle-environments/core'],
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
});
