import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const backendPort = process.env.BACKEND_PORT || '8000'
const frontendPort = Number(process.env.PORT) || 5173

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: frontendPort,
    proxy: {
      '/api': {
        target: `http://127.0.0.1:${backendPort}`,
        changeOrigin: true,
      },
    },
  },
})
