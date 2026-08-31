import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The UI runs on 5173 and forwards every /api call to the Python backend on 8000,
// so the browser only ever talks to a single origin.
export default defineConfig({
  plugins: [react()],
  server: {
    port: Number(process.env.FRONTEND_PORT) || 5173,
    strictPort: true,
    host: '127.0.0.1',
    proxy: {
      '/api': {
        target: `http://127.0.0.1:${process.env.API_PORT || 8000}`,
        changeOrigin: true,
      },
    },
  },
})
