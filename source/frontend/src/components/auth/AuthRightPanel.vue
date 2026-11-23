<script setup>
/** 右侧表单容器：登录/注册 Tab 切换 + 忘记密码弹窗托管。 */
import { ref, watch } from 'vue'
import LoginForm from './LoginForm.vue'
import RegisterForm from './RegisterForm.vue'
import ForgetPasswordModal from './ForgetPasswordModal.vue'

const props = defineProps({ prefillUsername: { type: String, default: '' } })

const tab = ref('login')
const forgetVisible = ref(false)
const prefill = ref(props.prefillUsername)

watch(
  () => props.prefillUsername,
  (v) => {
    if (v) prefill.value = v
  }
)

function onRegistered(username) {
  prefill.value = username
  tab.value = 'login'
}

function onResetDone(username) {
  if (username) prefill.value = username
  tab.value = 'login'
}
</script>

<template>
  <section class="auth-right">
    <div class="right-top-line" aria-hidden="true"></div>
    <div class="auth-wrap">
      <div class="brand brand-mobile">
        <span class="logo" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3 8l4-4 5 5 4-4 5 5v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
          </svg>
        </span>
        <h1 class="name">AI 漫剧平台</h1>
        <p class="slogan">一句话灵感，AI 帮你拍成漫剧</p>
      </div>

      <div class="auth-card">
        <!-- 胶囊 Tab（设计规范 12.3：胶囊形 + 选中高亮） -->
        <div class="tabs" role="tablist" aria-label="登录或注册">
          <button
            type="button"
            role="tab"
            class="tab"
            :class="{ active: tab === 'login' }"
            :aria-selected="tab === 'login'"
            @click="tab = 'login'"
          >
            登录
          </button>
          <button
            type="button"
            role="tab"
            class="tab"
            :class="{ active: tab === 'register' }"
            :aria-selected="tab === 'register'"
            @click="tab = 'register'"
          >
            注册
          </button>
        </div>

        <Transition name="pane" mode="out-in">
          <LoginForm v-if="tab === 'login'" :key="'login'" :prefill="prefill" @switch="tab = $event" @forget="forgetVisible = true" />
          <RegisterForm v-else :key="'register'" @switch="tab = $event" @registered="onRegistered" />
        </Transition>
      </div>

      <p class="foot">登录即代表同意《AI 生成内容使用规范》</p>
    </div>

    <ForgetPasswordModal v-model="forgetVisible" @done="onResetDone" />
  </section>
</template>

<style scoped>
.auth-right {
  position: relative;
  flex: 1;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background: var(--bg);
}

.right-top-line {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: linear-gradient(
    90deg,
    transparent 15%,
    color-mix(in srgb, var(--primary) 60%, transparent) 50%,
    transparent 85%
  );
  pointer-events: none;
}

.auth-right::before {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    radial-gradient(640px 380px at 50% -8%, rgba(0, 113, 227, 0.08), transparent 70%),
    radial-gradient(520px 320px at 88% 108%, rgba(0, 113, 227, 0.06), transparent 65%);
}

.auth-wrap {
  position: relative;
  z-index: 1;
  width: 420px;
  max-width: calc(100vw - var(--space-7));
  padding: var(--space-7) 0;
}

/* 移动端品牌区（桌面端由左侧面板承担） */
.brand-mobile {
  text-align: center;
  margin-bottom: var(--space-6);
  animation: fadeUp 0.5s var(--ease-out) both;
}

@media (min-width: 1024px) {
  .brand-mobile {
    display: none;
  }
}

.logo {
  width: 44px;
  height: 44px;
  border-radius: var(--radius);
  background: var(--brand-grad);
  color: #fff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  box-shadow: var(--shadow);
}

.logo svg {
  width: 22px;
  height: 22px;
}

.name {
  margin: var(--space-3) 0 var(--space-1);
  font-size: var(--text-xl);
  font-weight: 800;
  letter-spacing: -1px;
  color: var(--text-primary);
}

.slogan {
  margin: 0;
  color: var(--text-secondary);
  font-size: 14px;
}

.auth-card {
  background: var(--surface);
  border-radius: var(--radius-xl);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-xl);
  padding: var(--space-6);
  animation: fadeUp 0.5s var(--ease-out) 0.1s both;
}

.tabs {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-1);
  padding: 4px;
  margin-bottom: var(--space-5);
  border-radius: var(--radius-pill);
  background: var(--surface-hover);
}

.tab {
  height: 36px;
  border: none;
  border-radius: var(--radius-pill);
  background: transparent;
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--dur-base) var(--ease-smooth);
}

.tab:hover {
  color: var(--text-primary);
}

.tab.active {
  background: var(--surface-raised);
  color: var(--text-primary);
  box-shadow: var(--shadow-sm);
}

.foot {
  text-align: center;
  margin-top: var(--space-4);
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  animation: fadeUp 0.5s var(--ease-out) 0.2s both;
}

/* Tab 切换微动效（弹窗/页面进入 200-250ms） */
.pane-enter-active,
.pane-leave-active {
  transition: opacity 0.2s var(--ease-smooth), transform 0.2s var(--ease-smooth);
}

.pane-enter-from {
  opacity: 0;
  transform: translateY(8px);
}

.pane-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

@media (max-width: 768px) {
  .auth-wrap {
    width: auto;
    max-width: none;
    margin: 0 var(--space-4);
    padding: var(--space-5) 0;
  }

  .auth-card {
    padding: var(--space-5);
  }
}

/* 无障碍：减少动效（设计规范 14.4） */
@media (prefers-reduced-motion: reduce) {
  .auth-wrap *,
  .pane-enter-active,
  .pane-leave-active {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
</style>
