import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './app-entry/router'
import { vPermission } from './platform/directives/v-permission'
import { windowManager } from './desktop/window-manager/window-manager'
import { openAppById } from './desktop/app-registry/app-opener'
import api from './shared/api'
import type { PlatformCapability } from './types/global'
import './styles/theme.css'
import './styles/base.css'
import './styles/layout.css'
import './styles/common-components.css'
import './styles/notice-panel.css'
import './desktop/design-system/desktop-design-tokens.css'
import './styles/desktop-shell.css'
import './styles/login-page.css'

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)
app.use(router)
app.directive('permission', vPermission)

// Legacy fallback for older module runtimes. New code should use window.platform.
;(window as unknown as Record<string, unknown>).__HSWZ_WINDOW_MANAGER__ = windowManager

window.platform = {
  ...(window.platform ?? {}),
  api: {
    request: <T = unknown>(config: Record<string, unknown>) => api.request(config) as Promise<T>,
    get: <T = unknown>(url: string, config?: Record<string, unknown>) => api.get(url, config) as Promise<T>,
	    post: <T = unknown>(url: string, data?: unknown, config?: Record<string, unknown>) => (
	      api.post(url, data, config) as Promise<T>
	    ),
	    put: <T = unknown>(url: string, data?: unknown, config?: Record<string, unknown>) => (
	      api.put(url, data, config) as Promise<T>
	    ),
	    delete: <T = unknown>(url: string, config?: Record<string, unknown>) => (
	      api.delete(url, config) as Promise<T>
	    ),
	  },
  modules: {
    ...(window.platform?.modules ?? {}),
    call: <T = unknown>(
      targetModule: string,
      action: string,
      parameters: Record<string, unknown> = {},
    ) => api.post('/modules/call', { target_module: targetModule, action, parameters }) as Promise<T>,
    capabilities: () => api.get('/modules/capabilities') as Promise<PlatformCapability[]>,
    openApp: openAppById,
  },
}

router.isReady().then(() => {
  app.mount('#app')
})
