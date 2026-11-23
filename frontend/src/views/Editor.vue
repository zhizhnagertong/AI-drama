<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import api, { unwrap, refreshOnce } from '../api'
import { accessExpiresAt } from '../api/session'
import { useAuthStore } from '../stores/auth'
import { useProjectStore } from '../stores/project'
import TaskProgress from '../components/TaskProgress.vue'
import * as U from '../utils'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const projectStore = useProjectStore()
const projectId = route.params.id

/* ---------------- 状态 ---------------- */
const project = ref(null)
const episodes = ref([])
const currentEpisodeId = ref(null)
const storyboards = ref([])
const characters = ref([])
const assets = ref([])
const timelines = ref([])
const refreshing = ref(false)
const activeTab = ref('script')
/* 纯 UI：<1024px 侧栏抽屉开关 */
const sidebarOpen = ref(false)

const currentEpisode = computed(
  () => episodes.value.find((e) => e.id === currentEpisodeId.value) || null
)

const steps = [
  { key: 'script', label: '剧本', desc: 'AI 生成分镜脚本', icon: '📝' },
  { key: 'character', label: '角色', desc: '形象与音色设定', icon: '🎭' },
  { key: 'board', label: '画面分镜', desc: '分镜编排 · 抽卡选定 · 视频', icon: '🎨' },
  { key: 'voice', label: '配音', desc: '台词语音合成', icon: '🎤' },
  { key: 'final', label: '成片', desc: '时间线与合成', icon: '🎬' }
]

/* 三态流水线：后端 pipeline-status 优先，未返回时前端兜底推导；分镜与画面已合并为「画面分镜」一步 */
const pipe = ref(null)
const doneMap = computed(() => {
  const localBoard = storyboards.value.some((sb) => (sb.shots || []).length > 0)
  const localImage =
    storyboards.value.length > 0 && storyboards.value.every((sb) => U.hasSelected(sb))
  const local = {
    script: storyboards.value.length > 0,
    character: characters.value.length > 0,
    board: localBoard && localImage,
    voice: assets.value.some((a) => U.assetTypeOf(a) === 'audio'),
    final: timelines.value.some((t) => t.status === 'completed' && t.output_url)
  }
  const p = pipe.value
  if (!p) return local
  return {
    script: p.script?.status === 'done' || local.script,
    character: p.character?.status === 'done' || local.character,
    board: (p.board?.status === 'done' || localBoard) && (p.image?.status === 'done' || localImage),
    voice: p.voice?.status === 'done' || local.voice,
    final: p.final?.status === 'done' || local.final
  }
})

function stepState(key) {
  if (doneMap.value[key]) return 'done'
  const p = pipe.value
  if (!p) return 'pending'
  const active = (k) => p[k] && (p[k].status === 'partial' || p[k].status === 'running')
  if (key === 'board' ? active('board') || active('image') : active(key)) return 'active'
  return 'pending'
}

function stepCount(key) {
  const p = pipe.value
  /* 画面分镜步展示抽卡进度（后端 image 环节计数） */
  const src = key === 'board' ? p?.image : p?.[key]
  if (src && typeof src.completed === 'number' && typeof src.total === 'number' && src.total > 0)
    return `${src.completed}/${src.total}`
  return ''
}

const firstTodoStep = computed(() => {
  const order = ['script', 'character', 'board', 'voice', 'final']
  return order.find((k) => !doneMap.value[k]) || null
})

const ctaLabel = computed(() => {
  if (doneMap.value.final) return '查看成片'
  if (!firstTodoStep.value) return '查看成片'
  if (firstTodoStep.value === 'script') return '开始制作'
  return '继续制作'
})

function smartCta() {
  pickStep(doneMap.value.final ? 'final' : firstTodoStep.value || 'final')
}

/* 顶栏进度：done 环节数 / 总环节数 */
const pipelineProgress = computed(() => {
  const order = ['script', 'character', 'board', 'voice', 'final']
  const done = order.filter((k) => doneMap.value[k]).length
  return `${done}/${order.length}`
})

/* 纯 UI：当前步骤序号（01-06）与标题 */
const stepIndex = computed(() => {
  const i = steps.findIndex((s) => s.key === activeTab.value)
  return i < 0 ? 0 : i
})
const stepNo = computed(() => String(stepIndex.value + 1).padStart(2, '0'))
const stepName = computed(() => steps[stepIndex.value]?.label ?? '')

function pickStep(key) {
  activeTab.value = key
  sidebarOpen.value = false
}

/* ---------------- 数据加载 ---------------- */
function normTimeline(t) {
  if (!t || typeof t !== 'object') return { items: [] }
  const raw = Array.isArray(t.items) ? t.items : t.items?.items ?? t.timeline_items ?? []
  const items = raw.map((it, i) => ({
    id: it.id ?? it.shot_id ?? i,
    storyboard_id: it.storyboard_id,
    shot_id: it.shot_id ?? it.id,
    version_id: it.version_id,
    media_url: it.media_url || U.imgUrlOf(it) || U.imgUrlOf(it.shot || {}),
    duration: it.duration_sec ?? it.duration ?? it.duration_seconds ?? 3,
    subtitle: it.subtitle ?? it.subtitle_text ?? it.dialogue ?? '',
    audio_url: it.audio_url || it.voice_url || ''
  }))
  return { ...t, items }
}

let loadSeq = 0

async function loadAll() {
  // 并发保护：loadAll 会被切换剧集、SSE 完成回调、手动刷新同时触发，
  // 后返回的旧响应会覆盖新数据（出现“选中第 2 集却显示第 1 集分镜”），
  // 用递增序号丢弃过期响应。
  const seq = ++loadSeq
  refreshing.value = true
  try {
    const detail = unwrap(await api.get(`/projects/${projectId}`)) || {}
    if (seq !== loadSeq) return
    project.value = detail.project ?? detail

    episodes.value = U.asList(detail.episodes ?? [], 'episodes', 'list', 'items')
    if (!currentEpisodeId.value) {
      const q = Number(route.query.episode)
      currentEpisodeId.value =
        episodes.value.find((e) => e.id === q)?.id ?? episodes.value[0]?.id ?? null
    } else if (!episodes.value.some((e) => e.id === currentEpisodeId.value)) {
      currentEpisodeId.value = episodes.value[0]?.id ?? null
    }

    let sbs = U.asList(
      detail.storyboards ?? detail.project?.storyboards ?? [],
      'storyboards',
      'list',
      'items'
    )
    if (!sbs.length) {
      try {
        const r = unwrap(await api.get(`/projects/${projectId}/storyboards`))
        if (seq !== loadSeq) return
        sbs = U.asList(r, 'storyboards', 'list', 'items')
      } catch {
        /* 无独立分镜接口时忽略 */
      }
    }
    if (seq !== loadSeq) return
    // 按当前集过滤（历史数据 episode_id 为空时归入第一集展示）
    const epForFilter = currentEpisodeId.value
    if (epForFilter) {
      sbs = sbs.filter((sb) => !sb.episode_id || sb.episode_id === epForFilter)
    }
    storyboards.value = sbs.map((sb, i) => U.normStoryboard(sb, i))

    let chars = U.asList(detail.characters ?? [], 'characters', 'list', 'items')
    try {
      const r = unwrap(await api.get('/characters', { params: { project_id: projectId } }))
      if (seq !== loadSeq) return
      const fromApi = U.asList(r, 'characters', 'list', 'items')
      if (fromApi.length) chars = fromApi
    } catch {
      /* 忽略 */
    }
    if (seq !== loadSeq) return
    characters.value = chars

    assets.value = U.asList(detail.assets ?? [], 'assets', 'list', 'items')
    let tls = U.asList(detail.timelines ?? [], 'timelines', 'list', 'items')
    if (epForFilter) {
      tls = tls.filter((t) => !t.episode_id || t.episode_id === epForFilter)
    }
    timelines.value = tls.map(normTimeline)

    projectStore.setAll({
      project: project.value,
      storyboards: storyboards.value,
      characters: characters.value,
      assets: assets.value,
      timelines: timelines.value
    })
    loadPipeline()
  } finally {
    // 只有最新一次加载才负责收尾，避免旧请求把 loading 提前关掉
    if (seq === loadSeq) refreshing.value = false
  }
}

async function loadPipeline() {
  if (!currentEpisodeId.value) {
    pipe.value = null
    return
  }
  try {
    const r = unwrap(await api.get(`/episodes/${currentEpisodeId.value}/pipeline-status`))
    pipe.value = r?.steps ?? null
  } catch {
    pipe.value = null
  }
}

function switchEpisode(id) {
  if (id === currentEpisodeId.value) return
  currentEpisodeId.value = id
  scriptDirty.value = false
  loadAll()
}

/* ---------------- SSE 任务进度 ---------------- */
const tasks = reactive({})
const taskList = computed(() => Object.values(tasks))
const activeTaskCount = computed(
  () =>
    taskList.value.filter((t) => ['pending', 'queued', 'running', 'processing'].includes(t.status))
      .length
)
const failedTasks = computed(() => taskList.value.filter((t) => t.status === 'failed'))
let es = null
let reconnectTimer = null
let refreshTimer = null

let streamRetry = 0

