<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api, { unwrap } from '../api'
import { GENRES, STYLES, RATIOS } from '../utils'
import { useStyleStore } from '../stores/styles'

const router = useRouter()
const styleStore = useStyleStore()

const form = ref({
  title: '',
  genre: '科幻',
  style: '赛博朋克',
  aspect_ratio: '9:16',
  inspiration: ''
})

/* 风格描述：优先用后端预设 description，本地字典作 fallback */
const STYLE_DESC = {
  赛博朋克: '霓虹光效、未来都市',
  水墨国风: '水墨笔触、东方意境',
  日系动漫: '清新线条、高饱和',
  美式漫画: '强对比块面、硬派',
  '3D卡通': '圆润立体、玩具质感',
  写实: '电影感光影、细节'
}

const styleOptions = computed(() => {
  /* 后端可达时严格使用预设列表（全部停用则为空），仅请求失败回退内置常量 */
  const presets =
    styleStore.loaded && styleStore.source === 'remote'
      ? styleStore.presets
      : styleStore.presets.length
        ? styleStore.presets
        : STYLES.map((name) => ({ name }))
  return presets.map((p) => ({
    name: p.name,
    desc: p.description || STYLE_DESC[p.name] || 'AI 视觉风格'
  }))
})

onMounted(async () => {
  /* 强制刷新，确保与风格预设管理页的启停/增删即时同步 */
  await styleStore.fetch(true)
  if (!styleOptions.value.some((s) => s.name === form.value.style)) {
    form.value.style = styleOptions.value[0]?.name || form.value.style
  }
})

const creating = ref(false)

const canSubmit = computed(
  () => form.value.inspiration.trim().length > 0 || importedFiles.value.length > 0
)

/* ---------- 拖拽导入文件（与文字描述分开保存） ---------- */
const dragOver = ref(false)
const importing = ref(false)
const MAX_IMPORT_CHARS = 20000
const MAX_TOTAL_CHARS = 40000

/** 已导入的文件列表：{ name, text, expanded } */
const importedFiles = ref([])

function removeImportedFile(idx) {
  importedFiles.value.splice(idx, 1)
}

function toggleExpand(idx) {
  const f = importedFiles.value[idx]
  f.expanded = !f.expanded
}

const TEXT_EXT = /\.(txt|md|markdown|log|json|csv)$/i

/** 从 .docx（ZIP + deflate）中提取 word/document.xml 的纯文本 */
async function extractDocxText(file) {
  const buf = new Uint8Array(await file.arrayBuffer())
  const dv = new DataView(buf.buffer)
  /* 反向扫描定位中央目录结尾记录 EOCD */
  let eocd = -1
  for (let i = buf.length - 22; i >= Math.max(0, buf.length - 65557); i--) {
    if (dv.getUint32(i, true) === 0x06054b50) {
      eocd = i
      break
    }
  }
  if (eocd < 0) throw new Error('invalid zip')
  const count = dv.getUint16(eocd + 10, true)
  let off = dv.getUint32(eocd + 16, true)
  let target = null
  for (let n = 0; n < count; n++) {
    if (dv.getUint32(off, true) !== 0x02014b50) break
    const method = dv.getUint16(off + 10, true)
    const compSize = dv.getUint32(off + 20, true)
    const nameLen = dv.getUint16(off + 28, true)
    const extraLen = dv.getUint16(off + 30, true)
    const commentLen = dv.getUint16(off + 32, true)
    const localHeader = dv.getUint32(off + 42, true)
    const name = new TextDecoder().decode(buf.subarray(off + 46, off + 46 + nameLen))
    if (name === 'word/document.xml') {
      target = { method, compSize, localHeader }
      break
    }
    off += 46 + nameLen + extraLen + commentLen
  }
  if (!target) throw new Error('document.xml not found')
  const lNameLen = dv.getUint16(target.localHeader + 26, true)
  const lExtraLen = dv.getUint16(target.localHeader + 28, true)
  const start = target.localHeader + 30 + lNameLen + lExtraLen
  const data = buf.subarray(start, start + target.compSize)
  let xmlBytes = data
  if (target.method === 8) {
    if (typeof DecompressionStream === 'undefined') throw new Error('no DecompressionStream')
    const stream = new Blob([data]).stream().pipeThrough(new DecompressionStream('deflate-raw'))
    xmlBytes = new Uint8Array(await new Response(stream).arrayBuffer())
  } else if (target.method !== 0) {
    throw new Error('unsupported zip method')
  }
  const xml = new TextDecoder().decode(xmlBytes)
  return xml
    .replace(/<w:tab\b[^>]*\/>/g, '\t')
    .replace(/<\/w:p>/g, '\n')
    .replace(/<[^>]+>/g, '')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&#(\d+);/g, (_, d) => String.fromCodePoint(+d))
    .replace(/&amp;/g, '&')
}

