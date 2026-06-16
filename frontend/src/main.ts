import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
import App from './App.vue'
import router from './app-entry/router'
import { vPermission } from './platform/directives/v-permission'
import './styles/theme.css'
import './styles/base.css'
import './styles/layout.css'
import './styles/common-components.css'
import './styles/notice-panel.css'
import './styles/desktop-shell.css'
import './styles/login-page.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(ElementPlus, { locale: zhCn })
app.directive('permission', vPermission)

router.isReady().then(() => {
  app.mount('#app')
})
