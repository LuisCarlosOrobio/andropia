import { defineConfig } from 'vite'

// Built into `dist/`, which the Python server mounts. Kept out of git —
// build output is generated, not source.
export default defineConfig({
  build: { outDir: 'dist', emptyOutDir: true },
  server: {
    // `npm run dev` proxies the API to the simulation server, so the
    // frontend can hot-reload without a build step.
    proxy: {
      '/api': 'http://127.0.0.1:8600',
      '/ws': { target: 'ws://127.0.0.1:8600', ws: true },
    },
  },
})