/** 按文件类型提取文本，不支持的类型返回 null */
async function extractText(file) {
  if (/\.docx$/i.test(file.name)) return extractDocxText(file)
  if (TEXT_EXT.test(file.name) || file.type.startsWith('text/')) return file.text()
  return null
}

async function onInspirationDrop(e) {
  dragOver.value = false
  const files = Array.from(e.dataTransfer?.files || [])
  if (!files.length) return
  importing.value = true
  let ok = 0
  try {
    for (const f of files) {
      try {
        const text = await extractText(f)
        if (text == null) {
          ElMessage.warning(`暂不支持 ${f.name}，请使用 .txt / .md / .docx 文件`)
          continue
        }
        const t = text.trim()
        if (!t) {
          ElMessage.warning(`${f.name} 内容为空`)
          continue
        }
        let clipped = t
        if (clipped.length > MAX_IMPORT_CHARS) {
          clipped = clipped.slice(0, MAX_IMPORT_CHARS)
          ElMessage.warning(`${f.name} 内容过长，已截取前 ${MAX_IMPORT_CHARS} 字`)
        }
        importedFiles.value.push({ name: f.name, text: clipped, expanded: false })
        ok++
      } catch {
        ElMessage.error(`${f.name} 解析失败，请另存为 .txt 后重试`)
      }
    }
    if (ok) ElMessage.success(`已导入 ${ok} 个文件`)
  } finally {
    importing.value = false
  }
}

function onDragLeave(e) {
  if (!e.currentTarget.contains(e.relatedTarget)) dragOver.value = false
}

/** 提交时把文字描述与文件内容组合为灵感文本（带来源标记，供 AI 区分） */
function buildInspiration() {
  const parts = []
  const desc = form.value.inspiration.trim()
  if (desc) parts.push(desc)
  for (const f of importedFiles.value) {
    parts.push(`【文件：${f.name}】\n${f.text}`)
  }
  let merged = parts.join('\n\n')
  if (merged.length > MAX_TOTAL_CHARS) {
    merged = merged.slice(0, MAX_TOTAL_CHARS)
  }
  return merged
}

async function createPipeline() {
  if (!canSubmit.value) {
    ElMessage.warning('输入故事灵感，或拖入文本文件')
    return
  }
  creating.value = true
  let createdId = null
  try {
    const project = unwrap(
      await api.post('/projects', { ...form.value, inspiration: buildInspiration() })
    )
    const id = project?.id ?? project?.project?.id
    if (!id) throw new Error('创建项目失败')
    createdId = id
    // 项目一旦创建成功就先进编辑器：流水线启动失败不能表现为"整个创建失败"，
    // 否则用户会重复点击，堆出一堆空草稿项目。
    router.push(`/editor/${id}`)
    try {
      await api.post(`/projects/${id}/pipeline`)
      ElMessage.success('AI 流水线已启动，正在为你生成剧本…')
    } catch {
      ElMessage.warning('项目已创建，但 AI 流水线启动失败，可在创作台手动重新生成')
    }
  } catch {
    /* 错误提示由拦截器统一处理 */
    if (!createdId) {
      /* 项目未创建：停留在当前页，保留用户已填内容 */
    }
  } finally {
    creating.value = false
  }
}
</script>

