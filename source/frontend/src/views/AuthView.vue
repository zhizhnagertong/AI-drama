<script setup>
/** 登录注册父页：左侧品牌面板 + 右侧表单容器（对齐前端组件结构图）。 */
import AuthLeftPanel from '../components/auth/AuthLeftPanel.vue'
import AuthRightPanel from '../components/auth/AuthRightPanel.vue'
</script>

<template>
  <div class="auth-screen">
    <AuthLeftPanel />
    <AuthRightPanel />
  </div>
</template>

<style scoped>
.auth-screen {
  display: flex;
  min-height: 100vh;
  background: var(--bg);
}
</style>
