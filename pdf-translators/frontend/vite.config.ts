import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Backend (Flask) default port. `npm run dev` proxies the JSON API to it so
// you get Vite HMR on the UI while the real Python backend handles load/save.
const BACKEND = process.env.BACKEND || 'http://127.0.0.1:5107'

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': BACKEND,
    },
  },
  build: {
    // Flask serves dist/ as the production bundle.
    outDir: 'dist',
    emptyOutDir: true,
  },
})
