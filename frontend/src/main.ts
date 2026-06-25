import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './app-entry/router'
import { vPermission } from './platform/directives/v-permission'
import { windowManager } from './desktop/window-manager/window-manager'
import './styles/theme.css'
import './styles/base.css'
import './styles/layout.css'
import './styles/common-components.css'
import './styles/notice-panel.css'
import './styles/desktop-shell.css'
import './desktop/design-system/desktop-design-tokens.css'
import './styles/login-page.css'
import 'element-plus/dist/index.css'

// 暴露 windowManager 到全局，供模块通过 runtime.openApp() 打开其他应用
;(window as unknown as Record<string, unknown>).__HSWZ_WINDOW_MANAGER__ = windowManager

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.directive('permission', vPermission)

router.isReady().then(() => {
  app.mount('#app')
})