async function connectStream() {
  if (es) es.close()
  if (!auth.isLoggedIn) return
  // EventSource 无法携带 Header，令牌过期会导致 401 重连风暴；access 临期时无感续期
  if (accessExpiresAt.value <= Date.now() + 60_000) {
    try {
      await refreshOnce()
    } catch {
      /* 刷新失败由请求层广播处理，仍用当前令牌尝试 */
    }
  }
  if (!auth.token) return
  // EventSource 无法携带自定义 Header：先用 Authorization 换一次性票据（60s 有效），
  // 避免把 access token 拼进 URL 而泄漏到浏览器历史与反代日志。
  let ticket = ''
  try {
    const t = unwrap(await api.post(`/projects/${projectId}/stream-ticket`))
    ticket = t?.ticket || ''
  } catch {
    return // 票据获取失败（未登录/无权限）由请求层统一提示
  }
  if (!ticket || !auth.isLoggedIn) return
  es = new EventSource(
    `/api/v1/projects/${projectId}/stream?ticket=${encodeURIComponent(ticket)}`
  )
  es.onmessage = (e) => {
    let data
    try {
      data = JSON.parse(e.data)
    } catch {
      return
    }
    // 建连时后端补发的进行中任务快照（SSE 无事件重放，断线期间事件会丢失）
    if (data && data.type === 'snapshot' && Array.isArray(data.tasks)) {
      data.tasks.forEach((t) => handleTaskEvent({ ...t, type: 'task_update' }))
      return
    }
    handleTaskEvent(data)
  }
  es.onerror = () => {
    es?.close()
    es = null
    // 原实现无条件 3 秒重连：令牌失效或断网时会形成永久 401 重连风暴。
    // 改为指数退避 + 次数上限，登录态失效即停。
    if (!auth.isLoggedIn) return
    if (streamRetry >= 6) return
    const delay = Math.min(30000, 1000 * 2 ** streamRetry)
    streamRetry += 1
    clearTimeout(reconnectTimer)
    reconnectTimer = setTimeout(connectStream, delay)
  }
  es.onopen = () => {
    streamRetry = 0
  }
}

function handleTaskEvent(data) {
  if (!data || typeof data !== 'object') return
  const tid = data.task_id || data.id
  if (!tid) return
  const prev = tasks[tid] || {}
  // SSE 事件里 type 是事件名（task_update），真实任务类型在 task_type；轮询接口则直接是 type
  const ttype = data.task_type || (data.type === 'task_update' ? prev.type : data.type)
  tasks[tid] = { ...prev, ...data, task_id: tid, type: ttype }
  if (data.status === 'succeeded') {
    ElMessage.success(`${U.taskTypeLabel(ttype)}完成`)
    scheduleRefresh()
  } else if (data.status === 'failed') {
    showErrorOnce(`${U.taskTypeLabel(ttype)}失败：${data.error || '请重试'}`)
  }
}

/* 同类错误合并提示：批量任务失败时避免刷屏 */
let lastErrText = ''
let lastErrAt = 0
let errCount = 0
let errTimer = null
function showErrorOnce(text) {
  const now = Date.now()
  if (text === lastErrText && now - lastErrAt < 4000) {
    errCount++
    lastErrAt = now
    clearTimeout(errTimer)
    errTimer = setTimeout(() => {
      ElMessage.error(`${text}（同类失败共 ${errCount + 1} 次）`)
      errCount = 0
    }, 2500)
    return
  }
  lastErrText = text
  lastErrAt = now
  errCount = 0
  ElMessage.error(text)
}

function scheduleRefresh() {
  clearTimeout(refreshTimer)
  refreshTimer = setTimeout(() => loadAll(), 500)
}

async function retryTask(t) {
  try {
    await api.post(`/tasks/${t.task_id}/retry`)
    tasks[t.task_id] = { ...tasks[t.task_id], status: 'pending', error: '' }
    ElMessage.success('已重新提交任务')
  } catch {
    /* 拦截器已提示 */
  }
}

async function cancelTask(t) {
  try {
    await api.post(`/tasks/${t.task_id}/cancel`)
    tasks[t.task_id] = { ...tasks[t.task_id], status: 'canceled', error: '' }
    ElMessage.success('已请求取消任务')
  } catch {
    /* 拦截器已提示 */
  }
}

async function retryAllFailed() {
  const list = failedTasks.value
  if (!list.length) return
  try {
    for (const t of list) {
      await api.post(`/tasks/${t.task_id}/retry`)
      tasks[t.task_id] = { ...tasks[t.task_id], status: 'pending', error: '' }
    }
    ElMessage.success(`已重新提交 ${list.length} 个失败任务`)
  } catch {
    /* 拦截器已提示 */
  }
}

/* ---------------- 剧本 Tab ---------------- */
const generatingScript = ref(false)
const sbEditVisible = ref(false)
const sbForm = reactive({
  id: null,
  shot_type: '',
  description: '',
  dialogue: '',
  emotion: '',
  duration: 3
})

async function generateScript() {
  const hasBoards = storyboards.value.length > 0
  if (hasBoards) {
    try {
      await ElMessageBox.confirm(
        '重新生成剧本会删除本集现有的全部分镜与已生成的画面，确定继续吗？',
        '重新生成剧本',
        { type: 'warning', confirmButtonText: '仍然重新生成', cancelButtonText: '取消' }
      )
    } catch {
      return
    }
  }
  generatingScript.value = true
  try {
    const path = currentEpisodeId.value
      ? `/episodes/${currentEpisodeId.value}/generate-script`
      : `/projects/${projectId}/generate-script`
    await api.post(path)
    ElMessage.success('已提交剧本生成任务')
  } finally {
    generatingScript.value = false
  }
}

/* 剧本全文（梗概）可编辑：存 episode.synopsis，不影响分镜 */
const scriptText = ref('')
const scriptDirty = ref(false)
const scriptSaving = ref(false)

watch(
  currentEpisode,
  (ep) => {
    // 用户正在编辑且未保存时，不被刷新（SSE 触发的 loadAll）覆盖
    if (scriptDirty.value) return
    scriptText.value = ep?.synopsis || ep?.logline || ''
  },
  { immediate: true }
)

function onScriptInput() {
  scriptDirty.value = true
}

async function saveScriptText() {
  if (!currentEpisodeId.value) return
  scriptSaving.value = true
  try {
    await api.put(`/episodes/${currentEpisodeId.value}`, { synopsis: scriptText.value })
    scriptDirty.value = false
    ElMessage.success('剧本梗概已保存')
    await loadAll()
  } finally {
    scriptSaving.value = false
  }
}

const extractingChars = ref(false)
async function extractChars() {
  if (!currentEpisodeId.value) {
    ElMessage.warning('请先生成剧本')
    return
  }
  extractingChars.value = true
  try {
    const r = unwrap(await api.post(`/episodes/${currentEpisodeId.value}/extract-characters`))
    ElMessage.success(`角色提取完成：新增 ${r?.created ?? 0}，更新 ${r?.updated ?? 0}`)
    await loadAll()
  } finally {
    extractingChars.value = false
  }
}

function addSb() {
  Object.assign(sbForm, {
    id: null,
    shot_type: '中景',
    description: '',
    dialogue: '',
    emotion: '',
    duration: 3
  })
  sbEditVisible.value = true
}

function openEditSb(index) {
  const sb = storyboards.value[index]
  Object.assign(sbForm, {
    id: sb.id,
    shot_type: sb.shot_type || '',
    description: sb.description || '',
    dialogue: sb.dialogue || '',
    emotion: sb.emotion || '',
    duration: Number(sb.duration) || 3
  })
  sbEditVisible.value = true
}

async function saveSb() {
  // 前端先挡一次：画面描述为空时后端会 422，但提示不明确、弹窗也不关
  if (!String(sbForm.description || '').trim()) {
    ElMessage.warning('请填写画面描述')
    return
  }
  const payload = {
    shot_size: sbForm.shot_type,
    scene: sbForm.description,
    dialogue: sbForm.dialogue,
    emotion: sbForm.emotion,
    duration_sec: Math.max(1, Math.round(Number(sbForm.duration) || 3))
  }
  try {
    if (sbForm.id) {
      await api.put(`/storyboards/${sbForm.id}`, payload)
      const idx = storyboards.value.findIndex((s) => s.id === sbForm.id)
      if (idx >= 0) Object.assign(storyboards.value[idx], { ...sbForm })
      ElMessage.success('分镜已更新')
    } else {
      // 带当前集 id：否则后端回退默认集，在非第 1 集新增会落错集
      await api.post(
        `/projects/${projectId}/storyboards`,
        currentEpisodeId.value ? { ...payload, episode_id: currentEpisodeId.value } : payload
      )
      ElMessage.success('分镜已新增')
      await loadAll()
    }
  } catch (err) {
    // 失败保持弹窗打开，避免用户输入丢失
    ElMessage.error(err?.friendlyMessage || '保存失败，请重试')
    return
  }
  sbEditVisible.value = false
}

async function delSb(sb) {
  try {
    await ElMessageBox.confirm('删除后该分镜的镜头与画面版本将一并删除，确定吗？', '删除分镜', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消'
    })
  } catch {
    return
  }
  await api.delete(`/storyboards/${sb.id}`)
  storyboards.value = storyboards.value.filter((s) => s.id !== sb.id)
  ElMessage.success('分镜已删除')
}

