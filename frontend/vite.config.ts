import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'
import fs from 'fs'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

function getBackendTarget(): string {
  if (process.env.VITE_API_TARGET) return process.env.VITE_API_TARGET

  const portFile = path.resolve(__dirname, '../backend/logs/.backend.port')
  try {
    const port = fs.readFileSync(portFile, 'utf-8').trim()
    if (/^\d+$/.test(port)) return `http://127.0.0.1:${port}`
  } catch {
    // Backend has not been started by the watchdog yet.
  }
  return 'http://127.0.0.1:33000'
}

export default defineConfig({
  plugins: [
    vue(),
    AutoImport({
      resolvers: [ElementPlusResolver()],
      dts: false,
    }),
    Components({
      resolvers: [ElementPlusResolver()],
      dts: false,
    }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
      '@modules': path.resolve(__dirname, '../modules'),
      'marked': path.resolve(__dirname, 'node_modules/marked'),
      'dompurify': path.resolve(__dirname, 'node_modules/dompurify'),
      'highlight.js': path.resolve(__dirname, 'node_modules/highlight.js'),
      'pdfjs-dist': path.resolve(__dirname, 'node_modules/pdfjs-dist'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    fs: {
      allow: [
        path.resolve(__dirname, '..'),
      ],
    },
    proxy: {
      '/api': {
        target: getBackendTarget(),
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (id.includes('node_modules/@element-plus/icons-vue')) return 'element-icons'
          if (id.includes('node_modules/element-plus/es/components/table')) return 'element-table'
          if (id.includes('node_modules/element-plus/es/components/dialog') || id.includes('node_modules/element-plus/es/components/message')) return 'element-overlay'
          if (id.includes('node_modules/element-plus/es/components')) return 'element-components'
          if (id.includes('node_modules/element-plus') || id.includes('node_modules/@element-plus')) return 'element-core'
          if (id.includes('node_modules/pdfjs-dist')) return 'pdf'
          if (id.includes('node_modules/highlight.js') || id.includes('node_modules/marked')) return 'editor'
        },
      },
    },
  },
})
