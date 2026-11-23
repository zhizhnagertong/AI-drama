<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import api, { unwrap } from '../api'
import {
  asList,
  statusText,
  statusTagType,
  gradVar,
  firstChar,
  imgUrlOf,
  assetUrlOf,
  assetTypeOf,
  assetNameOf,
  normStoryboard,
  versionsOf,
  GENRES,
  STYLES,
  RATIOS
} from '../utils'
import { useStyleStore } from '../stores/styles'

const route = useRoute()
const router = useRouter()
const projectId = route.params.id
const styleStore = useStyleStore()

/* 风格下拉选项：后端可达时严格使用启用预设，仅请求失败回退内置 STYLES */
const styleNames = computed(() =>
  styleStore.loaded && styleStore.source === 'remote'
    ? styleStore.names
    : styleStore.names.length
      ? styleStore.names
      : STYLES
)

const project = ref(null)
const episodes = ref([])
const storyboards = ref([])
const assets = ref([])
const loading = ref(false)
const activeTab = ref('episodes')

const editVisible = ref(false)
const editForm = reactive({ title: '', genre: '', style: '', aspect_ratio: '9:16' })
const saving = ref(false)

/* 集编辑弹窗 */
const epVisible = ref(false)
const epForm = reactive({ id: null, title: '', synopsis: '' })
const epSaving = ref(false)

const cover = computed(() => imgUrlOf(project.value || {}))
const initial = computed(() => firstChar(project.value?.title))
const ratioText = computed(() => project.value?.aspect_ratio || project.value?.ratio || '9:16')

/* 页面本地时间格式化（Intl zh-CN） */
const dateFmt = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit'
})
function fmtDate(v) {
  if (!v) return ''
  const d = new Date(v)
  return Number.isNaN(d.getTime()) ? String(v) : dateFmt.format(d)
}

/* ---------- 素材聚合 ---------- */
const versionImages = computed(() =>
  storyboards.value.flatMap((sb) =>
    versionsOf(sb)
      .map((v) => imgUrlOf(v))
      .filter(Boolean)
      .map((url) => ({ url, from: `第${(sb.order_index ?? 0) + 1}幕` }))
  )
)

const assetsByType = computed(() => {
  const map = { image: [], audio: [], video: [], file: [] }
  for (const a of assets.value) {
    const t = assetTypeOf(a)
    ;(map[t] || map.file).push({
      name: assetNameOf(a),
      url: assetUrlOf(a),
      meta: a.meta || {}
    })
  }
  return map
})

const imageList = computed(() => {
  const seen = new Set()
  const out = []
  for (const img of versionImages.value) {
    if (!seen.has(img.url)) {
      seen.add(img.url)
      out.push(img)
    }
  }
  for (const a of assetsByType.value.image) {
    if (a.url && !seen.has(a.url)) {
      seen.add(a.url)
      out.push({ url: a.url, from: '素材库' })
    }
  }
  return out
})

const audioList = computed(() => assetsByType.value.audio.filter((a) => a.url))
const videoList = computed(() => {
  const seen = new Set()
  const out = []
  for (const sb of storyboards.value) {
    for (const sh of sb.shots || []) {
      const url = sh.video_url || (sh.versions || []).find((v) => v.video_url)?.video_url
      if (url && !seen.has(url)) {
        seen.add(url)
        out.push({ url, name: `第${(sb.order_index ?? 0) + 1}幕 · 镜头视频` })
      }
    }
  }
  for (const a of assetsByType.value.video) {
    if (a.url && !seen.has(a.url)) {
      seen.add(a.url)
      out.push({ url: a.url, name: a.name })
    }
  }
  return out
})

