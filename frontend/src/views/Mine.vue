<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import api, { unwrap } from '../api'
import { useAuthStore } from '../stores/auth'
import { useThemeStore } from '../stores/theme'
import { asList, firstChar } from '../utils'
import ProjectCard from '../components/ProjectCard.vue'

const router = useRouter()
const auth = useAuthStore()
const theme = useThemeStore()

const works = ref([])
const loading = ref(false)

/* ---------------- 编辑资料 ---------------- */
const profileVisible = ref(false)
const profileForm = reactive({ nickname: '' })
const profileSaving = ref(false)

function openProfile() {
  profileForm.nickname = auth.user?.nickname || auth.user?.username || ''
  profileVisible.value = true
}

async function saveProfile() {
  if (!profileForm.nickname.trim()) {
    ElMessage.warning('昵称不能为空')
    return
  }
  profileSaving.value = true
  try {
    const data = unwrap(await api.put('/auth/me', { nickname: profileForm.nickname.trim() }))
    auth.setUser(data)
    profileVisible.value = false
    ElMessage.success('资料已更新')
  } finally {
    profileSaving.value = false
  }
}

/* ---------------- 修改密码 ---------------- */
const pwdVisible = ref(false)
const pwdForm = reactive({ old_password: '', new_password: '', confirm: '' })
const pwdSaving = ref(false)

function openPassword() {
  Object.assign(pwdForm, { old_password: '', new_password: '', confirm: '' })
  pwdVisible.value = true
}

async function savePassword() {
  if (!/^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)\S{8,20}$/.test(pwdForm.new_password)) {
    ElMessage.warning('新密码须为 8-20 位，包含大写、小写字母和数字，不含空格')
    return
  }
  if (pwdForm.new_password !== pwdForm.confirm) {
    ElMessage.warning('两次输入的新密码不一致')
    return
  }
  pwdSaving.value = true
  try {
    await api.put('/auth/me/password', {
      old_password: pwdForm.old_password,
      new_password: pwdForm.new_password
    })
    pwdVisible.value = false
    ElMessage.success('密码已更新')
  } finally {
    pwdSaving.value = false
  }
}

const MODELS = [
  { name: 'agnes-2.5-flash', usage: '剧本 / 分镜脚本等文本创作' },
  { name: 'agnes-image-2.1-flash', usage: '分镜与角色参考图生成' },
  { name: 'agnes-video-2.5-flash', usage: '图生视频动效' }
]

async function load() {
  loading.value = true
  try {
    const data = unwrap(await api.get('/projects', { params: { page: 1, page_size: 100 } }))
    works.value = asList(data, 'projects', 'list')
  } finally {
    loading.value = false
  }
}

function onThemeChange() {
  theme.toggle()
}

async function clearCache() {
  await ElMessageBox.confirm('将清除本地缓存的主题等偏好数据（不影响登录状态与云端作品），是否继续？', '清除本地缓存', {
    confirmButtonText: '清除',
    cancelButtonText: '取消',
    type: 'warning'
  })
  // 保留会话键（auth.* 前缀），其余本地缓存清除
  for (const store of [localStorage, sessionStorage]) {
    const keep = {}
    for (let i = 0; i < store.length; i++) {
      const k = store.key(i)
      if (k && (k.startsWith('auth.') || k === 'theme')) keep[k] = store.getItem(k)
    }
    store.clear()
    for (const [k, v] of Object.entries(keep)) store.setItem(k, v)
  }
  ElMessage.success('本地缓存已清除')
}

onMounted(load)

function onDeleted(id) {
  works.value = works.value.filter((p) => p.id !== id)
}
</script>

