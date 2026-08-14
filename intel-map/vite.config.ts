import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: '/neo/',
  server: {
    port: 3001,
    strictPort: true,
    proxy: {
      '/api': 'http://localhost:8000',
    },
    hmr: {
      host: 'localhost',
      port: 3001,
      clientPort: 3001,
    },
  },
})
