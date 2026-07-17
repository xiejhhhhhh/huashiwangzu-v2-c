import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'
import fs from 'fs'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

interface DevServerConfig {
  backend_base_url?: string
  frontend_base_url?: string
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

function readProjectConfigFile(filePath: string): DevServerConfig | null {
  try {
    const parsed: unknown = JSON.parse(fs.readFileSync(filePath, 'utf-8'))
    if (!isRecord(parsed)) return null
    return {
      backend_base_url: typeof parsed.backend_base_url === 'string' ? parsed.backend_base_url : undefined,
      frontend_base_url: typeof parsed.frontend_base_url === 'string' ? parsed.frontend_base_url : undefined,
    }
  } catch {
    return null
  }
}

function getProjectConfig(): DevServerConfig {
  const configFiles = [
    path.resolve(__dirname, '../dev_toolkit/config.local.json'),
    path.resolve(__dirname, '../dev_toolkit/config.example.json'),
  ]
  for (const filePath of configFiles) {
    const config = readProjectConfigFile(filePath)
    if (config) return config
  }
  return {}
}

function getConfiguredPort(baseUrl: string | undefined): number | null {
  if (!baseUrl) return null
  try {
    const parsed = new URL(baseUrl)
    if (!parsed.port) return null
    const port = Number(parsed.port)
    return Number.isInteger(port) && port > 0 ? port : null
  } catch {
    return null
  }
}

const projectConfig = getProjectConfig()

function getBackendTarget(): string {
  if (process.env.VITE_API_TARGET) return process.env.VITE_API_TARGET
  if (projectConfig.backend_base_url) return projectConfig.backend_base_url

  const portFile = path.resolve(__dirname, '../backend/logs/.backend.port')
  try {
    const port = fs.readFileSync(portFile, 'utf-8').trim()
    if (/^\d+$/.test(port)) return `http://127.0.0.1:${port}`
  } catch {
    // Backend has not been started by the watchdog yet.
  }
  throw new Error('Backend target is not configured. Set VITE_API_TARGET or dev_toolkit/config.local.json backend_base_url.')
}

function getFrontendPort(): number {
  const envPort = process.env.VITE_FRONTEND_PORT || process.env.FRONTEND_PORT || process.env.PORT
  if (envPort && /^\d+$/.test(envPort)) return Number(envPort)
  const configPort = getConfiguredPort(projectConfig.frontend_base_url)
  if (configPort) return configPort
  throw new Error('Frontend port is not configured. Set VITE_FRONTEND_PORT or dev_toolkit/config.local.json frontend_base_url.')
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
      '@products': path.resolve(__dirname, '../products'),
      'marked': path.resolve(__dirname, 'node_modules/marked'),
      'dompurify': path.resolve(__dirname, 'node_modules/dompurify'),
      'highlight.js': path.resolve(__dirname, 'node_modules/highlight.js'),
      'pdfjs-dist': path.resolve(__dirname, 'node_modules/pdfjs-dist'),
      'element-plus': path.resolve(__dirname, 'node_modules/element-plus'),
      'element-plus/es': path.resolve(__dirname, 'node_modules/element-plus/es'),
      'three/addons': path.resolve(__dirname, 'node_modules/three/examples/jsm'),
    },
    dedupe: ['three'],
  },
  server: {
    host: '0.0.0.0',
    port: getFrontendPort(),
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