async function moveSb(index, d) {
  const arr = storyboards.value
  const j = index + d
  if (j < 0 || j >= arr.length) return
  ;[arr[index], arr[j]] = [arr[j], arr[index]]
  try {
    await api.put(`/projects/${projectId}/storyboards/reorder`, {
      ordered_ids: arr.map((s) => s.id)
    })
  } catch {
    /* 拦截器已提示 */
  }
}

/* ---------------- 角色 Tab ---------------- */
const charEditVisible = ref(false)
const charForm = reactive({
  id: null,
  name: '',
  description: '',
  prompt_template: '',
  voice: ''
})
const refLoading = reactive({})
let audioEl = null

function addChar() {
  Object.assign(charForm, {
    id: null,
    name: '',
    description: '',
    prompt_template: '',
    voice: 'longxiaochun'
  })
  charEditVisible.value = true
}

function openEditChar(c) {
  Object.assign(charForm, {
    id: c.id,
    name: c.name || '',
    description: c.description || '',
    prompt_template: c.prompt_template || c.prompt || '',
    voice: c.voice || ''
  })
  charEditVisible.value = true
}

async function saveChar() {
  const payload = {
    name: String(charForm.name || '').trim(),
    description: charForm.description,
    prompt_template: charForm.prompt_template,
    voice: charForm.voice
  }
  if (!payload.name) {
    ElMessage.warning('请填写角色名称')
    return
  }
  try {
    if (charForm.id) {
      await api.put(`/characters/${charForm.id}`, payload)
      const idx = characters.value.findIndex((c) => c.id === charForm.id)
      if (idx >= 0) {
        Object.assign(characters.value[idx], payload)
      }
      ElMessage.success('角色已更新')
    } else {
      const created = unwrap(await api.post(`/projects/${projectId}/characters`, payload))
      characters.value.push(created)
      ElMessage.success('角色已新增')
    }
  } catch (err) {
    ElMessage.error(err?.friendlyMessage || '保存失败，请重试')
    return
  }
  charEditVisible.value = false
}

async function delChar(c) {
  try {
    await ElMessageBox.confirm(`确定删除角色「${c.name || '未命名角色'}」吗？`, '删除角色', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消'
    })
  } catch {
    return
  }
  await api.delete(`/characters/${c.id}`)
  characters.value = characters.value.filter((x) => x.id !== c.id)
  ElMessage.success('角色已删除')
}

async function genRef(c) {
  refLoading[c.id] = true
  try {
    await api.post(`/characters/${c.id}/generate-ref`)
    ElMessage.success('已提交参考图生成任务')
  } finally {
    refLoading[c.id] = false
  }
}

function playAudio(url) {
  if (!url) {
    ElMessage.warning('暂无试听音频')
    return
  }
  audioEl?.pause()
  audioEl = new Audio(url)
  audioEl.play().catch(() => ElMessage.warning('音频播放失败'))
}

async function audition(c) {
  const data = unwrap(await api.get(`/characters/${c.id}/audition`))
  const url =
    (typeof data === 'string' && data) || data?.audio_url || data?.url || ''
  playAudio(url)
}

function charOf(sb) {
  return (
    characters.value.find((c) => c.id === sb.character_id) ||
    characters.value.find((c) => c.name && c.name === sb.character_name)
  )
}

/* ---------------- 分镜 / 画面 Tab ---------------- */
const genVisible = ref(false)
const genForm = reactive({ sbId: null, count: 2 })
const generating = ref(false)

/* 批量模式：选择 + 成本确认 */
const batchMode = ref(false)
const batchSel = ref(new Set())
const batchImageVisible = ref(false)
const batchImageCount = ref(2)
const batchVideoVisible = ref(false)
const batchVideoSeconds = ref('5')
const batchSubmitting = ref(false)

function toggleBatchMode() {
  batchMode.value = !batchMode.value
  if (!batchMode.value) batchSel.value = new Set()
}

function toggleBatchSel(id) {
  const s = new Set(batchSel.value)
  s.has(id) ? s.delete(id) : s.add(id)
  batchSel.value = s
}

function selectAllBatch() {
  batchSel.value = new Set(storyboards.value.map((sb) => sb.id))
}

function openBatchImages() {
  if (!currentEpisodeId.value) {
    ElMessage.warning('请先选择剧集')
    return
  }
  if (!batchSel.value.size) {
    ElMessage.warning('请先勾选分镜')
    return
  }
  batchImageVisible.value = true
}

async function confirmBatchImages() {
  batchSubmitting.value = true
  try {
    const r = unwrap(
      await api.post(`/episodes/${currentEpisodeId.value}/batch-images`, {
        storyboard_ids: [...batchSel.value],
        count: batchImageCount.value
      })
    )
    batchImageVisible.value = false
    batchMode.value = false
    batchSel.value = new Set()
    ElMessage.success(`已提交 ${r?.submitted ?? 0} 个画面生成任务`)
  } finally {
    batchSubmitting.value = false
  }
}

function openBatchVideos() {
  if (!currentEpisodeId.value) {
    ElMessage.warning('请先选择剧集')
    return
  }
  if (!batchSel.value.size) {
    ElMessage.warning('请先勾选分镜')
    return
  }
  batchVideoVisible.value = true
}

async function confirmBatchVideos() {
  batchSubmitting.value = true
  try {
    const r = unwrap(
      await api.post(`/episodes/${currentEpisodeId.value}/batch-videos`, {
        storyboard_ids: [...batchSel.value],
        seconds: batchVideoSeconds.value
      })
    )
    batchVideoVisible.value = false
    batchMode.value = false
    batchSel.value = new Set()
    const skipped = (r?.skipped || []).length
    ElMessage.success(
      `已提交 ${r?.submitted ?? 0} 个视频生成任务${skipped ? `，跳过 ${skipped} 个（无选定画面或已有视频）` : ''}`
    )
  } finally {
    batchSubmitting.value = false
  }
}

function openGenImage(sb) {
  genForm.sbId = sb.id
  genForm.count = 2
  genVisible.value = true
}

async function confirmGen() {
  generating.value = true
  try {
    await api.post(`/storyboards/${genForm.sbId}/generate-image`, { count: genForm.count })
    genVisible.value = false
    ElMessage.success(`已提交 ${genForm.count} 张画面生成任务`)
  } finally {
    generating.value = false
  }
}

async function regenImage(sb) {
  await api.post(`/storyboards/${sb.id}/generate-image`, { count: 1 })
  ElMessage.success('已提交重新生成任务')
}

function isSelected(sb, v) {
  return U.selectedOf(sb)?.id === v.id
}

async function selectVersion(sb, v) {
  await api.post(`/shots/${v.shot_id}/select-version`, { version_id: v.id })
  ElMessage.success('已选定该版本')
  loadAll()
}

/* ---------------- 版本编辑 / 删除 ---------------- */
const versionEditVisible = ref(false)
const versionForm = reactive({ shot_id: null, version_id: null, prompt: '', seed: null })

function openEditVersion(v) {
  Object.assign(versionForm, {
    shot_id: v.shot_id,
    version_id: v.id,
    prompt: v.prompt || '',
    seed: v.seed ?? null
  })
  versionEditVisible.value = true
}

async function saveVersion() {
  const payload = { prompt: versionForm.prompt }
  if (versionForm.seed !== null && versionForm.seed !== undefined && versionForm.seed !== '') {
    payload.seed = Number(versionForm.seed)
  }
  await api.put(`/shots/${versionForm.shot_id}/versions/${versionForm.version_id}`, payload)
  versionEditVisible.value = false
  ElMessage.success('版本已更新')
  loadAll()
}

