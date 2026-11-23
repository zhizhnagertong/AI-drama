<script setup>
import { onMounted, onBeforeUnmount, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useThemeStore } from './stores/theme'
import { onSessionExpired } from './api/session'

const theme = useThemeStore()
const router = useRouter()

function sync() {
  theme.apply()
}

let unsubscribe = null

onMounted(() => {
  sync()
  // 任意页面令牌彻底失效时，全局清理并跳登录页
  unsubscribe = onSessionExpired((reason) => {
    if (reason) ElMessage.warning(reason)
    if (router.currentRoute.value.path !== '/login') {
      router.push({
        path: '/login',
        query: router.currentRoute.value.fullPath === '/' ? {} : { redirect: router.currentRoute.value.fullPath }
      })
    }
  })
})

onBeforeUnmount(() => unsubscribe?.())
watch(() => theme.theme, sync)
</script>

<template>
  <div class="app-root" :data-theme="theme.theme">
    <router-view />
  </div>
</template>

<style scoped>
.app-root {
  min-height: 100%;
  background: var(--bg);
  color: var(--text);
}
</style>
