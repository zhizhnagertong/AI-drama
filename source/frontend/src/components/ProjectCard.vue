<script setup>
import { computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete } from '@element-plus/icons-vue'
import api from '../api'
import { gradVar, statusText, fmtTime, imgUrlOf } from '../utils'

const props = defineProps({
  project: { type: Object, required: true }
})
const emit = defineEmits(['deleted'])

const cover = computed(() => imgUrlOf(props.project))
const styleName = computed(() => props.project.style || props.project.style_name || '未指定风格')
const timeText = computed(() => fmtTime(props.project.updated_at || props.project.created_at))

const charCount = computed(() => {
  const p = props.project
  const v = p.characters?.length ?? p.character_count ?? p.stats?.character_count
  return Number.isFinite(v) ? v : null
})
const epCount = computed(() => {
  const p = props.project
  const v = p.episodes?.length ?? p.episode_count ?? p.stats?.storyboard_count
  return Number.isFinite(v) ? v : null
})

/* 参考稿 dot 语义：进行中=success、已完成=primary、草稿=tertiary */
const dotClass = computed(() => {
  const s = props.project.status
  if (s === 'completed') return 'done'
  if (s === 'producing' || s === 'script_ready') return 'on'
  if (s === 'failed') return 'err'
  return ''
})

async function removeProject() {
  const title = props.project.title || '未命名项目'
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
  await api.delete(`/projects/${props.project.id}`)
  ElMessage.success('项目已彻底删除')
  emit('deleted', props.project.id)
}
</script>

<template>
  <article v-reveal class="project-card g-card">
    <div class="project-thumb">
      <img
        v-if="cover"
        :src="cover"
        :alt="`${project.title || '未命名项目'} 封面`"
        loading="lazy"
        width="640"
        height="360"
      />
      <div v-else class="thumb-grad" :style="{ background: gradVar(project.id) }">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
          <path d="M3 8l4-4 5 5 4-4 5 5v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
        </svg>
      </div>
      <div class="project-status">
        <span class="tag">
          <span class="dot" :class="dotClass"></span>
          {{ statusText(project.status) }}
        </span>
      </div>
      <button
        type="button"
        class="project-more"
        title="删除项目"
        aria-label="删除项目"
        @click.stop="removeProject"
      >
        <el-icon :size="14"><Delete /></el-icon>
      </button>
    </div>
    <div class="project-body">
      <div class="project-name" :title="project.title">
        <router-link class="title-link" :to="`/project/${project.id}`">
          {{ project.title || '未命名项目' }}
        </router-link>
      </div>
      <div class="project-meta">
        <span class="tag tag-primary">{{ styleName }}</span>
        <span v-if="charCount !== null && epCount !== null" class="counts">
          {{ charCount }}角色 · {{ epCount }}集
        </span>
        <span v-if="timeText" class="time">{{ timeText }}</span>
      </div>
    </div>
  </article>
</template>

<style scoped>
.project-card {
  position: relative;
  cursor: pointer;
  transition: transform 0.4s var(--ease-out),
    box-shadow 0.4s var(--ease-out), border-color 0.4s var(--ease-out);
}

.project-card:hover {
  transform: translateY(-4px);
  box-shadow: var(--shadow-lg);
  border-color: var(--border-strong);
}

/* ---------- 封面（参考稿 .project-thumb） ---------- */
.project-thumb {
  position: relative;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  background: var(--thumb-bg);
  display: flex;
  align-items: center;
  justify-content: center;
}

.project-thumb img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.thumb-grad {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.thumb-grad svg {
  width: 40px;
  height: 40px;
  color: rgba(255, 255, 255, 0.15);
}

/* ---------- 状态 tag（参考稿 .project-status，左上角磨砂胶囊 + dot） ---------- */
.project-status {
  position: absolute;
  top: 12px;
  left: 12px;
  z-index: 2;
}

.project-status .tag {
  display: inline-flex;
  align-items: center;
  padding: 4px 12px;
  border-radius: var(--radius-pill);
  background: rgba(0, 0, 0, 0.6);
  -webkit-backdrop-filter: blur(10px);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 600;
}

.project-status .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-tertiary);
  display: inline-block;
  margin-right: 6px;
}

.project-status .dot.on {
  background: var(--success);
}

.project-status .dot.done {
  background: var(--primary);
}

.project-status .dot.err {
  background: var(--error);
}

/* ---------- 删除按钮（参考稿 .project-more，hover 显现） ---------- */
.project-more {
  appearance: none;
  -webkit-appearance: none;
  position: absolute;
  top: 10px;
  right: 10px;
  z-index: 2;
  width: 32px;
  height: 32px;
  padding: 0;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.6);
  -webkit-backdrop-filter: blur(10px);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.08);
  display: grid;
  place-items: center;
  color: var(--text-secondary);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.2s var(--ease-out),
    background-color 0.2s var(--ease-out), color 0.2s var(--ease-out);
}

.project-card:hover .project-more,
.project-card:focus-within .project-more {
  opacity: 1;
}

.project-more:hover {
  background: rgba(0, 0, 0, 0.8);
  color: var(--text-primary);
}

/* ---------- 正文（参考稿 .project-body） ---------- */
.project-body {
  padding: 18px 20px;
}

.project-name {
  font-size: 16px;
  font-weight: 700;
  letter-spacing: -0.3px;
  margin-bottom: 6px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--text-primary);
}

.title-link {
  color: inherit;
}

/* stretched-link：整个卡片可点击，且键盘可聚焦标题链接 */
.title-link::after {
  content: '';
  position: absolute;
  inset: 0;
  z-index: 1;
}

.title-link:hover {
  color: var(--primary);
}

.project-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12.5px;
  color: var(--text-secondary);
  flex-wrap: wrap;
}

.project-meta .tag {
  display: inline-flex;
  align-items: center;
  padding: 4px 12px;
  border-radius: var(--radius-pill);
  font-size: 12px;
  font-weight: 600;
}

.project-meta .tag-primary {
  background: var(--primary-soft);
  color: var(--accent);
}

.project-meta .time {
  font-variant-numeric: tabular-nums;
}
</style>
