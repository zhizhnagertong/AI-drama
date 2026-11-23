<script setup>
import { nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import api, { unwrap } from '../api'
import { asList } from '../utils'
import { useStyleStore } from '../stores/styles'

const router = useRouter()
const styleStore = useStyleStore()

/* ---------------- 列表加载 ---------------- */
const list = ref([])
const loading = ref(false)
const error = ref(false)
const includeInactive = ref(false)

async function load() {
  loading.value = true
  error.value = false
  try {
    const data = unwrap(
      await api.get('/styles', {
        params: { page: 1, page_size: 100, include_inactive: includeInactive.value }
      })
    )
    list.value = asList(data, 'items', 'styles', 'list')
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
}

watch(includeInactive, load)
onMounted(load)

/* ---------------- 启停（乐观更新） ---------------- */
const togglingId = ref(null)

async function toggleActive(s) {
  const prev = s.is_active
  s.is_active = !prev
  togglingId.value = s.id
  try {
    const updated = unwrap(await api.patch(`/styles/${s.id}/toggle`))
    if (updated && updated.id != null) {
      const idx = list.value.findIndex((x) => x.id === updated.id)
      if (idx > -1) list.value.splice(idx, 1, { ...list.value[idx], ...updated })
    }
    styleStore.fetch(true)
  } catch {
    s.is_active = prev /* 回滚（错误提示由拦截器统一弹出） */
  } finally {
    togglingId.value = null
  }
}

/* ---------------- 新建 / 编辑 ---------------- */
const dialogVisible = ref(false)
const editingId = ref(null)
const saving = ref(false)
const nameError = ref('')
const formRef = ref(null)

const form = reactive({
  name: '',
  prompt: '',
  description: '',
  negative_prompt: '',
  sort_order: 0
})

const rules = {
  name: [
    {
      required: true,
      validator: (rule, value, callback) => {
        if (!value || !String(value).trim()) return callback(new Error('请输入风格名称'))
        if (value !== String(value).trim()) return callback(new Error('名称首尾不能包含空格'))
        const len = String(value).trim().length
        if (len < 1 || len > 64) return callback(new Error('名称长度为 1-64 个字符'))
        callback()
      },
      trigger: 'blur'
    }
  ],
  prompt: [
    { required: true, message: '请输入提示词', trigger: 'blur' },
    { max: 2000, message: '提示词不能超过 2000 个字符', trigger: 'blur' }
  ]
}

function resetForm() {
  Object.assign(form, { name: '', prompt: '', description: '', negative_prompt: '', sort_order: 0 })
  nameError.value = ''
  nextTick(() => formRef.value?.clearValidate())
}

function openCreate() {
  editingId.value = null
  resetForm()
  dialogVisible.value = true
}

function openEdit(s) {
  editingId.value = s.id
  Object.assign(form, {
    name: s.name || '',
    prompt: s.prompt || '',
    description: s.description || '',
    negative_prompt: s.negative_prompt || '',
    sort_order: Number(s.sort_order) || 0
  })
  nameError.value = ''
  dialogVisible.value = true
  nextTick(() => formRef.value?.clearValidate())
}

async function save() {
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  nameError.value = ''
  saving.value = true
  const payload = {
    name: form.name.trim(),
    prompt: form.prompt.trim(),
    description: form.description.trim(),
    negative_prompt: form.negative_prompt.trim(),
    sort_order: form.sort_order
  }
  try {
    if (editingId.value == null) {
      const created = unwrap(await api.post('/styles', { ...payload, is_active: true }))
      if (created && created.id != null) list.value.push(created)
      else load()
      ElMessage.success('风格已创建')
    } else {
      const updated = unwrap(await api.put(`/styles/${editingId.value}`, payload))
      const idx = list.value.findIndex((x) => x.id === editingId.value)
      if (idx > -1 && updated && updated.id != null) {
        list.value.splice(idx, 1, { ...list.value[idx], ...updated })
      } else {
        load()
      }
      ElMessage.success('风格已更新')
    }
    dialogVisible.value = false
    styleStore.fetch(true)
  } catch (err) {
    /* 重名 400：拦截器已弹后端消息，这里额外把名称字段标红 */
    if (err?.response?.status === 400) {
      nameError.value = err.response?.data?.message || err.response?.data?.detail || '风格名称已存在'
    }
  } finally {
    saving.value = false
  }
}

/* ---------------- 删除 ---------------- */
async function removeStyle(s) {
  try {
    await ElMessageBox.confirm(
      `确定删除风格「${s.name}」吗？删除后不可恢复。`,
      '删除风格',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  await api.delete(`/styles/${s.id}`)
  list.value = list.value.filter((x) => x.id !== s.id)
  ElMessage.success('风格已删除')
  styleStore.fetch(true)
}
</script>

<template>
  <div class="g-page">
    <!-- 页头 -->
    <div v-reveal class="styles-header">
      <button type="button" class="back-btn" aria-label="返回我的主页" @click="router.push('/mine')">
        <svg
          aria-hidden="true"
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2.5"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <polyline points="15 18 9 12 15 6" />
        </svg>
      </button>
      <div class="styles-header-text">
        <h1 class="g-page-title">风格预设</h1>
        <p class="g-page-sub">管理 AI 出图的视觉风格，创作时可直接选用启用中的风格</p>
      </div>
      <el-button type="primary" round @click="openCreate">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" aria-hidden="true">
          <path d="M12 5v14M5 12h14" />
        </svg>
        <span class="new-label">新建风格</span>
      </el-button>
    </div>

    <!-- 工具栏 -->
    <div v-reveal="1" class="styles-toolbar">
      <el-switch v-model="includeInactive" aria-label="显示已停用的风格" />
      <span class="toolbar-label">显示已停用</span>
      <span v-if="!loading && !error" class="toolbar-count num">{{ list.length }} 个风格</span>
    </div>

    <!-- 卡片网格 -->
    <div v-loading="loading" class="grid-wrap">
      <template v-if="!error">
        <div v-if="list.length" class="grid">
          <article
            v-for="(s, i) in list"
            :key="s.id"
            v-reveal="Math.min(i + 1, 6)"
            class="style-card g-card"
            :class="{ 'style-card--off': !s.is_active }"
          >
            <div class="card-head">
              <h3 class="style-name" :title="s.name">{{ s.name }}</h3>
              <el-tag :type="s.is_active ? 'success' : 'info'" effect="light" size="small" round>
                {{ s.is_active ? '启用' : '停用' }}
              </el-tag>
            </div>
            <p v-if="s.description" class="style-desc">{{ s.description }}</p>
            <p class="style-prompt mono" :title="s.prompt">{{ s.prompt || '（未填写提示词）' }}</p>
            <div class="card-foot">
              <el-switch
                :model-value="s.is_active"
                :loading="togglingId === s.id"
                aria-label="启用/停用该风格"
                @change="toggleActive(s)"
              />
              <div class="card-ops">
                <el-button text size="small" @click="openEdit(s)">编辑</el-button>
                <el-button text size="small" class="op-danger" @click="removeStyle(s)">删除</el-button>
              </div>
            </div>
          </article>
        </div>
        <div v-else-if="!loading" class="g-empty">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
            <circle cx="13.5" cy="6.5" r="2.5" />
            <circle cx="17.5" cy="10.5" r="2.5" />
            <circle cx="8.5" cy="7.5" r="2.5" />
            <circle cx="6.5" cy="12.5" r="2.5" />
            <path d="M12 22a10 10 0 1 1 10-10c0 1.5-1 2-2 2h-2a2 2 0 0 0-2 2c0 .5.2 1 .5 1.5.3.5.5 1 .5 1.5a3 3 0 0 1-3 3z" />
          </svg>
          <h3>还没有风格预设</h3>
          <p>创建你的第一个视觉风格，让 AI 出图更有辨识度</p>
          <el-button type="primary" round @click="openCreate">新建风格</el-button>
        </div>
      </template>
      <div v-else class="g-empty">
        <h3>风格列表加载失败</h3>
        <p>网络异常或服务暂不可用，请稍后重试</p>
        <el-button round @click="load">重试</el-button>
      </div>
    </div>

    <!-- 新建 / 编辑弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="editingId == null ? '新建风格' : '编辑风格'"
      width="520px"
      :close-on-click-modal="false"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <el-form-item label="名称" prop="name" :error="nameError">
          <el-input
            v-model="form.name"
            placeholder="如：赛博朋克"
            maxlength="64"
            show-word-limit
            @input="nameError = ''"
          />
        </el-form-item>
        <el-form-item label="提示词" prop="prompt">
          <el-input
            v-model="form.prompt"
            type="textarea"
            :rows="4"
            maxlength="2000"
            show-word-limit
            placeholder="cyberpunk, neon lights, futuristic city, high contrast, cinematic lighting…"
          />
        </el-form-item>
        <el-form-item label="简介（可选）">
          <el-input v-model="form.description" maxlength="256" placeholder="一句话描述这个风格的视觉效果" />
        </el-form-item>
        <el-form-item label="负向提示词（可选）">
          <el-input
            v-model="form.negative_prompt"
            type="textarea"
            :rows="2"
            maxlength="2000"
            show-word-limit
            placeholder="blurry, low quality, watermark…"
          />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="form.sort_order" :min="0" :max="999" />
          <span class="sort-hint">数值越小越靠前</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button round :disabled="saving" @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" round :loading="saving" :disabled="saving" @click="save">
          保存
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
/* ---------- 页头 ---------- */
.styles-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 28px;
}

.back-btn {
  width: 40px;
  height: 40px;
  border-radius: var(--radius);
  background: var(--surface);
  border: 1px solid var(--border);
  display: grid;
  place-items: center;
  color: var(--text-secondary);
  cursor: pointer;
  flex-shrink: 0;
  font-family: inherit;
  transition: background-color 0.2s var(--ease-out),
    color 0.2s var(--ease-out), border-color 0.2s var(--ease-out);
}

.back-btn:hover {
  background: var(--surface-raised);
  color: var(--text-primary);
  border-color: var(--border-strong);
}

.styles-header-text {
  flex: 1;
  min-width: 0;
}

.new-label {
  margin-left: 6px;
}

/* ---------- 工具栏 ---------- */
.styles-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 24px;
}

.toolbar-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
}

.toolbar-count {
  margin-left: auto;
  font-size: 12.5px;
  color: var(--text-tertiary);
}

/* ---------- 卡片网格（对齐工作台 project-grid） ---------- */
.grid-wrap {
  min-height: 240px;
}

.grid {
  display: grid;
  grid-template-columns: repeat(1, 1fr);
  gap: 20px;
}

@media (min-width: 640px) {
  .grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (min-width: 1024px) {
  .grid {
    grid-template-columns: repeat(3, 1fr);
  }
}

/* ---------- 风格卡 ---------- */
.style-card {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  transition: transform 0.4s var(--ease-out), box-shadow 0.4s var(--ease-out),
    border-color 0.4s var(--ease-out);
}

.style-card:hover {
  transform: translateY(-3px);
  box-shadow: var(--shadow);
  border-color: var(--border-strong);
}

.style-card--off {
  opacity: 0.66;
}

.card-head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.style-name {
  flex: 1;
  min-width: 0;
  font-size: 16px;
  font-weight: 700;
  letter-spacing: -0.3px;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.style-desc {
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-secondary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 0;
}

.style-prompt {
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-tertiary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-all;
}

.card-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: auto;
  padding-top: 12px;
  border-top: 1px solid var(--divider);
}

.card-ops {
  display: flex;
  align-items: center;
  gap: 4px;
}

.op-danger {
  color: var(--error);
}

/* ---------- 弹窗 ---------- */
.sort-hint {
  margin-left: 10px;
  font-size: 12px;
  color: var(--text-tertiary);
}

/* ---------- 窄屏 ---------- */
@media (max-width: 768px) {
  .styles-header {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
