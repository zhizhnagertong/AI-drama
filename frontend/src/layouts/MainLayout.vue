<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Moon, Sunny } from '@element-plus/icons-vue'
import { useAuthStore } from '../stores/auth'
import { useThemeStore } from '../stores/theme'
import { firstChar } from '../utils'

const router = useRouter()
const auth = useAuthStore()
const theme = useThemeStore()

const navs = [
  { label: '工作台', to: '/', icon: 'grid' },
  { label: '创作', to: '/create', icon: 'sparkle' },
  { label: '我的', to: '/mine', icon: 'user' }
]

const initial = computed(() => firstChar(auth.displayName))
const userMenu = ref(null)
const scrolled = ref(false)
const mobileOpen = ref(false)

function onScroll() {
  scrolled.value = window.scrollY > 10
}

onMounted(() => {
  window.addEventListener('scroll', onScroll, { passive: true })
  onScroll()
})

onBeforeUnmount(() => {
  window.removeEventListener('scroll', onScroll)
})

function toggleMobileMenu() {
  mobileOpen.value = !mobileOpen.value
}

function onThemeChange() {
  theme.toggle()
}

function onAvatarKeydown(e) {
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault()
    userMenu.value?.handleOpen()
  }
}

function onUserCommand(cmd) {
  if (cmd === 'logout') auth.logout()
  if (cmd === 'mine') router.push('/mine')
}
</script>

<template>
  <div class="layout">
    <header class="topbar glass-bar" :class="{ scrolled }">
      <div class="topbar-inner">
        <router-link to="/" class="brand">
          <span class="brand-logo" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M3 8l4-4 5 5 4-4 5 5v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
            </svg>
          </span>
          <span class="brand-name">AI 漫剧平台</span>
        </router-link>

        <nav class="nav">
          <router-link
            v-for="n in navs"
            :key="n.to"
            :to="n.to"
            class="nav-link"
            :class="{ active: $route.path === n.to }"
          >
            <svg v-if="n.icon === 'grid'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <rect x="3" y="3" width="7" height="7" rx="1.5" />
              <rect x="14" y="3" width="7" height="7" rx="1.5" />
              <rect x="3" y="14" width="7" height="7" rx="1.5" />
              <rect x="14" y="14" width="7" height="7" rx="1.5" />
            </svg>
            <svg v-else-if="n.icon === 'sparkle'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <path d="M12 2l2.4 7.2L22 11l-7.6 2.8L12 22l-2.4-8.2L2 11l7.6-1.8z" />
            </svg>
            <svg v-else-if="n.icon === 'plus'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <path d="M12 5v14M5 12h14" />
            </svg>
            <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <circle cx="12" cy="8" r="4" />
              <path d="M4 21v-1a6 6 0 0 1 6-6h4a6 6 0 0 1 6 6v1" />
            </svg>
            {{ n.label }}
          </router-link>
        </nav>

        <div class="right">
          <el-switch
            class="theme-switch theme-switch--text"
            :model-value="theme.isDark"
            inline-prompt
            active-text="深色"
            inactive-text="浅色"
            aria-label="切换深色/浅色主题"
            @change="onThemeChange"
          />
          <el-button
            class="new-project-btn"
            type="primary"
            round
            aria-label="新建项目"
            @click="router.push('/create')"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" aria-hidden="true">
              <path d="M12 5v14M5 12h14" />
            </svg>
            <span class="new-project-label">新建</span>
          </el-button>
          <el-dropdown ref="userMenu" trigger="click" @command="onUserCommand">
            <span
              class="avatar"
              role="button"
              tabindex="0"
              aria-label="用户菜单"
              aria-haspopup="menu"
              @keydown="onAvatarKeydown"
            >
              {{ initial }}
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item disabled>
                  {{ auth.displayName }}
                </el-dropdown-item>
                <el-dropdown-item divided command="mine">我的主页</el-dropdown-item>
                <el-dropdown-item command="logout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <button
            class="mobile-toggle"
            type="button"
            aria-label="打开导航菜单"
            :aria-expanded="mobileOpen"
            @click="toggleMobileMenu"
          >
            <span></span>
            <span></span>
            <span></span>
          </button>
        </div>
      </div>
    </header>

    <div class="mobile-menu" :class="{ open: mobileOpen }">
      <router-link
        v-for="n in navs"
        :key="n.to"
        :to="n.to"
        :class="{ active: $route.path === n.to }"
        @click="mobileOpen = false"
      >
        <svg v-if="n.icon === 'grid'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
          <rect x="3" y="3" width="7" height="7" rx="1.5" />
          <rect x="14" y="3" width="7" height="7" rx="1.5" />
          <rect x="3" y="14" width="7" height="7" rx="1.5" />
          <rect x="14" y="14" width="7" height="7" rx="1.5" />
        </svg>
        <svg v-else-if="n.icon === 'sparkle'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
          <path d="M12 2l2.4 7.2L22 11l-7.6 2.8L12 22l-2.4-8.2L2 11l7.6-1.8z" />
        </svg>
        <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
          <circle cx="12" cy="8" r="4" />
          <path d="M4 21v-1a6 6 0 0 1 6-6h4a6 6 0 0 1 6 6v1" />
        </svg>
        {{ n.label }}
      </router-link>
      <div class="mobile-theme">
        <span>深色模式</span>
        <el-switch
          class="theme-switch theme-switch--icon"
          :model-value="theme.isDark"
          inline-prompt
          :active-icon="Moon"
          :inactive-icon="Sunny"
          aria-label="切换深色/浅色主题"
          @change="onThemeChange"
        />
      </div>
    </div>

    <main class="layout-main">
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.layout {
  min-height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--bg);
}