/* ---------- 数据加载 ---------- */
async function load() {
  loading.value = true
  try {
    const detail = unwrap(await api.get(`/projects/${projectId}`))
    const p = detail?.project ?? detail
    project.value = p
    episodes.value = asList(detail?.episodes ?? [], 'episodes', 'list', 'items')
    storyboards.value = asList(
      detail?.storyboards ?? detail?.project?.storyboards ?? [],
      'storyboards',
      'list',
      'items'
    ).map(normStoryboard)
    assets.value = asList(detail?.assets ?? [], 'assets', 'list', 'items')
  } finally {
    loading.value = false
  }
}

/* ---------- 剧集管理 ---------- */
function epStatusText(s) {
  return statusText(s)
}

function openAddEp() {
  Object.assign(epForm, { id: null, title: '', synopsis: '' })
  epVisible.value = true
}

function openEditEp(ep) {
  Object.assign(epForm, { id: ep.id, title: ep.title || '', synopsis: ep.synopsis || '' })
  epVisible.value = true
}

async function saveEp() {
  epSaving.value = true
  try {
    if (epForm.id) {
      await api.put(`/episodes/${epForm.id}`, {
        title: epForm.title,
        synopsis: epForm.synopsis
      })
    } else {
      await api.post(`/projects/${projectId}/episodes`, {
        title: epForm.title || undefined,
        synopsis: epForm.synopsis || undefined
      })
    }
    epVisible.value = false
    await load()
  } finally {
    epSaving.value = false
  }
}