async function delVersion(sb, v) {
  try {
    await ElMessageBox.confirm(
      isSelected(sb, v)
        ? '该版本已被选定，删除后镜头的选定状态将被清空，确定删除吗？'
        : '确定删除该画面版本吗？',
      '删除版本',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  await api.delete(`/shots/${v.shot_id}/versions/${v.id}`)
  ElMessage.success('版本已删除')
  loadAll()
}

function selectedShots(sb) {
  return (sb?.shots || []).filter((sh) => {
    const vs = sh.versions || []
    return (
      !!sh.selected_version_id ||
      vs.some((v) => v.id === sh.selected_version_id || v.is_selected || v.selected)
    )
  })
}

async function genVideo(sb) {
  const targets = selectedShots(sb)
  if (!targets.length) {
    ElMessage.warning('请先选定一个画面版本')
    return
  }
  for (const sh of targets) {
    await api.post(`/shots/${sh.id}/generate-video`)
  }
  ElMessage.success('已提交视频生成任务')
}

/* ---------------- 配音 Tab ---------------- */
async function genVoice(sb) {
  const c = charOf(sb)
  await api.post(`/storyboards/${sb.id}/generate-voice`, {
    character_id: c?.id,
    voice: c?.voice
  })
  ElMessage.success('已提交配音任务')
}

/* ---------------- 成片 Tab ---------------- */
const currentTimeline = computed(() => {
  const ts = timelines.value
  if (!ts.length) return null
  return ts.find((t) => t.status === 'completed' && t.output_url) || ts[ts.length - 1]
})

const timelineLoading = ref(false)
const compositing = ref(false)

async function downloadFinal() {
  try {
    const params = currentEpisodeId.value ? { episode_id: currentEpisodeId.value } : {}
    const r = unwrap(await api.get(`/projects/${projectId}/export`, { params }))
    const url = r?.output_url || currentTimeline.value?.output_url
    if (!url) {
      ElMessage.warning('暂无可下载的成片')
      return
    }
    const a = document.createElement('a')
    a.href = url
    a.download = ''
    document.body.appendChild(a)
    a.click()
    a.remove()
  } catch {
    /* 拦截器已提示 */
  }
}

async function autoTimeline() {
  timelineLoading.value = true
  try {
    await api.post(`/projects/${projectId}/timelines`, {
      episode_id: currentEpisodeId.value
    })
    ElMessage.success('已提交时间线生成')
    await loadAll()
  } finally {
    timelineLoading.value = false
  }
}

/* 合成预检：缺视频的镜头清单 */
const precheck = ref(null)
async function runPrecheck() {
  if (!currentEpisodeId.value) return null
  try {
    const r = unwrap(await api.get(`/episodes/${currentEpisodeId.value}/composite-check`))
    precheck.value = r
    return r
  } catch {
    return null
  }
}

async function composite() {
  const t = currentTimeline.value
  if (!t) return
  const check = await runPrecheck()
  if (check && check.missing && check.missing.length) {
    try {
      await ElMessageBox.confirm(
        `${check.total} 幕中有 ${check.missing.length} 幕缺少镜头视频（第 ${check.missing
          .map((m) => m.seq)
          .join('、')} 幕），时间线将自动跳过它们。是否继续合成？`,
        '合成预检',
        { type: 'warning', confirmButtonText: '继续合成', cancelButtonText: '取消' }
      )
    } catch {
      return
    }
  }
  compositing.value = true
  try {
    await api.post(`/timelines/${t.id}/composite`)
    ElMessage.success('已提交成片合成任务')
  } finally {
    compositing.value = false
  }
}

async function saveTimeline() {
  const t = currentTimeline.value
  if (!t) return
  await api.put(`/timelines/${t.id}`, {
    items: t.items.map((it) => ({
      shot_id: it.shot_id,
      version_id: it.version_id,
      media_url: it.media_url || it.image_url,
      duration_sec: Number(it.duration) || 5,
      subtitle: it.subtitle,
      audio_url: it.audio_url
    }))
  })
}

function moveTl(index, d) {
  const items = currentTimeline.value?.items
  if (!items) return
  const j = index + d
  if (j < 0 || j >= items.length) return
  ;[items[index], items[j]] = [items[j], items[index]]
  saveTimeline().catch(() => {})
}

async function removeTl(index) {
  const items = currentTimeline.value?.items
  if (!items) return
  items.splice(index, 1)
  saveTimeline().catch(() => {})
}

async function delTimeline() {
  const t = currentTimeline.value
  if (!t) return
  try {
    await ElMessageBox.confirm('确定删除当前时间线吗？', '删除时间线', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消'
    })
  } catch {
    return
  }
  await api.delete(`/timelines/${t.id}`)
  ElMessage.success('时间线已删除')
  loadAll()
}

/* ---------------- 生命周期 ---------------- */
onMounted(() => {
  loadAll()
  connectStream()
})

onBeforeUnmount(() => {
  es?.close()
  es = null
  clearTimeout(reconnectTimer)
  clearTimeout(refreshTimer)
  audioEl?.pause()
})
</script>

<template>
  <div class="editor">
    <!-- 顶栏（参考稿 .editor-header） -->
    <header class="editor-header">
      <button
        type="button"
        class="editor-back"
        aria-label="返回项目详情"
        @click="router.push(`/project/${projectId}`)"
      >
        <el-icon :size="18"><ArrowLeft /></el-icon>
      </button>
      <div class="editor-title">{{ project?.title || '创作工作台' }}</div>
      <div class="editor-meta">
        <el-select
          v-if="episodes.length"
          :model-value="currentEpisodeId"
          size="small"
          class="episode-select"
          aria-label="切换剧集"
          @change="switchEpisode"
        >
          <el-option
            v-for="e in episodes"
            :key="e.id"
            :label="`第${e.episode_number}集 · ${e.title}`"
            :value="e.id"
          />
        </el-select>
        <span class="pill num">{{ pipelineProgress }}</span>
        <span v-if="project?.style" class="pill">{{ project.style }}</span>
        <el-tag
          v-if="project"
          :type="U.statusTagType(project.status)"
          size="small"
          effect="light"
          round
        >
          {{ U.statusText(project.status) }}
        </el-tag>
        <span class="pill num">{{ stepIndex + 1 }}/{{ steps.length }}</span>
      </div>
      <div class="editor-actions">
        <el-button
          v-if="failedTasks.length"
          class="btn-sm"
          type="warning"
          plain
          round
          @click="retryAllFailed"
        >
          重试失败({{ failedTasks.length }})
        </el-button>
        <TaskProgress :tasks="taskList" @retry="retryTask" @cancel="cancelTask" />
        <el-badge
          v-if="activeTaskCount"
          :value="activeTaskCount"
          type="primary"
          class="task-badge"
        >
          <el-icon :size="18"><Loading /></el-icon>
        </el-badge>
        <el-button class="btn-sm" type="primary" round @click="smartCta">
          <el-icon><MagicStick /></el-icon>
          &nbsp;{{ ctaLabel }}
        </el-button>
        <el-button
          :icon="Refresh"
          circle
          :loading="refreshing"
          title="刷新数据"
          aria-label="刷新数据"
          @click="loadAll"
        />
      </div>
    </header>

    <div class="editor-body">
      <!-- 左侧 6 步流水线（参考稿 .editor-sidebar） -->
      <aside class="editor-sidebar" :class="{ hidden: !sidebarOpen }">
        <div class="sidebar-section">
          <div class="sidebar-label">
            <span class="live-dot" aria-hidden="true"></span>创作流水线
          </div>
          <button
            v-for="(s, i) in steps"
            :key="s.key"
            type="button"
            class="sidebar-item"
            :class="{
              on: activeTab === s.key,
              done: stepState(s.key) === 'done',
              doing: stepState(s.key) === 'active'
            }"
            :aria-current="activeTab === s.key ? 'step' : undefined"
            @click="pickStep(s.key)"
          >
            <span class="icon" aria-hidden="true">
              <el-icon v-if="stepState(s.key) === 'done'" :size="13"><Check /></el-icon>
              <span v-else-if="stepState(s.key) === 'active'" class="pipe-pulse" aria-hidden="true"></span>
              <template v-else>{{ s.icon }}</template>
            </span>
            <span class="s-text">
              <span class="s-name">
                {{ s.label }}
                <span v-if="stepCount(s.key)" class="s-count mono">{{ stepCount(s.key) }}</span>
              </span>
              <span class="s-desc">
                <template v-if="stepState(s.key) === 'active'">进行中 · </template>{{ s.desc }}
              </span>
            </span>
          </button>
        </div>
      </aside>

      <!-- <1024px 浮动抽屉开关（参考稿 .editor-toggle） -->
      <button
        type="button"
        class="editor-toggle"
        aria-label="切换步骤侧栏"
        :aria-expanded="sidebarOpen ? 'true' : 'false'"
        @click="sidebarOpen = !sidebarOpen"
      >
        <el-icon :size="20"><Menu /></el-icon>
      </button>

      <!-- 右侧主区（参考稿 .editor-main / .editor-panel） -->
      <main v-loading="refreshing" class="editor-main">
        <Transition name="sec">
          <div class="editor-panel" :key="activeTab">
            <!-- 01 剧本 -->
            <section v-if="activeTab === 'script'">
              <div class="step-header">
                <div class="step-badge">
                  <span class="step-num">{{ stepNo }}</span>
                  <span class="step-name">{{ stepName }}</span>
                  <span class="step-sub">共 {{ storyboards.length }} 个分镜</span>
                </div>
                <div class="step-ops">
                  <el-button
                    class="btn-sm"
                    type="primary"
                    :loading="generatingScript"
                    @click="generateScript"
                  >
                    <el-icon><MagicStick /></el-icon>
                    &nbsp;AI 生成分镜脚本
                  </el-button>
                  <el-button
                    class="btn-sm"
                    :loading="extractingChars"
                    :disabled="!storyboards.length"
                    @click="extractChars"
                  >
                    <el-icon><Refresh /></el-icon>
                    &nbsp;重提角色
                  </el-button>
                  <el-button class="btn-sm" @click="addSb">
                    <el-icon><Plus /></el-icon>
                    &nbsp;新增分镜
                  </el-button>
                </div>
              </div>
              <div class="script-text-card">
                <div class="st-head">
                  <span class="st-label">剧本梗概（可编辑，不影响分镜）</span>
                  <span class="st-count mono">{{ scriptText.length }} 字</span>
                  <el-button
                    class="btn-sm"
                    type="primary"
                    plain
                    :disabled="!scriptDirty || !currentEpisodeId"
                    :loading="scriptSaving"
                    @click="saveScriptText"
                  >
                    保存
                  </el-button>
                </div>
                <el-input
                  v-model="scriptText"
                  type="textarea"
                  :rows="4"
                  placeholder="本集故事梗概 / 剧情走向，AI 生成剧本时参考；改完点保存即可，无需重新生成"
                  @input="onScriptInput"
                />
              </div>
              <div v-if="storyboards.length" class="table-card">
                <el-table :data="storyboards" row-key="id">
                  <el-table-column label="序号" width="60" align="center">
                    <template #default="{ $index }">{{ $index + 1 }}</template>
                  </el-table-column>
                  <el-table-column prop="shot_type" label="景别" width="90" />
                  <el-table-column
                    prop="description"
                    label="画面描述"
                    min-width="220"
                    show-overflow-tooltip
                  />
                  <el-table-column prop="dialogue" label="台词" min-width="180" show-overflow-tooltip />
                  <el-table-column prop="emotion" label="情绪" width="90" />
                  <el-table-column label="时长" width="80">
                    <template #default="{ row }">{{ U.fmtDuration(row.duration) || '-' }}</template>
                  </el-table-column>
                  <el-table-column label="操作" width="220" fixed="right">
                    <template #default="{ row, $index }">
                      <el-button link type="primary" size="small" @click="openEditSb($index)">
                        编辑
                      </el-button>
                      <el-button link size="small" :disabled="$index === 0" @click="moveSb($index, -1)">
                        上移
                      </el-button>
                      <el-button
                        link
                        size="small"
                        :disabled="$index === storyboards.length - 1"
                        @click="moveSb($index, 1)"
                      >
                        下移
                      </el-button>
                      <el-button link size="small" type="danger" @click="delSb(row)">删除</el-button>
                    </template>
                  </el-table-column>
                </el-table>
              </div>
              <div v-else class="g-empty">
                <el-empty description="还没有分镜脚本，点击「AI 生成分镜脚本」开始" :image-size="90" />
              </div>
            </section>

            <!-- 02 角色 -->
            <section v-else-if="activeTab === 'character'">
              <div class="step-header">
                <div class="step-badge">
                  <span class="step-num">{{ stepNo }}</span>
                  <span class="step-name">{{ stepName }}</span>
                  <span class="step-sub">{{ characters.length }} 个角色</span>
                </div>
                <div class="step-ops">
                  <el-button class="btn-sm" type="primary" @click="addChar">
                    <el-icon><Plus /></el-icon>
                    &nbsp;新增角色
                  </el-button>
                </div>
              </div>
              <div v-if="characters.length" class="char-grid">
                <div v-for="c in characters" :key="c.id" class="char-card">
                  <div
                    class="char-visual"
                    :style="U.imgUrlOf(c) ? null : { background: U.gradVar(c.id) }"
                  >
                    <img
                      v-if="U.imgUrlOf(c)"
                      :src="U.imgUrlOf(c)"
                      :alt="`${c.name || '未命名角色'} 参考图`"
                      loading="lazy"
                      width="640"
                      height="640"
                    />
                    <span v-else class="letter">{{ U.firstChar(c.name) }}</span>
                  </div>
                  <div class="char-info">
                    <h4>{{ c.name || '未命名角色' }}</h4>
                    <p>{{ c.description || '暂无描述' }}</p>
                    <div class="char-tags">
                      <el-tag size="small" effect="plain" round>
                        {{ U.voiceLabel(c.voice) }}
                      </el-tag>
                    </div>
                    <div class="char-actions">
                      <el-button class="btn-sm" @click="openEditChar(c)">编辑</el-button>
                      <el-button
                        class="btn-sm"
                        type="primary"
                        :loading="refLoading[c.id]"
                        @click="genRef(c)"
                      >
                        生成参考图
                      </el-button>
                      <el-button class="btn-sm" text type="primary" @click="audition(c)">
                        试听
                      </el-button>
                      <el-button class="btn-sm" text type="danger" @click="delChar(c)">删除</el-button>
                    </div>
                  </div>
                </div>
              </div>
              <div v-else class="g-empty">
                <el-empty description="剧本生成后将自动提取角色设定" :image-size="90" />
              </div>
            </section>

            <!-- 03 画面分镜 -->
            <section v-else-if="activeTab === 'board'">
              <div class="step-header">
                <div class="step-badge">
                  <span class="step-num">{{ stepNo }}</span>
                  <span class="step-name">{{ stepName }}</span>
                  <span class="step-sub">{{ storyboards.length }} 幕 · 抽卡选定后可生成视频</span>
                </div>
                <div v-if="storyboards.length" class="step-ops">
                  <el-button class="btn-sm" :type="batchMode ? 'warning' : 'default'" plain round @click="toggleBatchMode">
                    <el-icon><Select /></el-icon>
                    &nbsp;{{ batchMode ? '退出批量' : '批量模式' }}
                  </el-button>
                  <template v-if="batchMode">
                    <el-button class="btn-sm" text @click="selectAllBatch">全选</el-button>
                    <span class="batch-count mono">已选 {{ batchSel.size }}</span>
                    <el-button class="btn-sm" type="primary" :disabled="!batchSel.size" @click="openBatchImages">
                      批量出图
                    </el-button>
                    <el-button class="btn-sm" type="primary" plain :disabled="!batchSel.size" @click="openBatchVideos">
                      批量出视频
                    </el-button>
                  </template>
                </div>
              </div>
              <div v-if="storyboards.length" class="shot-grid">
                <div
                  v-for="(sb, i) in storyboards"
                  :key="sb.id || i"
                  class="shot-card"
                  :class="{ picked: batchSel.has(sb.id) }"
                >
                  <div class="shot-visual">
                    <label v-if="batchMode" class="shot-check" @click.stop>
                      <input
                        type="checkbox"
                        :checked="batchSel.has(sb.id)"
                        :aria-label="`选择第 ${i + 1} 幕`"
                        @change="toggleBatchSel(sb.id)"
                      />
                    </label>
                    <el-image
                      v-if="U.thumbOf(sb)"
                      class="shot-img"
                      :src="U.thumbOf(sb)"
                      :alt="`第 ${i + 1} 镜缩略图`"
                      fit="cover"
                      :preview-src-list="U.versionsOf(sb).map(U.imgUrlOf).filter(Boolean)"
                      :initial-index="0"
                      preview-teleported
                      hide-on-click-modal
                    />
                    <div v-else class="shot-grad" :style="{ background: U.gradVar(sb.id ?? i) }">
                      {{ i + 1 }}
                    </div>
                    <span v-if="U.hasSelected(sb)" class="sel" aria-label="已选定画面">✓</span>
                    <el-tag
                      v-if="sb.shot_type || U.fmtDuration(sb.duration)"
                      class="qc"
                      type="primary"
                      size="small"
                      effect="light"
                      round
                    >
                      {{ sb.shot_type || U.fmtDuration(sb.duration) }}
                    </el-tag>
                  </div>
                  <div class="shot-info">
                    <div class="name">
                      第 {{ i + 1 }} 幕
                      <span v-if="U.fmtDuration(sb.duration)" class="n-meta mono num">
                        {{ U.fmtDuration(sb.duration) }}
                      </span>
                    </div>
                    <div class="prompt">{{ sb.description || '（暂无画面描述）' }}</div>
                    <div class="s-dialogue" :class="{ none: !sb.dialogue }">
                      {{ sb.dialogue || '（无台词）' }}
                    </div>
                  </div>
                  <div v-if="U.versionsOf(sb).length || U.videoUrlOf(sb)" class="shot-versions">
                    <div v-for="(v, vi) in U.versionsOf(sb)" :key="v.id || vi" class="ver-cell">
                      <el-image
                        class="shot-ver"
                        :class="{ on: isSelected(sb, v) }"
                        :src="U.imgUrlOf(v)"
                        :alt="`第 ${i + 1} 镜候选画面 ${vi + 1}`"
                        fit="cover"
                        :preview-src-list="U.versionsOf(sb).map(U.imgUrlOf).filter(Boolean)"
                        :initial-index="vi"
                        preview-teleported
                        hide-on-click-modal
                      />
                      <div class="ver-ops">
                        <el-tag v-if="isSelected(sb, v)" type="success" size="small" effect="dark" round>
                          已选
                        </el-tag>
                        <el-button v-else link type="primary" size="small" @click="selectVersion(sb, v)">
                          选定
                        </el-button>
                        <el-button link type="primary" size="small" @click="openEditVersion(v)">
                          编辑
                        </el-button>
                        <el-button link type="danger" size="small" @click="delVersion(sb, v)">
                          删除
                        </el-button>
                      </div>
                    </div>
                    <div v-if="U.videoUrlOf(sb)" class="ver-video">
                      <video :src="U.videoUrlOf(sb)" controls preload="metadata" />
                      <span class="v-label">镜头视频</span>
                    </div>
                  </div>
                  <div class="shot-actions">
                    <el-button class="btn-sm shot-gen-btn" type="primary" @click="openGenImage(sb)">
                      <el-icon><Picture /></el-icon>
                      &nbsp;生成画面
                    </el-button>
                    <el-button
                      v-if="U.versionsOf(sb).length"
                      class="btn-sm"
                      @click="regenImage(sb)"
                    >
                      重新生成
                    </el-button>
                    <el-button
                      v-if="U.hasSelected(sb) && !U.videoUrlOf(sb)"
                      class="btn-sm"
                      type="primary"
                      plain
                      @click="genVideo(sb)"
                    >
                      <el-icon><VideoCamera /></el-icon>
                      &nbsp;生成视频
                    </el-button>
                  </div>
                </div>
              </div>
              <div v-else class="g-empty">
                <el-empty description="先生成剧本，再来制作画面" :image-size="90" />
              </div>
            </section>

            <!-- 05 配音 -->
            <section v-else-if="activeTab === 'voice'">
              <div class="step-header">
                <div class="step-badge">
                  <span class="step-num">{{ stepNo }}</span>
                  <span class="step-name">{{ stepName }}</span>
                  <span class="step-sub">{{ storyboards.length }} 幕台词</span>
                </div>
              </div>
              <div v-if="storyboards.length" class="dub-list">
                <div v-for="(sb, i) in storyboards" :key="sb.id || i" class="dub-row">
                  <div
                    class="dub-avatar"
                    :style="{ background: U.gradVar(charOf(sb)?.id ?? sb.id ?? i) }"
                    aria-hidden="true"
                  >
                    {{ U.firstChar(sb.character_name || sb.dialogue) }}
                  </div>
                  <div class="dub-meta">
                    <b>{{ sb.character_name || `第 ${i + 1} 幕` }}</b>
                    <span :class="{ none: !sb.dialogue }">{{ sb.dialogue || '（无台词）' }}</span>
                  </div>
                  <div class="dub-tags">
                    <el-tag v-if="sb.emotion" size="small" effect="plain" round>
                      {{ sb.emotion }}
                    </el-tag>
                    <el-tag size="small" type="info" effect="plain" round>
                      {{ U.voiceLabel(charOf(sb)?.voice) }}
                    </el-tag>
                  </div>
                  <div v-if="U.audioOfSb(assets, sb.id)" class="dub-audio">
                    <audio :src="U.audioOfSb(assets, sb.id)" controls preload="none" />
                  </div>
                  <el-button
                    v-else
                    class="btn-sm"
                    type="primary"
                    plain
                    :disabled="!sb.dialogue"
                    @click="genVoice(sb)"
                  >
                    <el-icon><Microphone /></el-icon>
                    &nbsp;生成配音
                  </el-button>
                </div>
              </div>
              <div v-else class="g-empty">
                <el-empty description="先生成剧本，再为台词配音" :image-size="90" />
              </div>
            </section>

            <!-- 06 成片 -->
            <section v-else-if="activeTab === 'final'">
              <div class="step-header">
                <div class="step-badge">
                  <span class="step-num">{{ stepNo }}</span>
                  <span class="step-name">{{ stepName }}</span>
                  <span class="step-sub">
                    {{ currentTimeline ? `时间线 ${currentTimeline.items.length} 项` : '未创建时间线' }}
                  </span>
                </div>
                <div class="step-ops">
                  <el-button class="btn-sm" :loading="timelineLoading" @click="autoTimeline">
                    <el-icon><List /></el-icon>
                    &nbsp;自动生成时间线
                  </el-button>
                  <el-button
                    class="btn-sm"
                    type="primary"
                    :disabled="!currentTimeline || !currentTimeline.items.length"
                    :loading="compositing"
                    @click="composite"
                  >
                    <el-icon><Film /></el-icon>
                    &nbsp;合成成片
                  </el-button>
                  <el-button
                    class="btn-sm"
                    type="danger"
                    plain
                    :disabled="!currentTimeline"
                    @click="delTimeline"
                  >
                    删除时间线
                  </el-button>
                </div>
              </div>

              <template v-if="currentTimeline">
                <div v-if="currentTimeline.output_url" class="output">
                  <div class="video-frame">
                    <video :src="currentTimeline.output_url" controls preload="metadata" class="final-video" />
                  </div>
                  <div class="out-ops">
                    <el-button class="btn-lg" type="primary" @click="downloadFinal">
                      <el-icon><Download /></el-icon>
                      &nbsp;下载成片
                    </el-button>
                  </div>
                </div>
                <div class="timeline-panel">
                  <div class="tl-label">镜头序列</div>
                  <el-table :data="currentTimeline.items" row-key="id">
                    <el-table-column label="序号" width="60" align="center">
                      <template #default="{ $index }">{{ $index + 1 }}</template>
                    </el-table-column>
                    <el-table-column label="缩略图" width="120">
                      <template #default="{ row, $index }">
                        <div class="tl-thumb">
                          <img
                            v-if="row.media_url"
                            :src="row.media_url"
                            :alt="`时间线第 ${$index + 1} 项缩略图`"
                            loading="lazy"
                            width="176"
                            height="99"
                          />
                          <div v-else class="tl-grad">
                            <el-icon><Picture /></el-icon>
                          </div>
                        </div>
                      </template>
                    </el-table-column>
                    <el-table-column label="时长" width="80">
                      <template #default="{ row }">{{ U.fmtDuration(row.duration) || '-' }}</template>
                    </el-table-column>
                    <el-table-column prop="subtitle" label="字幕" min-width="200" show-overflow-tooltip />
                    <el-table-column label="音频" width="70" align="center">
                      <template #default="{ row }">
                        <el-icon v-if="row.audio_url" style="color: var(--success)"><Check /></el-icon>
                        <span v-else class="text-secondary">—</span>
                      </template>
                    </el-table-column>
                    <el-table-column label="操作" width="170" fixed="right">
                      <template #default="{ $index }">
                        <el-button link size="small" :disabled="$index === 0" @click="moveTl($index, -1)">
                          上移
                        </el-button>
                        <el-button
                          link
                          size="small"
                          :disabled="$index === currentTimeline.items.length - 1"
                          @click="moveTl($index, 1)"
                        >
                          下移
                        </el-button>
                        <el-button link size="small" type="danger" @click="removeTl($index)">
                          删除
                        </el-button>
                      </template>
                    </el-table-column>
                  </el-table>
                </div>
              </template>
              <div v-else class="g-empty">
                <el-empty description="先「自动生成时间线」，再「合成成片」" :image-size="90" />
              </div>
            </section>
          </div>
        </Transition>
      </main>
    </div>

    <!-- 分镜编辑弹窗 -->
    <el-dialog v-model="sbEditVisible" :title="sbForm.id ? '编辑分镜' : '新增分镜'" width="520px">
      <el-form label-position="top">
        <div class="form-grid">
          <el-form-item label="景别">
            <el-select v-model="sbForm.shot_type" allow-create filterable style="width: 100%">
              <el-option v-for="t in U.SHOT_TYPES" :key="t" :label="t" :value="t" />
            </el-select>
          </el-form-item>
          <el-form-item label="时长（秒）">
            <el-input-number v-model="sbForm.duration" :min="1" :max="30" :step="0.5" />
          </el-form-item>
          <el-form-item label="情绪">
            <el-input v-model="sbForm.emotion" placeholder="如：紧张 / 温柔 / 悲伤" />
          </el-form-item>
        </div>
        <el-form-item label="画面描述">
          <el-input v-model="sbForm.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="台词">
          <el-input v-model="sbForm.dialogue" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="sbEditVisible = false">取消</el-button>
        <el-button type="primary" @click="saveSb">保存</el-button>
      </template>
    </el-dialog>

    <!-- 角色编辑弹窗 -->
    <el-dialog
      v-model="charEditVisible"
      :title="charForm.id ? '编辑角色' : '新增角色'"
      width="520px"
    >
      <el-form label-position="top">
        <div class="form-grid">
          <el-form-item label="名称">
            <el-input v-model="charForm.name" maxlength="20" />
          </el-form-item>
          <el-form-item label="音色">
            <el-select v-model="charForm.voice" style="width: 100%">
              <el-option v-for="v in U.VOICES" :key="v.value" :label="v.label" :value="v.value" />
            </el-select>
          </el-form-item>
        </div>
        <el-form-item label="描述">
          <el-input v-model="charForm.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="提示词模板">
          <el-input
            v-model="charForm.prompt_template"
            type="textarea"
            :rows="3"
            placeholder="用于生成角色参考图的提示词模板"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="charEditVisible = false">取消</el-button>
        <el-button type="primary" @click="saveChar">保存</el-button>
      </template>
    </el-dialog>

    <!-- 生成画面弹窗 -->
    <el-dialog v-model="genVisible" title="生成画面" width="380px">
      <p class="gen-tip">将为该分镜生成候选画面（抽卡后选定最佳版本）</p>
      <div class="gen-count">
        <span>生成数量</span>
        <el-input-number v-model="genForm.count" :min="1" :max="4" />
      </div>
      <template #footer>
        <el-button @click="genVisible = false">取消</el-button>
        <el-button type="primary" :loading="generating" @click="confirmGen">
          开始生成
        </el-button>
      </template>
    </el-dialog>

    <!-- 批量出图确认 -->
    <el-dialog v-model="batchImageVisible" title="批量生成画面" width="420px">
      <p class="gen-tip">
        将为选中的 <b>{{ batchSel.size }}</b> 个分镜各生成候选画面，共
        <b>{{ batchSel.size * batchImageCount }}</b> 张图。
      </p>
      <div class="gen-count">
        <span>每个分镜版本数</span>
        <el-input-number v-model="batchImageCount" :min="1" :max="4" />
      </div>
      <div class="batch-confirm-meta mono">
        模型：agnes-image-2.1-flash · 比例：{{ project?.aspect_ratio || '9:16' }} ·
        预计耗时 ≈ {{ Math.ceil(batchSel.size * batchImageCount * 0.5) }} 分钟
      </div>
      <template #footer>
        <el-button @click="batchImageVisible = false">取消</el-button>
        <el-button type="primary" :loading="batchSubmitting" @click="confirmBatchImages">
          开始生成
        </el-button>
      </template>
    </el-dialog>

    <!-- 批量出视频确认 -->
    <el-dialog v-model="batchVideoVisible" title="批量生成视频" width="420px">
      <p class="gen-tip">
        将为选中的 <b>{{ batchSel.size }}</b> 个分镜生成镜头视频，
        已有视频或无选定画面的会被自动跳过。
      </p>
      <div class="gen-count">
        <span>单镜时长（秒）</span>
        <el-select v-model="batchVideoSeconds" style="width: 110px">
          <el-option v-for="s in ['5', '10']" :key="s" :label="`${s}s`" :value="s" />
        </el-select>
      </div>
      <div class="batch-confirm-meta mono">
        模型：agnes-video-2.5-flash · 预计耗时 ≈
        {{ Math.max(10, Math.ceil(batchSel.size * 2.5)) }} 分钟（单任务轮询上限 10 分钟）
      </div>
      <template #footer>
        <el-button @click="batchVideoVisible = false">取消</el-button>
        <el-button type="primary" :loading="batchSubmitting" @click="confirmBatchVideos">
          开始生成
        </el-button>
      </template>
    </el-dialog>

    <!-- 版本编辑弹窗 -->
    <el-dialog v-model="versionEditVisible" title="编辑画面版本" width="480px">
      <el-form label-position="top">
        <el-form-item label="提示词">
          <el-input v-model="versionForm.prompt" type="textarea" :rows="4" />
        </el-form-item>
        <el-form-item label="Seed（留空保持不变）">
          <el-input-number v-model="versionForm.seed" :min="0" :max="999" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="versionEditVisible = false">取消</el-button>
        <el-button type="primary" @click="saveVersion">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