<template>
  <div v-reveal class="g-page">
    <!-- 头部（参考稿 .mine-header） -->
    <div class="mine-header">
      <div class="mine-avatar">{{ firstChar(auth.displayName) }}</div>
      <div class="mine-info">
        <h1>{{ auth.displayName }}</h1>
        <p>@{{ auth.user?.username || '-' }}</p>
        <div class="mine-stats">
          <div class="mine-stat">
            <b class="num">{{ works.length }}</b>
            <span>作品</span>
          </div>
          <div class="mine-stat">
            <b class="num">{{ works.filter((w) => w.status === 'producing').length }}</b>
            <span>进行中</span>
          </div>
          <div class="mine-stat">
            <b class="num">{{ works.filter((w) => w.status === 'completed').length }}</b>
            <span>已完成</span>
          </div>
        </div>
      </div>
      <el-button class="edit-profile" round @click="openProfile">编辑资料</el-button>
    </div>

    <!-- 我的作品 -->
    <h2 class="g-section-title">我的作品</h2>
    <div v-loading="loading">
      <div v-if="works.length" class="mine-grid">
        <ProjectCard
          v-for="(p, i) in works"
          :key="p.id"
          v-reveal="Math.min(i + 1, 6)"
          :project="p"
          @deleted="onDeleted"
        />
      </div>
      <div v-else-if="!loading" class="g-empty">
        <el-empty description="还没有作品，去「创作」页开启第一部漫剧吧" :image-size="80" />
      </div>
    </div>

    <!-- 账号设置（参考稿 .setting-card 列表） -->
    <h2 class="g-section-title settings-title">账号设置</h2>

    <div v-reveal="1" class="setting-card">
      <span class="setting-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
        </svg>
      </span>
      <div class="setting-text">
        <b>深色模式</b>
      </div>
      <el-switch
        :model-value="theme.isDark"
        inline-prompt
        active-text="深色"
        inactive-text="浅色"
        aria-label="切换深色/浅色主题"
        @change="onThemeChange"
      />
    </div>

    <div v-reveal="2" class="setting-card setting-card--models">
      <span class="setting-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="4" y="4" width="16" height="16" rx="2" />
          <rect x="9" y="9" width="6" height="6" />
          <line x1="9" y1="1" x2="9" y2="4" />
          <line x1="15" y1="1" x2="15" y2="4" />
          <line x1="9" y1="20" x2="9" y2="23" />
          <line x1="15" y1="20" x2="15" y2="23" />
          <line x1="20" y1="9" x2="23" y2="9" />
          <line x1="20" y1="14" x2="23" y2="14" />
          <line x1="1" y1="9" x2="4" y2="9" />
          <line x1="1" y1="14" x2="4" y2="14" />
        </svg>
      </span>
      <div class="setting-text">
        <b>AI 模型信息（只读）</b>
        <span>当前平台使用的生成模型</span>
      </div>
      <div class="model-list">
        <div v-for="m in MODELS" :key="m.name" class="model">
          <span class="mname mono">{{ m.name }}</span>
          <span class="musage">{{ m.usage }}</span>
        </div>
      </div>
    </div>

    <div v-reveal="3" class="setting-card">
      <span class="setting-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="3" y="11" width="18" height="11" rx="2" />
          <path d="M7 11V7a5 5 0 0 1 10 0v4" />
        </svg>
      </span>
      <div class="setting-text">
        <b>修改密码</b>
        <span>定期更新密码更安全</span>
      </div>
      <el-button plain round size="small" @click="openPassword">修改密码</el-button>
    </div>

    <div v-reveal="4" class="setting-card setting-card--link" @click="router.push('/styles')">
      <span class="setting-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M12 22a10 10 0 1 1 10-10c0 1.5-1 2-2 2h-2a2 2 0 0 0-2 2c0 .5.2 1 .5 1.5.3.5.5 1 .5 1.5a3 3 0 0 1-3 3z" />
          <circle cx="13.5" cy="6.5" r="1.5" />
          <circle cx="17.5" cy="10.5" r="1.5" />
          <circle cx="8.5" cy="7.5" r="1.5" />
          <circle cx="6.5" cy="12.5" r="1.5" />
        </svg>
      </span>
      <div class="setting-text">
        <b>风格预设</b>
        <span>管理 AI 出图的视觉风格</span>
      </div>
      <span class="setting-arrow" aria-hidden="true">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="9 18 15 12 9 6" />
        </svg>
      </span>
    </div>

    <div v-reveal="5" class="setting-card">
      <span class="setting-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="3 6 5 6 21 6" />
          <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
        </svg>
      </span>
      <div class="setting-text">
        <b>清除本地缓存</b>
        <span>清理本地偏好数据，不影响云端作品</span>
      </div>
      <el-button plain round size="small" @click="clearCache">清除缓存</el-button>
    </div>

    <!-- 编辑资料弹窗 -->
    <el-dialog v-model="profileVisible" title="编辑资料" width="380px">
      <el-form label-position="top">
        <el-form-item label="昵称">
          <el-input v-model="profileForm.nickname" maxlength="64" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button round @click="profileVisible = false">取消</el-button>
        <el-button type="primary" round :loading="profileSaving" @click="saveProfile">
          保存
        </el-button>
      </template>
    </el-dialog>

    <!-- 修改密码弹窗 -->
    <el-dialog v-model="pwdVisible" title="修改密码" width="380px">
      <el-form label-position="top">
        <el-form-item label="原密码">
          <el-input v-model="pwdForm.old_password" type="password" show-password />
        </el-form-item>
        <el-form-item label="新密码（至少 6 位）">
          <el-input v-model="pwdForm.new_password" type="password" show-password />
        </el-form-item>
        <el-form-item label="确认新密码">
          <el-input v-model="pwdForm.confirm" type="password" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button round @click="pwdVisible = false">取消</el-button>
        <el-button type="primary" round :loading="pwdSaving" @click="savePassword">
          保存
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
/* ---------- 头部（参考稿 .mine-header） ---------- */
.mine-header {
  display: flex;
  align-items: center;
  gap: 20px;
  margin-bottom: 40px;
  padding: 32px;
  background: linear-gradient(135deg, rgba(0, 113, 227, 0.06), transparent);
  border-radius: var(--radius-xl);
  border: 1px solid var(--border);
}