<template>
  <div class="g-page">
    <div v-reveal class="create-layout">
      <!-- 左：创作面板 -->
      <div class="create-panel">
        <h2>开始创作</h2>
        <p>输入一个灵感，AI 自动生成剧本、分镜、角色与成片</p>

        <div class="field-group">
          <label class="field-label" for="inspiration-input">
            创作灵感 <span class="required">*</span>
          </label>
          <div
            class="inspiration-drop"
            :class="{ 'drag-over': dragOver, importing }"
            @dragenter.prevent="dragOver = true"
            @dragover.prevent="dragOver = true"
            @dragleave.prevent="onDragLeave"
            @drop.prevent="onInspirationDrop"
          >
            <textarea
              id="inspiration-input"
              v-model="form.inspiration"
              class="inspiration"
              rows="5"
              aria-label="创作灵感"
              placeholder="输入你的故事灵感…&#10;支持一句话点子、故事梗概或小说片段，例如：&#10;「赛博朋克都市里，一个失忆的外卖骑手发现自己救过的人都是同一个女孩…」"
            ></textarea>
            <div v-if="dragOver" class="drop-mask">
              <span>松开导入文件</span>
            </div>
          </div>
          <div v-if="importedFiles.length" class="file-list">
            <div v-for="(f, i) in importedFiles" :key="i" class="file-item">
              <button
                type="button"
                class="file-name"
                :title="f.text"
                @click="toggleExpand(i)"
              >
                <svg
                  aria-hidden="true"
                  width="13"
                  height="13"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                >
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <path d="M14 2v6h6" />
                </svg>
                <span class="file-name-text">{{ f.name }}</span>
                <span class="file-meta">{{ f.text.length }} 字 {{ f.expanded ? '▲' : '▼' }}</span>
              </button>
              <button
                type="button"
                class="file-remove"
                aria-label="移除文件"
                @click="removeImportedFile(i)"
              >
                ×
              </button>
              <pre v-if="f.expanded" class="file-preview">{{ f.text }}</pre>
            </div>
          </div>
          <span class="drop-hint">
            {{ importing ? '正在解析文件…' : '可拖入.txt /.md /.docx文件' }}
          </span>
        </div>

        <div class="field-group">
          <label class="field-label">标题（可选）</label>
          <el-input
            v-model="form.title"
            class="field-input"
            placeholder="留给 AI 起名也可以"
            maxlength="30"
          />
        </div>

        <div class="field-group">
          <label class="field-label">题材</label>
          <el-select v-model="form.genre" class="field-input">
            <el-option v-for="g in GENRES" :key="g" :label="g" :value="g" />
          </el-select>
        </div>

        <div class="field-group">
          <label class="field-label">视觉风格</label>
          <div v-if="styleOptions.length" class="style-grid">
            <button
              v-for="s in styleOptions"
              :key="s.name"
              type="button"
              class="style-option"
              :class="{ on: form.style === s.name }"
              @click="form.style = s.name"
            >
              <b>{{ s.name }}</b>
              <span>{{ s.desc }}</span>
            </button>
          </div>
          <div v-else class="style-empty">
            暂无启用中的视觉风格，请先到
            <router-link to="/styles">风格预设</router-link>
            启用或新建风格
          </div>
        </div>

        <div class="field-group">
          <label class="field-label">画面比例</label>
          <div class="aspect-row">
            <button
              v-for="r in RATIOS"
              :key="r.value"
              type="button"
              class="aspect-option"
              :class="{ on: form.aspect_ratio === r.value }"
              @click="form.aspect_ratio = r.value"
            >
              {{ r.label }}
            </button>
          </div>
        </div>

        <div class="create-btn-area">
          <el-button
            class="generate-btn"
            type="primary"
            size="large"
            :loading="creating"
            :disabled="!canSubmit"
            @click="createPipeline"
          >
            <template #icon>
              <svg
                aria-hidden="true"
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2.5"
              >
                <path d="M12 2l2.4 7.2L22 11l-7.6 2.8L12 22l-2.4-8.2L2 11l7.6-1.8z" />
              </svg>
            </template>
            <span class="generate-label">{{ creating ? '生成中…' : '一键 AI 生成' }}</span>
          </el-button>
          <span class="hint">将依次生成：剧本 → 角色 → 分镜 → 画面 → 配音 → 成片</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ---------- 布局 ---------- */
.create-layout {
  display: grid;
  grid-template-columns: 1fr;
  width: min(50vw, 100%);
  min-width: 320px;
  margin: 0 auto;
}

/* ---------- 面板（参考稿 .create-panel） ---------- */
.create-panel {
  background: var(--surface);
  border-radius: var(--radius-xl);
  border: 1px solid var(--border);
  padding: 32px;
  box-shadow: var(--shadow-sm);
  align-self: start;
}

.create-panel h2 {
  font-size: 24px;
  font-weight: 800;
  letter-spacing: -0.5px;
  margin-bottom: 6px;
  color: var(--text-primary);
}

.create-panel > p {
  color: var(--text-secondary);
  font-size: 14px;
  margin-bottom: 28px;
}

/* ---------- 字段（参考稿 .field-group / .field-label） ---------- */
.field-group {
  margin-bottom: 20px;
}

.field-label {
  display: block;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.field-label .required {
  color: var(--danger);
  margin-left: 2px;
}

.field-input {
  width: 100%;
}

/* ---------- 灵感输入（参考稿 .textarea） ---------- */
.inspiration-drop {
  position: relative;
  border-radius: var(--radius);
}

.inspiration-drop.drag-over .inspiration {
  border-color: var(--primary);
  box-shadow: 0 0 0 3.5px var(--primary-ring);
}

.drop-mask {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius);
  border: 2px dashed var(--primary);
  background: rgba(0, 113, 227, 0.1);
  color: var(--primary);
  font-size: 14px;
  font-weight: 600;
  pointer-events: none;
}