/* ---------- 顶栏（参考稿 .navbar：60px 磨砂玻璃 + scrolled 阴影） ---------- */
.topbar {
  position: sticky;
  top: 0;
  z-index: var(--z-bar);
}

.topbar-inner {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 var(--space-5);
  height: 60px;
  display: flex;
  align-items: center;
  gap: var(--space-5);
}

/* ---------- 品牌（参考稿 .navbar-brand / .brand-icon） ---------- */
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  user-select: none;
  color: var(--text-primary);
  font-weight: 700;
  font-size: 16px;
  letter-spacing: -0.3px;
  text-decoration: none;
  transition: opacity var(--dur-fast) var(--ease-out);
}

.brand:hover {
  color: var(--text-primary);
  opacity: 0.8;
}

.brand-logo {
  width: 30px;
  height: 30px;
  border-radius: 9px;
  background: var(--brand-grad);
  color: #fff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  box-shadow: var(--shadow-sm);
}

.brand-logo svg {
  width: 16px;
  height: 16px;
}

.brand-name {
  white-space: nowrap;
}

/* ---------- 导航（参考稿 .nav-link：36px pill + 15px 线性图标） ---------- */
.nav {
  display: flex;
  gap: var(--space-1);
  flex: 1;
}

.nav-link {
  display: flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  padding: 0 var(--space-4);
  border-radius: var(--radius-pill);
  font-size: 14px;
  font-weight: 500;
  color: var(--text-secondary);
  text-decoration: none;
  transition: color 0.18s var(--ease-out),
    background-color 0.18s var(--ease-out), box-shadow 0.18s var(--ease-out);
}

.nav-link svg {
  width: 15px;
  height: 15px;
  flex-shrink: 0;
}

.nav-link:hover {
  color: var(--text-primary);
  background-color: var(--surface-hover);
}

.nav-link.active {
  background-color: rgba(255, 255, 255, 0.1);
  color: #fff;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.3);
}

[data-theme='light'] .nav-link.active {
  background-color: rgba(29, 29, 31, 0.08);
  color: var(--text-primary);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
}

/* ---------- 右侧操作区（参考稿 .navbar-actions） ---------- */
.right {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.new-project-btn {
  height: 36px;
  padding: 0 var(--space-4);
  font-size: 14px;
  gap: var(--space-1);
}

.new-project-btn svg {
  flex-shrink: 0;
}

/* ---------- 头像（参考稿 .avatar-btn：34px 圆 + brand 渐变） ---------- */
.avatar {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: var(--brand-grad);
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: transform 0.2s var(--ease-out),
    box-shadow var(--dur-fast) var(--ease-out);
}

.avatar:hover {
  transform: scale(1.05);
}

.avatar:focus-visible {
  box-shadow: 0 0 0 3px var(--primary-soft);
}

/* ---------- 移动端汉堡（参考稿 .mobile-toggle：三条线 20x2） ---------- */
.mobile-toggle {
  display: none;
  flex-direction: column;
  gap: 4px;
  background: none;
  border: none;
  cursor: pointer;
  padding: 4px;
}

.mobile-toggle span {
  display: block;
  width: 20px;
  height: 2px;
  background: var(--text-primary);
  border-radius: 2px;
  transition: transform 0.3s var(--ease-out), opacity 0.3s var(--ease-out);
}

/* ---------- 移动端全屏菜单（参考稿 .mobile-menu） ---------- */
.mobile-menu {
  position: fixed;
  inset: 60px 0 0;
  background: rgba(0, 0, 0, 0.96);
  -webkit-backdrop-filter: blur(20px);
  backdrop-filter: blur(20px);
  padding: var(--space-5);
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  transform: translateY(-100%);
  opacity: 0;
  pointer-events: none;
  transition: transform 0.4s var(--ease-out), opacity 0.4s var(--ease-out);
  z-index: calc(var(--z-bar) - 1);
}

.mobile-menu.open {
  transform: translateY(0);
  opacity: 1;
  pointer-events: auto;
}

.mobile-menu a {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px var(--space-4);
  border-radius: var(--radius);
  font-size: 16px;
  font-weight: 500;
  color: var(--text-secondary);
  transition: background-color 0.2s var(--ease-out),
    color 0.2s var(--ease-out);
}

.mobile-menu a svg {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
}

.mobile-menu a:hover {
  background: var(--surface-hover);
  color: var(--text-primary);
}

.mobile-menu a.active {
  background: var(--surface-hover);
  color: var(--text-primary);
}

.mobile-theme {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 14px var(--space-4);
  border-radius: var(--radius);
  font-size: 16px;
  font-weight: 500;
  color: var(--text-secondary);
}

/* ---------- 响应式：<768px 隐藏 nav，显示汉堡 ---------- */
@media (min-width: 768px) {
  .mobile-menu {
    display: none;
  }
}

@media (max-width: 767px) {
  .topbar-inner {
    gap: var(--space-3);
    padding: 0 var(--space-4);
  }
  .brand-name {
    display: none;
  }
  .nav {
    display: none;
  }
  .theme-switch--text {
    display: none;
  }
  .new-project-label {
    display: none;
  }
  .new-project-btn {
    padding-left: var(--space-3);
    padding-right: var(--space-3);
  }
  .mobile-toggle {
    display: flex;
  }
}
</style>