.mine-avatar {
  width: 80px;
  height: 80px;
  border-radius: 50%;
  background: var(--brand-grad);
  display: grid;
  place-items: center;
  font-size: 32px;
  font-weight: 800;
  color: #fff;
  flex-shrink: 0;
  box-shadow: var(--shadow-sm);
}

.mine-info {
  flex: 1;
  min-width: 0;
}

.mine-info h1 {
  font-size: 28px;
  font-weight: 800;
  letter-spacing: -1px;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mine-info p {
  color: var(--text-secondary);
  font-size: 14px;
  margin-top: 4px;
}

.mine-stats {
  display: flex;
  gap: 32px;
  margin-top: 16px;
}

.mine-stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.mine-stat b {
  font-size: 22px;
  font-weight: 800;
  font-family: var(--font-mono);
  color: var(--text-primary);
}

.mine-stat span {
  font-size: 12px;
  color: var(--text-secondary);
}

.edit-profile {
  flex-shrink: 0;
}

/* ---------- 作品网格（参考稿 .mine-grid） ---------- */
.mine-grid {
  display: grid;
  grid-template-columns: repeat(1, 1fr);
  gap: 20px;
  margin-bottom: var(--space-8);
}

@media (min-width: 640px) {
  .mine-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (min-width: 1024px) {
  .mine-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}

.settings-title {
  margin-top: 48px;
}

/* ---------- 设置卡片（参考稿 .setting-card） ---------- */
.setting-card {
  background: var(--surface);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border);
  padding: 20px;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 14px;
  cursor: default;
  transition: box-shadow 0.3s var(--ease-out),
    border-color 0.3s var(--ease-out);
}

.setting-card:hover {
  box-shadow: var(--shadow);
  border-color: var(--border-strong);
}

.setting-card--link {
  cursor: pointer;
}

.setting-arrow {
  color: var(--text-tertiary);
  display: inline-flex;
  flex-shrink: 0;
  transition: transform 0.2s var(--ease-out);
}

.setting-card--link:hover .setting-arrow {
  transform: translateX(2px);
}

.setting-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.06);
  display: grid;
  place-items: center;
  color: var(--text-secondary);
  flex-shrink: 0;
}

[data-theme='light'] .setting-icon {
  background: rgba(29, 29, 31, 0.05);
}

.setting-icon svg {
  width: 18px;
  height: 18px;
}

.setting-text {
  flex: 1;
  min-width: 0;
}

.setting-text b {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
}

.setting-text span {
  display: block;
  font-size: 12.5px;
  color: var(--text-secondary);
  margin-top: 2px;
}

/* ---------- 模型列表（只读信息） ---------- */
.setting-card--models {
  align-items: flex-start;
  flex-wrap: wrap;
}

.model-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  width: 100%;
  padding-left: 54px;
}

.model {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: 10px 14px;
  border-radius: var(--radius);
  background: var(--surface-hover);
  min-width: 0;
}

.mname {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
}

.musage {
  margin-left: auto;
  font-size: var(--text-xs);
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ---------- 窄屏 ---------- */
@media (max-width: 768px) {
  .mine-header {
    flex-direction: column;
    align-items: flex-start;
    padding: 24px;
    gap: var(--space-4);
  }
  .edit-profile {
    align-self: stretch;
  }
  .model-list {
    padding-left: 0;
  }
  .musage {
    margin-left: 0;
  }
  .model {
    flex-direction: column;
    align-items: flex-start;
    gap: 2px;
  }
}
</style>
