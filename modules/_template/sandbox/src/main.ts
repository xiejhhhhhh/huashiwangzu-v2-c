import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import App from './App.vue'

const app = createApp(App)
// Sandbox keeps full Element Plus registration on purpose: the isolated module shell favors
// simple local preview setup, while the main framework continues to optimize its own bundle.
app.use(ElementPlus)
app.mount('#app')