/* ============ 根容器（参考稿 .editor：全屏固定工作台） ============ */
.editor {
  position: fixed;
  inset: 0;
  z-index: 1;
  display: flex;
  flex-direction: column;
  background: var(--bg);
  animation: fadeUp 0.3s var(--ease-out);
}

/* ============ 顶栏（参考稿 .editor-header） ============ */
.editor-header {
  height: 56px;
  display: flex;
  align-items: center;
  gap: var(--space-4);
  padding: 0 20px;
  background: var(--glass-bg);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
  backdrop-filter: blur(20px) saturate(180%);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.editor-back {
  appearance: none;
  -webkit-appearance: none;
  width: 36px;
  height: 36px;
  border-radius: var(--radius);
  border: none;
  background: transparent;
  display: grid;
  place-items: center;
  color: var(--text-secondary);
  cursor: pointer;
  flex-shrink: 0;
  transition: background-color var(--dur-base) var(--ease-out),
    color var(--dur-base) var(--ease-out);
}

.editor-back:hover {
  background: var(--surface-hover);
  color: var(--text-primary);
}

.editor-title {
  font-size: var(--text-base);
  font-weight: 700;
  letter-spacing: -0.3px;
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--text-primary);
}

.editor-meta {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-shrink: 0;
}

.editor-meta .pill {
  font-size: 11px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: var(--radius-pill);
  background: var(--surface-hover);
  color: var(--text-secondary);
  border: 1px solid var(--border);
  white-space: nowrap;
}

