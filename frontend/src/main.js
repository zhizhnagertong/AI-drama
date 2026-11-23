import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import App from './App.vue'
import router from './router'
import { reveal } from './utils/directives'
import { useAuthStore } from './stores/auth'
import './styles/tokens.css'
import './styles/main.css'

const app = createApp(App)

app.directive('reveal', reveal)

for (const [name, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(name, component)
}

const pinia = createPinia()
app.use(pinia)

// 启动即恢复会话（同步部分在首个 await 前完成，路由守卫可立即读到令牌）
useAuthStore(pinia).init()

app.use(router)
app.use(ElementPlus, { locale: zhCn })
app.mount('#app')
