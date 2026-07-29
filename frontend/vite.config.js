import { defineConfig } from 'vite'
import { resolve } from 'node:path'

// Built into `dist/`, which the Python server mounts. Kept out of git —
// build output is generated, not source.
export default defineConfig({
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        // The viewer, and a development-only pose tuner. Gesture angles
        // cannot be tuned by reasoning about a rig; they have to be watched.
        main: resolve(__dirname, 'index.html'),
        tune: resolve(__dirname, 'tune.html'),
      },
    },
  },
  server: {
    // `npm run dev` proxies the API to the simulation server, so the
    // frontend can hot-reload without a build step.
    proxy: {
      '/api': 'http://127.0.0.1:8600',
      '/ws': { target: 'ws://127.0.0.1:8600', ws: true },
    },
  },
})