.editor-meta .episode-select {
  width: 168px;
}

.editor-meta .episode-select :deep(.el-select__wrapper) {
  border-radius: var(--radius-pill);
  background: var(--surface-hover);
  box-shadow: 0 0 0 1px var(--border) inset;
  font-size: 12px;
  font-weight: 600;
}

.editor-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-shrink: 0;
}

/* ============ 主体 ============ */
.editor-body {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  position: relative;
}

/* ============ 侧栏（参考稿 .editor-sidebar） ============ */
.editor-sidebar {
  width: 260px;
  flex-shrink: 0;
  background: var(--surface);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  padding: var(--space-4);
  gap: var(--space-1);
  transition: transform var(--dur-slow) var(--ease-out);
}

.sidebar-section {
  margin-bottom: var(--space-2);
}

.sidebar-label {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 10px 12px;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-tertiary);
}

.live-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--primary);
  display: inline-block;
  flex-shrink: 0;
  animation: pulse 2s infinite;
}

/* 步骤项（参考稿 .sidebar-item） */
.sidebar-item {
  appearance: none;
  -webkit-appearance: none;
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 10px 12px;
  border-radius: var(--radius);
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-family: inherit;
  font-size: 13.5px;
  font-weight: 600;
  cursor: pointer;
  text-align: left;
  transition: background-color var(--dur-fast) var(--ease-out),
    color var(--dur-fast) var(--ease-out);
}

