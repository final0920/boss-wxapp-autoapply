import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { TanStackRouterVite } from '@tanstack/router-plugin/vite'

export default defineConfig({
  plugins: [
    TanStackRouterVite({ target: 'react', autoCodeSplitting: true }),
    react(),
  ],
  server: {
    port: 5180,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8010',
        changeOrigin: true,
      },
      '/socket.io': {
        target: 'http://127.0.0.1:8010',
        changeOrigin: true,
        ws: true,
      },
      '/ws': {
        target: 'http://127.0.0.1:8010',
        changeOrigin: true,
        ws: true,
      },
    },
  },
})
