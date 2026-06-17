import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@modules': path.resolve(__dirname, '..'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: Number(process.env.VITE_SANDBOX_PORT) || 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET || 'http://127.0.0.1:30004',
        changeOrigin: true,
      },
    },
  },
})