.sidebar-item:hover {
  background: var(--surface-hover);
  color: var(--text-primary);
}

.sidebar-item.on {
  background: var(--primary-soft);
  color: var(--accent);
}

.sidebar-item .icon {
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
  background: var(--surface-hover);
  display: grid;
  place-items: center;
  font-size: 13px;
  flex-shrink: 0;
  transition: background-color var(--dur-fast) var(--ease-out),
    color var(--dur-fast) var(--ease-out);
}

.sidebar-item.done .icon {
  background: var(--success-soft);
  color: var(--success);
}

.sidebar-item.on .icon {
  background: var(--primary);
  color: #fff;
}

.s-text {
  display: flex;
  flex-direction: column;
  line-height: 1.3;
  min-width: 0;
  flex: 1;
}

.s-name {
  font-weight: 600;
}

.s-desc {
  font-size: 11px;
  color: var(--text-tertiary);
  font-weight: 400;
}

/* 三态流水线：进行中 */
.sidebar-item.doing .icon {
  background: var(--warning-soft);
  color: var(--warning);
}

.pipe-pulse {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--warning);
  animation: pipePulse 1.2s var(--ease-out) infinite;
}

@keyframes pipePulse {
  0% {
    box-shadow: 0 0 0 0 rgba(255, 149, 0, 0.5);
  }
  70% {
    box-shadow: 0 0 0 7px rgba(255, 149, 0, 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(255, 149, 0, 0);
  }
}

.s-count {
  margin-left: 6px;
  font-size: 10.5px;
  font-weight: 700;
  color: var(--accent);
  background: var(--primary-soft);
  padding: 1px 6px;
  border-radius: var(--radius-pill);
}

/* 剧本梗概编辑卡片 */
.script-text-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 16px;
  margin-bottom: var(--space-4);
}

.st-head {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: 10px;
}

.st-label {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
  flex: 1;
}

.st-count {
  font-size: 12px;
  color: var(--text-tertiary);
}

/* 批量模式 */
.batch-count {
  font-size: 12px;
  color: var(--text-secondary);
  padding: 0 4px;
}

.shot-card.picked {
  border-color: var(--primary);
  box-shadow: 0 0 0 2px var(--primary-soft);
}

.shot-check {
  position: absolute;
  top: 8px;
  left: 8px;
  z-index: 3;
  width: 24px;
  height: 24px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.55);
  backdrop-filter: blur(6px);
  cursor: pointer;
}

.shot-check input {
  width: 15px;
  height: 15px;
  accent-color: var(--primary);
  cursor: pointer;
}

.batch-confirm-meta {
  margin-top: 12px;
  font-size: 12px;
  color: var(--text-tertiary);
  background: var(--surface-hover);
  border-radius: var(--radius);
  padding: 8px 12px;
}

.task-badge {
  margin-right: 4px;
  display: inline-flex;
  align-items: center;
  color: var(--text-secondary);
}

/* 浮动抽屉开关（参考稿 .editor-toggle） */
.editor-toggle {
  display: none;
}

/* ============ 主区（参考稿 .editor-main / .editor-panel） ============ */
.editor-main {
  position: relative;
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  padding: 28px 32px 48px;
}

.editor-panel {
  max-width: 900px;
  margin: 0 auto;
}

/* section 切换：对齐 fadeUp 参数（opacity + translateY(12px) .3s） */
.sec-enter-active,
.sec-leave-active {
  transition: opacity var(--dur-slow) var(--ease-out),
    transform var(--dur-slow) var(--ease-out);
}
.sec-leave-active {
  position: absolute;
  top: 28px;
  left: 32px;
  right: 32px;
  max-width: 900px;
  margin: 0 auto;
}
.sec-enter-from,
.sec-leave-to {
  opacity: 0;
  transform: translateY(12px);
}

/* ============ 步骤头（参考稿 .step-header） ============ */
.step-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-6);
  flex-wrap: wrap;
  gap: 12px;
}

.step-badge {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  flex-wrap: wrap;
}

.step-num {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  font-weight: 700;
  color: var(--accent);
  background: var(--primary-soft);
  padding: 4px 10px;
  border-radius: var(--radius-sm);
}

.step-name {
  font-size: var(--text-lg);
  font-weight: 700;
  color: var(--text-primary);
}