async function removeEp(ep) {
  try {
    await ElMessageBox.confirm(
      `确定删除「${ep.title}」吗？该集的分镜与生成记录将保留但不再可达。`,
      '删除剧集',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  await api.delete(`/episodes/${ep.id}`)
  ElMessage.success('剧集已删除')
  await load()
}

async function genEpScript(ep) {
  await api.post(`/episodes/${ep.id}/generate-script`)
  ElMessage.success(`已提交「${ep.title}」剧本生成任务`)
}

async function runEpPipeline(ep) {
  await api.post(`/episodes/${ep.id}/pipeline`)
  ElMessage.success(`「${ep.title}」一键流水线已启动`)
}

function openEpEditor(ep) {
  router.push(`/editor/${projectId}?episode=${ep.id}`)
}

function handleEpCmd(cmd, ep) {
  if (cmd === 'edit') openEditEp(ep)
  else if (cmd === 'delete') removeEp(ep)
  else if (cmd === 'editor') openEpEditor(ep)
  else if (cmd === 'script') genEpScript(ep)
  else if (cmd === 'pipeline') runEpPipeline(ep)
}

/* ---------- 项目状态手动标记（乐观更新） ---------- */
const statusMenuOpen = ref(false)
const statusOptions = [
  { value: 'draft', label: '草稿' },
  { value: 'script_ready', label: '剧本就绪' },
  { value: 'producing', label: '制作中' },
  { value: 'completed', label: '已完成' },
  { value: 'failed', label: '失败' }
]

async function setProjectStatus(val) {
  statusMenuOpen.value = false
  if (!project.value || project.value.status === val) return
  const prev = project.value.status
  project.value = { ...project.value, status: val }
  try {
    await api.put(`/projects/${projectId}`, { status: val })
  } catch {
    project.value = { ...project.value, status: prev }
  }
}

function closeStatusMenu() {
  statusMenuOpen.value = false
}

watch(statusMenuOpen, (open) => {
  // 幂等：先删后加，避免多次打开时重复绑定
  document.removeEventListener('click', closeStatusMenu)
  if (open) document.addEventListener('click', closeStatusMenu)
})

// 注意：不能只写 onBeforeUnmount(closeStatusMenu)。watcher 在组件卸载后不再触发，
// 那里的 removeEventListener 永远不会执行，监听器会一直持有已销毁的组件实例。
onBeforeUnmount(() => document.removeEventListener('click', closeStatusMenu))

/* 集卡片智能按钮：按 stats 推导下一步 */
function epCta(ep) {
  const s = ep.stats || {}
  if (s.has_final) return { label: '查看成片', action: 'editor' }
  if ((s.storyboard_count || 0) > 0) return { label: '继续制作', action: 'editor' }
  return { label: '开始制作', action: 'pipeline' }
}

function epProgress(ep) {
  const s = ep.stats || {}
  if (!s.storyboard_count) return ''
  return `${s.completed_count || 0}/${s.storyboard_count} 画面`
}

async function epCtaClick(ep) {
  const cta = epCta(ep)
  if (cta.action === 'editor') {
    openEpEditor(ep)
  } else {
    await runEpPipeline(ep)
  }
}

function openEdit() {
  Object.assign(editForm, {
    title: project.value?.title || '',
    genre: project.value?.genre || '其他',
    style: project.value?.style || STYLES[0],
    aspect_ratio: ratioText.value
  })
  editVisible.value = true
}

async function saveEdit() {
  saving.value = true
  try {
    await api.put(`/projects/${projectId}`, {
      title: editForm.title,
      genre: editForm.genre,
      style: editForm.style,
      aspect_ratio: editForm.aspect_ratio
    })
    project.value = { ...project.value, ...editForm }
    editVisible.value = false
  } finally {
    saving.value = false
  }
}

/* ---------- 封面 ---------- */
const coverGenerating = ref(false)

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

// 组件卸载标志：封面轮询最长 4 分钟，用户离开页面后必须停止，否则会持续打接口
let alive = true
onBeforeUnmount(() => {
  alive = false
})

async function generateCover() {
  if (coverGenerating.value) return
  coverGenerating.value = true
  try {
    const { task_id } = unwrap(await api.post(`/projects/${projectId}/generate-cover`))
    // 轮询任务状态直至完成/失败
    for (let i = 0; i < 120; i++) {
      await sleep(2000)
      if (!alive) return
      let t = null
      try {
        t = unwrap(await api.get(`/tasks/${task_id}`))
      } catch {
        continue // 单次请求失败（网络抖动）不终止轮询
      }
      if (!alive) return
      if (t?.status === 'succeeded') {
        ElMessage.success('封面已生成')
        await load()
        return
      }
      if (t?.status === 'failed') {
        ElMessage.error(`封面生成失败：${t.error || '未知错误'}`)
        return
      }
    }
    if (alive) ElMessage.warning('封面生成超时，请稍后刷新查看')
  } finally {
    coverGenerating.value = false
  }
}

async function setAsCover(url) {
  if (!url) return
  await api.put(`/projects/${projectId}`, { cover_url: url })
  project.value = { ...project.value, cover_url: url }
  ElMessage.success('已设为项目封面')
}

async function removeProject() {
  const title = project.value?.title || '未命名项目'
  // 第一重确认：警告此操作不可恢复
  try {
    await ElMessageBox.confirm(
      `确定删除项目「${title}」吗？该项目的所有剧集、分镜、生成图片与视频将被一并删除。`,
      '删除项目',
      { type: 'warning', confirmButtonText: '继续删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  // 第二重确认：输入项目名防止误删
  let input = ''
  try {
    const res = await ElMessageBox.prompt(
      `此操作不可恢复！请输入项目名「${title}」以确认彻底删除。`,
      '再次确认',
      {
        type: 'error',
        confirmButtonText: '彻底删除',
        cancelButtonText: '取消',
        inputPlaceholder: title,
        inputValidator: (val) => (val && val.trim() === title ? true : '项目名不匹配')
      }
    )
    input = res?.value || ''
  } catch {
    return
  }
  if (input.trim() !== title) return
  await api.delete(`/projects/${projectId}`)
  ElMessage.success('项目已彻底删除')
  router.push('/')
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="g-page">
    <!-- 头部（参考稿 .project-detail-header） -->
    <div v-reveal class="project-detail-header">
      <button type="button" class="back-btn" aria-label="返回工作台" @click="router.push('/')">
        <svg
          aria-hidden="true"
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2.5"
        >
          <polyline points="15 18 9 12 15 6" />
        </svg>
      </button>

      <div class="cover">
        <img
          v-if="cover"
          :src="cover"
          :alt="`${project?.title || '未命名项目'} 封面`"
          width="640"
          height="360"
        />
        <div v-else class="cover-grad" :style="{ background: gradVar(projectId) }">
          <span>{{ initial }}</span>
        </div>
      </div>

      <div class="project-detail-info">
        <div class="title-line">
          <h1 class="title">{{ project?.title || '未命名项目' }}</h1>
          <div class="status-wrap">
            <el-tag
              :type="statusTagType(project?.status)"
              effect="light"
              round
              class="status-badge"
              title="点击标记项目状态"
              @click.stop="statusMenuOpen = !statusMenuOpen"
            >
              {{ statusText(project?.status) }}
              <el-icon class="status-caret" :size="10"><ArrowDown /></el-icon>
            </el-tag>
            <div v-if="statusMenuOpen" class="more-menu status-menu" @click.stop>
              <button
                v-for="s in statusOptions"
                :key="s.value"
                type="button"
                class="menu-item"
                :class="{ on: project?.status === s.value }"
                @click="setProjectStatus(s.value)"
              >
                {{ s.label }}
              </button>
            </div>
          </div>
        </div>
        <div class="project-detail-meta">
          <span class="tag tag-primary">{{ project?.genre || '其他' }}</span>
          <span class="tag tag-primary">{{ project?.style || '未指定风格' }}</span>
          <span class="tag">{{ ratioText }}</span>
          <span>{{ episodes.length }} 集</span>
          <span>{{ storyboards.length }} 分镜</span>
          <span>{{ imageList.length + audioList.length + videoList.length }} 素材</span>
          <span>
            创建于 {{ fmtDate(project?.created_at) }}
            <template v-if="project?.updated_at"> · 更新于 {{ fmtDate(project?.updated_at) }}</template>
          </span>
        </div>
        <div v-if="project?.inspiration || project?.raw_text" class="insp">
          灵感：{{ project?.inspiration || project?.raw_text }}
        </div>
      </div>

      <div class="ops">
        <el-button class="ops-btn" round @click="openEdit">
          <el-icon aria-hidden="true"><Edit /></el-icon>
          <span class="ops-label">编辑</span>
        </el-button>
        <el-button
          class="ops-btn"
          type="primary"
          round
          @click="router.push(`/editor/${projectId}`)"
        >
          <el-icon aria-hidden="true"><VideoPlay /></el-icon>
          <span class="ops-label">进入创作工作台</span>
        </el-button>
        <el-button class="ops-btn" type="danger" plain round @click="removeProject">
          删除项目
        </el-button>
      </div>
    </div>

    <el-tabs v-reveal="1" v-model="activeTab" class="detail-tabs">
      <el-tab-pane name="episodes">
        <template #label>
          <span class="tab-label">
            剧集
            <span class="count">{{ episodes.length }}</span>
          </span>
        </template>

        <div class="tab-toolbar">
          <el-button type="primary" round size="small" @click="openAddEp">
            <el-icon><Plus /></el-icon>
            <span class="ops-label">新增剧集</span>
          </el-button>
        </div>

        <div v-if="episodes.length" class="episode-grid">
          <div
            v-for="(ep, i) in episodes"
            :key="ep.id"
            v-reveal="Math.min(i + 1, 6)"
            class="episode-card g-card"
          >
            <div class="episode-card-head">
              <div class="ep-num">
                <span class="label">EP</span>
                <b>{{ String(ep.episode_number).padStart(2, '0') }}</b>
              </div>
              <el-tag size="small" effect="light" round>{{ epStatusText(ep.status) }}</el-tag>
            </div>
            <div class="episode-card-title" :title="ep.title">
              {{ ep.title || `第${ep.episode_number}集` }}
            </div>
            <div class="episode-card-syn" :title="ep.synopsis || ep.logline">
              {{ ep.synopsis || ep.logline || '（暂无梗概）' }}
            </div>
            <div class="episode-card-stats">
              <span>{{ ep.stats?.storyboard_count ?? 0 }} 分镜</span>
              <span>{{ ep.stats?.video_count ?? 0 }} 视频</span>
              <span v-if="epProgress(ep)" class="mono">{{ epProgress(ep) }}</span>
              <span v-if="ep.stats?.has_final" class="ok">已有成片</span>
            </div>
            <div class="episode-card-ops">
              <el-button type="primary" size="small" round @click="epCtaClick(ep)">
                {{ epCta(ep).label }}
              </el-button>
              <el-dropdown trigger="click" @command="(cmd) => handleEpCmd(cmd, ep)">
                <el-button size="small" round aria-label="更多操作">
                  <el-icon><MoreFilled /></el-icon>
                </el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="editor">进入工作台</el-dropdown-item>
                    <el-dropdown-item command="script">生成剧本</el-dropdown-item>
                    <el-dropdown-item command="pipeline">一键流水线</el-dropdown-item>
                    <el-dropdown-item command="edit" divided>编辑</el-dropdown-item>
                    <el-dropdown-item command="delete">删除</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </div>
        </div>
        <div v-else class="g-empty">
          <el-empty description="还没有剧集，点击「新增剧集」开始" :image-size="90">
            <el-button type="primary" round @click="openAddEp">新增剧集</el-button>
          </el-empty>
        </div>
      </el-tab-pane>

      <el-tab-pane name="assets">
        <template #label>
          <span class="tab-label">
            素材库
            <span class="count">{{ imageList.length + audioList.length + videoList.length }}</span>
          </span>
        </template>

        <template v-if="imageList.length || audioList.length || videoList.length">
          <template v-if="imageList.length">
            <h3 class="asset-title">图片（{{ imageList.length }}）</h3>
            <div class="asset-grid">
              <div
                v-for="(img, i) in imageList"
                :key="img.url"
                v-reveal="Math.min(i + 1, 6)"
                class="asset-card g-card"
              >
                <div class="asset-thumb">
                  <el-image
                    :src="img.url"
                    :alt="`素材图片 ${i + 1}（${img.from}）`"
                    :preview-src-list="imageList.map((x) => x.url)"
                    :initial-index="i"
                    fit="cover"
                    preview-teleported
                    loading="lazy"
                  />
                  <span class="kind">{{ img.from }}</span>
                  <el-button
                    class="set-cover-btn"
                    type="primary"
                    size="small"
                    round
                    :disabled="cover === img.url"
                    @click.stop="setAsCover(img.url)"
                  >
                    {{ cover === img.url ? '已是封面' : '设为封面' }}
                  </el-button>
                </div>
                <div class="asset-name">图片 {{ i + 1 }}</div>
              </div>
            </div>
          </template>

          <template v-if="videoList.length">
            <h3 class="asset-title">视频（{{ videoList.length }}）</h3>
            <div class="av-grid">
              <div
                v-for="(v, i) in videoList"
                :key="v.url"
                v-reveal="Math.min(i + 1, 6)"
                class="av-cell g-card"
              >
                <video :src="v.url" controls preload="metadata" />
                <span class="av-name">{{ v.name }}</span>
              </div>
            </div>
          </template>

          <template v-if="audioList.length">
            <h3 class="asset-title">音频（{{ audioList.length }}）</h3>
            <div class="audio-list">
              <div
                v-for="(a, i) in audioList"
                :key="a.url"
                v-reveal="Math.min(i + 1, 6)"
                class="audio-row g-card"
              >
                <span class="a-name">{{ a.name }}</span>
                <audio :src="a.url" controls preload="none" />
              </div>
            </div>
          </template>
        </template>
        <div v-else class="g-empty">
          <el-empty description="暂无素材，生成的画面 / 音频 / 视频会汇集到这里" :image-size="90" />
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 编辑项目弹窗 -->
    <el-dialog v-model="editVisible" title="编辑项目" width="440px">
      <el-form label-position="top">
        <el-form-item label="标题">
          <el-input
            v-model="editForm.title"
            name="project-name"
            autocomplete="off"
            maxlength="40"
          />
        </el-form-item>
        <el-form-item label="题材">
          <el-select v-model="editForm.genre" style="width: 100%">
            <el-option v-for="g in GENRES" :key="g" :label="g" :value="g" />
          </el-select>
        </el-form-item>
        <el-form-item label="风格">
          <el-select v-model="editForm.style" style="width: 100%">
            <el-option v-for="s in styleNames" :key="s" :label="s" :value="s" />
          </el-select>
        </el-form-item>
        <el-form-item label="画面比例">
          <el-radio-group v-model="editForm.aspect_ratio">
            <el-radio-button v-for="r in RATIOS" :key="r.value" :value="r.value">
              {{ r.label }}
            </el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="封面">
          <div class="cover-row">
            <div class="cover-preview">
              <img v-if="cover" :src="cover" alt="项目封面" />
              <div v-else class="cover-grad" :style="{ background: gradVar(projectId) }">
                <span>{{ initial }}</span>
              </div>
            </div>
            <div class="cover-actions">
              <el-button
                round
                size="small"
                :loading="coverGenerating"
                @click="generateCover"
              >
                <el-icon><MagicStick /></el-icon>
                <span class="ops-label">{{ cover ? '重新生成封面' : '生成封面' }}</span>
              </el-button>
              <span class="cover-hint">也可到「素材库」中选定画面设为封面</span>
            </div>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button round @click="editVisible = false">取消</el-button>
        <el-button type="primary" round :loading="saving" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 新增 / 编辑剧集弹窗 -->
    <el-dialog v-model="epVisible" :title="epForm.id ? '编辑剧集' : '新增剧集'" width="440px">
      <el-form label-position="top">
        <el-form-item label="剧集标题">
          <el-input
            v-model="epForm.title"
            placeholder="留空则自动命名为「第 N 集」"
            maxlength="40"
          />
        </el-form-item>
        <el-form-item label="本集梗概">
          <el-input
            v-model="epForm.synopsis"
            type="textarea"
            :rows="3"
            placeholder="这一集讲什么（供 AI 编剧参考）"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button round @click="epVisible = false">取消</el-button>
        <el-button type="primary" round :loading="epSaving" @click="saveEp">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
/* ---------- 头部（参考稿 .project-detail-header） ---------- */
.project-detail-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 32px;
  flex-wrap: wrap;
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
  transition: background-color 0.2s var(--ease-out),
    color 0.2s var(--ease-out), border-color 0.2s var(--ease-out);
  flex-shrink: 0;
  font-family: inherit;
}

.back-btn:hover {
  background: var(--surface-raised);
  color: var(--text-primary);
  border-color: var(--border-strong);
}

.cover {
  width: 200px;
  aspect-ratio: 16 / 9;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  flex-shrink: 0;
  background: var(--thumb-bg);
}

.cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.cover-grad {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.cover-grad span {
  font-size: var(--text-2xl);
  font-weight: 700;
  color: rgba(255, 255, 255, 0.92);
  text-shadow: 0 2px 12px rgba(0, 0, 0, 0.25);
}

.project-detail-info {
  flex: 1;
  min-width: 0;
}

.title-line {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
}

.title {
  margin: 0;
  font-size: 28px;
  font-weight: 800;
  letter-spacing: -1px;
  color: var(--text-primary);
  text-wrap: balance;
}

.project-detail-meta {
  display: flex;
  gap: 16px;
  font-size: 13.5px;
  color: var(--text-secondary);
  flex-wrap: wrap;
  align-items: center;
  margin-top: 8px;
}

.tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 12px;
  border-radius: var(--radius-pill);
  background: rgba(255, 255, 255, 0.08);
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
}

[data-theme='light'] .tag {
  background: rgba(29, 29, 31, 0.06);
}

.tag-primary {
  background: var(--primary-soft);
  color: var(--accent);
}

.insp {
  margin-top: var(--space-3);
  font-size: var(--text-sm);
  color: var(--text-secondary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.ops {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-shrink: 0;
  flex-wrap: wrap;
}

.ops-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.ops-label {
  margin-left: var(--space-1);
}

/* ---------- 项目状态角标菜单 ---------- */
.status-wrap {
  position: relative;
  display: inline-flex;
}

.status-badge {
  cursor: pointer;
  user-select: none;
}

.status-caret {
  margin-left: 4px;
  opacity: 0.7;
}

.more-menu.status-menu {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  z-index: 20;
  min-width: 132px;
  background: var(--surface-raised, var(--surface));
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-lg, var(--shadow));
  padding: 6px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.menu-item {
  appearance: none;
  border: none;
  background: transparent;
  font-family: inherit;
  text-align: left;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  padding: 7px 10px;
  border-radius: var(--radius-sm, 8px);
  cursor: pointer;
  transition: background-color 0.15s var(--ease-out), color 0.15s var(--ease-out);
}

.menu-item:hover {
  background: var(--surface-hover);
  color: var(--text-primary);
}

.menu-item.on {
  background: var(--primary-soft);
  color: var(--accent);
}

/* ---------- Tabs（对齐参考稿 .detail-tabs 形态） ---------- */
.tab-toolbar {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-4);
}

.sb-ep-select {
  width: 220px;
}

/* ---------- 剧集卡片 ---------- */
.episode-grid {
  display: grid;
  grid-template-columns: repeat(1, 1fr);
  gap: 16px;
}

@media (min-width: 640px) {
  .episode-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (min-width: 1100px) {
  .episode-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}

.episode-card {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  transition: transform 0.4s var(--ease-out), box-shadow 0.4s var(--ease-out);
}

.episode-card:hover {
  transform: translateY(-3px);
  box-shadow: var(--shadow);
}

.episode-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.episode-card-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.episode-card-syn {
  font-size: 13px;
  color: var(--text-secondary);
  min-height: 34px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.episode-card-stats {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: var(--text-tertiary);
}

.episode-card-stats .ok {
  color: var(--success);
  font-weight: 600;
}

.episode-card-ops {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding-top: 10px;
  border-top: 1px solid var(--divider);
}

.detail-tabs :deep(.el-tabs__header) {
  margin-bottom: 28px;
}

.detail-tabs :deep(.el-tabs__nav-wrap::after) {
  background-color: var(--divider);
  height: 1px;
}

.detail-tabs :deep(.el-tabs__item) {
  font-size: 14px;
  font-weight: 600;
  padding: 10px 16px;
  height: auto;
  line-height: 1.4;
  color: var(--text-secondary);
}

.detail-tabs :deep(.el-tabs__item:hover) {
  color: var(--text-primary);
}

.detail-tabs :deep(.el-tabs__item.is-active) {
  color: var(--primary);
}

.detail-tabs :deep(.el-tabs__active-bar) {
  height: 2px;
  border-radius: var(--radius-pill);
  background-color: var(--primary);
}

.tab-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.tab-label .count {
  font-family: var(--font-mono);
  font-size: 11px;
  background: rgba(255, 255, 255, 0.08);
  padding: 2px 8px;
  border-radius: 6px;
  color: var(--text-tertiary);
}

[data-theme='light'] .tab-label .count {
  background: rgba(29, 29, 31, 0.06);
}

.detail-tabs :deep(.el-tabs__item.is-active) .tab-label .count {
  background: rgba(0, 113, 227, 0.15);
  color: #5ac8fa;
}

/* ---------- 分镜编号徽标（剧集卡片复用） ---------- */
.ep-num {
  display: flex;
  align-items: baseline;
  gap: 4px;
  padding: 6px 12px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.06);
  font-family: var(--font-mono);
}

[data-theme='light'] .ep-num {
  background: rgba(29, 29, 31, 0.05);
}

.ep-num .label {
  font-size: 10px;
  font-weight: 700;
  color: var(--text-tertiary);
  letter-spacing: 0.08em;
}

.ep-num b {
  font-size: 18px;
  font-weight: 800;
  color: var(--text-primary);
}

/* ---------- 素材库（参考稿 .asset-grid / .asset-card） ---------- */
.asset-title {
  font-size: var(--text-base);
  font-weight: 700;
  letter-spacing: -0.01em;
  margin: var(--space-5) 0 var(--space-3);
}

.asset-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

@media (min-width: 640px) {
  .asset-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (min-width: 1024px) {
  .asset-grid {
    grid-template-columns: repeat(4, 1fr);
  }
}

.asset-card {
  cursor: pointer;
  transition: transform 0.4s var(--ease-out), box-shadow 0.4s var(--ease-out),
    border-color 0.4s var(--ease-out);
}

.asset-card:hover {
  transform: translateY(-3px);
  box-shadow: var(--shadow);
}

.asset-thumb {
  aspect-ratio: 1;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--thumb-bg);
  overflow: hidden;
}

.asset-thumb .el-image {
  width: 100%;
  height: 100%;
}

.asset-thumb .kind {
  position: absolute;
  bottom: 8px;
  left: 8px;
  font-size: 11px;
  font-weight: 600;
  background: rgba(0, 0, 0, 0.6);
  color: #fff;
  padding: 3px 10px;
  border-radius: var(--radius-pill);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.asset-thumb .set-cover-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  opacity: 0;
  transition: opacity 0.25s var(--ease-out);
}

.asset-card:hover .set-cover-btn,
.asset-card:focus-within .set-cover-btn {
  opacity: 1;
}

.set-cover-btn[disabled] {
  opacity: 1;
}

/* ---------- 编辑弹窗封面区 ---------- */
.cover-row {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  width: 100%;
}

.cover-preview {
  width: 120px;
  aspect-ratio: 16 / 9;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  overflow: hidden;
  flex-shrink: 0;
  background: var(--thumb-bg);
}

.cover-preview img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.cover-actions {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  min-width: 0;
}

.cover-hint {
  font-size: 12px;
  color: var(--text-tertiary);
  line-height: 1.5;
}

.asset-name {
  padding: 10px 12px;
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--text-primary);
}

/* ---------- 视频 / 音频（容器对齐 .g-card） ---------- */
.av-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 16px;
}

.av-cell {
  min-width: 0;
  padding: 12px;
  transition: transform 0.4s var(--ease-out), box-shadow 0.4s var(--ease-out);
}

.av-cell:hover {
  transform: translateY(-3px);
  box-shadow: var(--shadow);
}

.av-cell video {
  width: 100%;
  aspect-ratio: 16 / 9;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: #000;
  display: block;
}

.av-name {
  display: block;
  margin-top: var(--space-2);
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.audio-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.audio-row {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-3) var(--space-4);
}

.a-name {
  flex: 0 1 auto;
  min-width: 0;
  font-size: var(--text-sm);
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.audio-row audio {
  flex: 1;
  min-width: 0;
  width: 100%;
  height: 36px;
}

/* ---------- 窄屏 ---------- */
@media (max-width: 768px) {
  .project-detail-header {
    flex-direction: column;
    align-items: stretch;
  }
  .back-btn {
    align-self: flex-start;
  }
  .cover {
    width: 100%;
  }
  .ops {
    flex-direction: row;
    flex-wrap: wrap;
  }
  .ops .ops-btn {
    flex: 1;
  }
  .audio-row {
    flex-direction: column;
    align-items: stretch;
    gap: var(--space-2);
  }
}
</style>