.drop-hint {
  display: block;
  margin-top: 6px;
  font-size: 12px;
  color: var(--text-tertiary);
}

/* ---------- 已导入文件列表 ---------- */
.file-list {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.file-item {
  position: relative;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  overflow: hidden;
}

.file-name {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  appearance: none;
  border: none;
  background: transparent;
  color: var(--text-primary);
  font-family: inherit;
  font-size: 13px;
  padding: 9px 36px 9px 12px;
  cursor: pointer;
  text-align: left;
}

.file-name:hover {
  background: rgba(255, 255, 255, 0.04);
}

[data-theme='light'] .file-name:hover {
  background: rgba(29, 29, 31, 0.04);
}

.file-name-text {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 600;
}

.file-meta {
  flex-shrink: 0;
  font-size: 12px;
  color: var(--text-tertiary);
  font-weight: 400;
}

.file-remove {
  position: absolute;
  appearance: none;
  border: none;
  background: transparent;
  color: var(--text-tertiary);
  font-size: 16px;
  line-height: 1;
  padding: 2px 6px;
  cursor: pointer;
}

.file-remove {
  top: 7px;
  right: 6px;
}

.file-remove:hover {
  color: var(--danger);
}

.file-preview {
  margin: 0;
  padding: 10px 12px;
  border-top: 1px dashed var(--border);
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 180px;
  overflow: auto;
  font-family: inherit;
}

.inspiration {
  width: 100%;
  padding: 14px 16px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius);
  background: var(--surface);
  color: var(--text-primary);
  font-size: 14px;
  resize: vertical;
  min-height: 120px;
  transition: border-color 0.2s var(--ease-out),
    box-shadow 0.2s var(--ease-out), background-color 0.2s var(--ease-out);
  font-family: var(--font-ui);
  line-height: 1.7;
}

.inspiration:hover {
  border-color: rgba(255, 255, 255, 0.2);
}

[data-theme='light'] .inspiration:hover {
  border-color: rgba(29, 29, 31, 0.2);
}

.inspiration:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 3.5px var(--primary-ring);
}

.inspiration::placeholder {
  color: var(--text-tertiary);
}

/* ---------- 风格选择（参考稿 .style-grid / .style-option） ---------- */
.style-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
}

.style-option {
  appearance: none;
  border: 2px solid var(--border);
  border-radius: var(--radius);
  padding: 14px;
  cursor: pointer;
  transition: border-color 0.2s var(--ease-out),
    background-color 0.2s var(--ease-out);
  background: var(--surface);
  text-align: left;
  color: var(--text-primary);
  font-family: inherit;
}

.style-option:hover {
  border-color: var(--border-strong);
}

.style-option.on {
  border-color: var(--primary);
  background: rgba(0, 113, 227, 0.08);
}

.style-option b {
  display: block;
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 2px;
}

.style-option span {
  font-size: 12px;
  color: var(--text-tertiary);
}

.style-empty {
  border: 2px dashed var(--border);
  border-radius: var(--radius);
  padding: 18px 16px;
  font-size: 13px;
  color: var(--text-secondary);
  text-align: center;
}

.style-empty a {
  color: var(--primary);
  font-weight: 600;
}

/* ---------- 比例选择（参考稿 .aspect-row / .aspect-option） ---------- */
.aspect-row {
  display: flex;
  gap: 10px;
}

.aspect-option {
  flex: 1;
  appearance: none;
  border: 2px solid var(--border);
  border-radius: var(--radius);
  padding: 12px;
  cursor: pointer;
  transition: border-color 0.2s var(--ease-out),
    background-color 0.2s var(--ease-out), color 0.2s var(--ease-out);
  background: var(--surface);
  text-align: center;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  font-family: inherit;
}

.aspect-option:hover {
  border-color: var(--border-strong);
}

.aspect-option.on {
  border-color: var(--primary);
  background: var(--primary-soft);
  color: #5ac8fa;
}

/* ---------- 生成按钮（参考稿 .btn-lg .btn-block） ---------- */
.create-btn-area {
  margin-top: 28px;
}

.generate-btn {
  width: 100%;
  height: 44px;
  font-size: 15px;
}

.generate-label {
  margin-left: var(--space-1);
}

.hint {
  display: block;
  margin-top: 12px;
  font-size: 12.5px;
  color: var(--text-tertiary);
  text-align: center;
}

/* ---------- 窄屏 ---------- */
@media (max-width: 768px) {
  .create-panel {
    padding: 24px;
  }
  .create-layout {
    width: 100%;
  }
}
</style>