.step-sub {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.step-ops {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
}

/* .btn-sm / .btn-lg 形态（参考稿按钮体系） */
.btn-sm {
  height: 32px;
  padding: 0 14px;
  font-size: 13px;
}

.btn-lg {
  height: 44px;
  padding: 0 24px;
  font-size: 15px;
}

/* ============ 表格容器 ============ */
.table-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

/* ============ 角色（参考稿 .char-grid / .char-card） ============ */
.char-grid {
  display: grid;
  grid-template-columns: repeat(1, 1fr);
  gap: var(--space-4);
}

.char-card {
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  background: var(--surface);
  transition: box-shadow 0.3s var(--ease-out),
    border-color 0.3s var(--ease-out);
}

.char-card:hover {
  box-shadow: var(--shadow);
  border-color: var(--border-strong);
}

.char-visual {
  aspect-ratio: 1;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.char-visual img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.char-visual .letter {
  font-size: 48px;
  font-weight: 800;
  color: #fff;
  text-shadow: 0 2px 12px rgba(0, 0, 0, 0.4);
}

.char-info {
  padding: var(--space-4);
}

.char-info h4 {
  font-size: var(--text-base);
  font-weight: 700;
  margin-bottom: var(--space-1);
  color: var(--text-primary);
}

.char-info p {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 12px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 2.8em;
}

.char-tags {
  margin-bottom: 12px;
}

.char-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
}

/* ============ 分镜 / 画面（参考稿 .shot-grid / .shot-card） ============ */
.shot-grid {
  display: grid;
  grid-template-columns: repeat(1, 1fr);
  gap: 20px;
}

.shot-card {
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  background: var(--surface);
  transition: box-shadow 0.3s var(--ease-out),
    border-color 0.3s var(--ease-out);
}

.shot-card:hover {
  box-shadow: var(--shadow);
  border-color: var(--border-strong);
}

.shot-visual {
  aspect-ratio: 16 / 9;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background: var(--thumb-bg);
}

.shot-visual :deep(.shot-img) {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  display: block;
  cursor: zoom-in;
}

.shot-visual :deep(.shot-img .el-image__inner) {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.shot-grad {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-xl);
  font-weight: 700;
  color: #fff;
  text-shadow: 0 2px 12px rgba(0, 0, 0, 0.4);
}

/* 左上已选定 ✓ 徽标 */
.shot-visual .sel {
  position: absolute;
  top: 10px;
  left: 10px;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: var(--primary);
  color: #fff;
  display: grid;
  place-items: center;
  font-size: 12px;
  font-weight: 800;
  box-shadow: var(--shadow-sm);
}

/* 右上信息 pill */
.shot-visual .qc {
  position: absolute;
  top: 10px;
  right: 10px;
}

.shot-info {
  padding: 14px 16px;
}

.shot-info .name {
  font-size: 14px;
  font-weight: 700;
  margin-bottom: var(--space-1);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.shot-info .n-meta {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-tertiary);
}

.shot-info .prompt {
  font-size: 12.5px;
  color: var(--text-secondary);
  line-height: 1.5;
  margin-bottom: var(--space-2);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.shot-info .s-dialogue {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.shot-info .s-dialogue.none {
  color: var(--text-tertiary);
  font-weight: 400;
}

/* 版本缩略条 */
.shot-versions {
  display: flex;
  gap: var(--space-2);
  padding: 0 16px 14px;
  flex-wrap: wrap;
  align-items: flex-start;
}

.ver-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  min-width: 36px;
}

.ver-cell :deep(.shot-ver) {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-sm);
  border: 2px solid transparent;
  overflow: hidden;
  cursor: pointer;
  display: block;
  background: var(--surface-raised);
  transition: border-color var(--dur-base) var(--ease-out),
    box-shadow var(--dur-base) var(--ease-out),
    transform var(--dur-base) var(--ease-out),
    opacity var(--dur-base) var(--ease-out);
}

.ver-cell :deep(.shot-ver:hover) {
  transform: scale(1.08);
  opacity: 0.9;
}

.ver-cell :deep(.shot-ver.on) {
  border-color: var(--primary);
  box-shadow: 0 0 0 2px var(--primary-ring);
}

.ver-ops {
  display: flex;
  align-items: center;
  gap: 2px;
  white-space: nowrap;
}

.ver-ops :deep(.el-button.is-link) {
  height: auto;
  padding: 0 2px;
  font-size: 11px;
}

.ver-ops :deep(.el-tag) {
  height: 18px;
  padding: 0 6px;
  font-size: 10px;
}

.ver-video {
  width: 200px;
  min-width: 160px;
}

.ver-video video {
  width: 100%;
  aspect-ratio: 16 / 9;
  border-radius: var(--radius-sm);
  background: var(--bg);
  display: block;
}

.v-label {
  display: block;
  margin-top: 2px;
  text-align: center;
  font-size: 11px;
  color: var(--text-tertiary);
}

/* 卡片底部操作（参考稿 .shot-actions） */
.shot-actions {
  display: flex;
  gap: var(--space-2);
  padding: 0 16px 16px;
  flex-wrap: wrap;
}

.shot-gen-btn {
  flex: 1;
  min-width: 120px;
}

/* ============ 配音（参考稿 .dub-row） ============ */
.dub-list {
  display: flex;
  flex-direction: column;
}

.dub-row {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  margin-bottom: 12px;
  transition: box-shadow var(--dur-slow) var(--ease-out),
    border-color var(--dur-slow) var(--ease-out);
}

.dub-row:hover {
  box-shadow: var(--shadow);
  border-color: var(--border-strong);
}

.dub-avatar {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  color: #fff;
  font-size: var(--text-base);
  font-weight: 700;
  flex-shrink: 0;
  text-shadow: 0 1px 6px rgba(0, 0, 0, 0.3);
}

.dub-meta {
  flex: 1;
  min-width: 0;
}

.dub-meta b {
  font-size: var(--text-base);
  font-weight: 700;
  display: block;
  margin-bottom: 2px;
  color: var(--text-primary);
}

.dub-meta span {
  font-size: 13px;
  color: var(--text-secondary);
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dub-meta span.none {
  color: var(--text-tertiary);
}

.dub-tags {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-shrink: 0;
}

.dub-audio {
  flex-shrink: 0;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface-raised);
}

.dub-audio audio {
  display: block;
  height: 34px;
  max-width: 300px;
}

/* ============ 成片（参考稿 .timeline-panel） ============ */
.output {
  margin-bottom: var(--space-5);
  text-align: center;
}

.video-frame {
  display: inline-block;
  width: 100%;
  max-width: 720px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  background: var(--bg);
  box-shadow: var(--shadow-sm);
}

.final-video {
  width: 100%;
  aspect-ratio: 16 / 9;
  display: block;
  background: var(--bg);
}

.out-ops {
  margin-top: var(--space-3);
}

.timeline-panel {
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  padding: 20px;
  overflow-x: auto;
}

.tl-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-tertiary);
  margin: var(--space-1) 0;
}

.timeline-panel :deep(.el-table) {
  background: transparent;
}

.tl-thumb {
  width: 88px;
  aspect-ratio: 16 / 9;
  border-radius: var(--radius-sm);
  overflow: hidden;
  background: var(--thumb-bg);
}

.tl-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.tl-grad {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-tertiary);
}

/* ============ 弹窗内小件 ============ */
.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 var(--space-4);
}

.gen-tip {
  margin: 0 0 var(--space-4);
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.gen-count {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

/* ============ 响应式：<1024px 侧栏抽屉（参考稿 .editor-toggle） ============ */
@media (max-width: 1023px) {
  .editor-sidebar {
    position: absolute;
    top: 0;
    bottom: 0;
    left: 0;
    z-index: 100;
    box-shadow: var(--shadow-xl);
    transform: translateX(0);
  }

  .editor-sidebar.hidden {
    transform: translateX(-100%);
  }

  .editor-toggle {
    display: flex;
    position: fixed;
    bottom: 24px;
    left: 24px;
    z-index: 101;
    width: 48px;
    height: 48px;
    border-radius: 50%;
    background: var(--primary);
    color: #fff;
    border: none;
    align-items: center;
    justify-content: center;
    box-shadow: var(--shadow-lg);
    cursor: pointer;
    transition: background-color var(--dur-base) var(--ease-out),
      transform var(--dur-base) var(--ease-out);
  }

  .editor-toggle:hover {
    background: var(--primary-hover);
    transform: translateY(-2px);
  }

  .editor-main {
    padding: 20px 16px 40px;
  }

  .sec-leave-active {
    top: 20px;
    left: 16px;
    right: 16px;
  }
}

/* ≥640px：角色两列 / 分镜两列 */
@media (min-width: 640px) {
  .char-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .shot-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

/* ≥1024px：角色三列 */
@media (min-width: 1024px) {
  .char-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}

/* 窄屏细节 */
@media (max-width: 640px) {
  .editor-header {
    padding: 0 12px;
    gap: var(--space-2);
  }
  .editor-meta {
    display: none;
  }
  .dub-row {
    flex-wrap: wrap;
  }
  .dub-audio {
    width: 100%;
  }
  .dub-audio audio {
    max-width: 100%;
    width: 100%;
  }
  .step-ops {
    width: 100%;
  }
}
</style>
