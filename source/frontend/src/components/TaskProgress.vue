<script setup>
import { computed, ref, watch } from 'vue'
import { taskTypeLabel, taskStatusText, taskStatusTag } from '../utils'

const props = defineProps({
  /** [{ task_id, type, status, progress, error }] */
  tasks: { type: Array, default: () => [] }
})

const emit = defineEmits(['retry', 'cancel'])

const WEIGHT = { running: 0, processing: 0, pending: 1, failed: 2, succeeded: 3 }

const CANCELABLE = ['pending', 'queued', 'running', 'processing']

const sorted = computed(() => {
  const list = props.tasks.filter((t) => t && (t.task_id || t.id))
  return [...list].sort((a, b) => {
    const wa = WEIGHT[a.status] ?? 4
    const wb = WEIGHT[b.status] ?? 4
    return wa - wb
  })
})

const activeCount = computed(
  () => sorted.value.filter((t) => CANCELABLE.includes(t.status)).length
)
const failedCount = computed(
  () => sorted.value.filter((t) => t.status === 'failed').length
)
const doneCount = computed(
  () => sorted.value.filter((t) => t.status === 'succeeded').length
)

/* 面板只展示进行中/失败任务，已完成项折叠为计数，避免长列表遮挡页面 */
const visibleTasks = computed(
  () => sorted.value.filter((t) => t.status !== 'succeeded')
)

/* 折叠面板：默认收起，仅手动点击摘要胶囊开合 */
const open = ref(false)

/* 参考稿 .tag 语义 soft 底形态：el-tag type -> tag class */
const TAG_CLASS = {
  primary: 'tag-primary',
  success: 'tag-success',
  warning: 'tag-warning',
  danger: 'tag-danger'
}

function tagClass(status) {
  return TAG_CLASS[taskStatusTag(status)] || ''
}

function pct(t) {
  const p = Number(t.progress)
  if (t.status === 'succeeded') return 100
  if (!Number.isFinite(p)) return t.status === 'running' || t.status === 'processing' ? 50 : 0
  return Math.max(0, Math.min(100, Math.round(p * (p <= 1 ? 100 : 1))))
}

function retry(t) {
  emit('retry', t)
}

function cancel(t) {
  emit('cancel', t)
}
</script>

<template>
  <div v-if="sorted.length" class="tp-wrap">
    <!-- 收起态：摘要胶囊 -->
    <button
      type="button"
      class="tp-summary"
      :aria-expanded="open"
      aria-label="展开或收起生成任务面板"
      @click="open = !open"
    >
      <span v-if="activeCount" class="tp-spinner" aria-hidden="true"></span>
      <span v-else class="tp-dot" :class="{ 'tp-dot--err': failedCount }" aria-hidden="true"></span>
      <span class="tp-summary-text">
        {{ activeCount ? `生成中 ${activeCount}` : failedCount ? `失败 ${failedCount}` : `已完成 ${doneCount}` }}
      </span>
      <svg
        class="tp-chevron"
        :class="{ open }"
        aria-hidden="true"
        width="12"
        height="12"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2.5"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <polyline points="6 9 12 15 18 9" />
      </svg>
    </button>

    <!-- 展开态：Teleport 到 body，固定视口右下角，完全脱离顶栏堆叠上下文 -->
    <Teleport to="body">
      <transition name="tp-panel">
        <div
          v-if="open"
          class="task-progress"
          aria-live="polite"
          aria-label="生成任务进度"
        >
          <div class="tp-panel-head">
            <span class="tp-panel-title">生成任务</span>
            <button type="button" class="link-btn" aria-label="收起任务面板" @click="open = false">
              收起
            </button>
          </div>
          <div v-for="t in visibleTasks" :key="t.task_id || t.id" class="task-item">
            <div class="row">
              <span class="tag" :class="tagClass(t.status)">{{ taskStatusText(t.status) }}</span>
              <span class="type" :title="taskTypeLabel(t.type)">{{ taskTypeLabel(t.type) }}</span>
              <button v-if="t.status === 'failed'" type="button" class="link-btn retry-btn" @click="retry(t)">
                重试
              </button>
              <button
                v-if="CANCELABLE.includes(t.status)"
                type="button"
                class="link-btn cancel-btn"
                @click="cancel(t)"
              >
                取消
              </button>
            </div>
            <el-progress
              v-if="t.status !== 'failed'"
              :percentage="pct(t)"
              :status="t.status === 'succeeded' ? 'success' : undefined"
              :show-text="false"
              :stroke-width="4"
            />
            <div v-else class="err" :title="t.error || '生成失败'">{{ t.error || '生成失败' }}</div>
          </div>
          <div v-if="doneCount" class="task-item done-row">
            <span class="tag tag-success">已完成</span>
            <span class="type">共 {{ doneCount }} 项任务</span>
          </div>
          <div v-if="!visibleTasks.length" class="task-item">
            <span class="type">当前没有进行中的任务</span>
          </div>
        </div>
      </transition>
    </Teleport>
  </div>
</template>

<style scoped>
.tp-wrap {
  position: relative;
}

/* ---------- 摘要胶囊 ---------- */
.tp-summary {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 32px;
  padding: 0 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-pill);
  background: var(--surface);
  color: var(--text-secondary);
  font-family: inherit;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  transition: color var(--dur-fast) var(--ease-out),
    border-color var(--dur-fast) var(--ease-out),
    background-color var(--dur-fast) var(--ease-out);
}

.tp-summary:hover {
  color: var(--text-primary);
  border-color: var(--border-strong);
  background: var(--surface-raised);
}

.tp-summary-text {
  white-space: nowrap;
}

.tp-spinner {
  width: 12px;
  height: 12px;
  flex-shrink: 0;
  border-radius: 50%;
  border: 2px solid var(--primary-soft);
  border-top-color: var(--primary);
  animation: tp-spin 0.8s linear infinite;
}

@keyframes tp-spin {
  to {
    transform: rotate(360deg);
  }
}

.tp-dot {
  width: 8px;
  height: 8px;
  flex-shrink: 0;
  border-radius: 50%;
  background: var(--success);
}

.tp-dot--err {
  background: var(--error);
}

.tp-chevron {
  flex-shrink: 0;
  transition: transform var(--dur-base) var(--ease-out);
}

.tp-chevron.open {
  transform: rotate(180deg);
}

/* ---------- 浮动面板（Teleport 到 body，固定视口右下角） ---------- */
.task-progress {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: var(--z-pop);
  display: flex;
  flex-direction: column;
  width: 320px;
  max-height: min(420px, calc(100vh - 120px));
  overflow-y: auto;
  overscroll-behavior: contain;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xl);
}

.tp-panel-head {
  position: sticky;
  top: 0;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px 10px 16px;
  background: var(--surface-raised);
  border-bottom: 1px solid var(--divider);
}

.tp-panel-title {
  font-size: 12.5px;
  font-weight: 700;
  color: var(--text-secondary);
}

.tp-panel-enter-active,
.tp-panel-leave-active {
  transition: opacity var(--dur-base) var(--ease-out),
    transform var(--dur-base) var(--ease-out);
}

.tp-panel-enter-from,
.tp-panel-leave-to {
  opacity: 0;
  transform: translateY(8px);
}

@media (max-width: 640px) {
  .task-progress {
    right: 16px;
    left: 16px;
    bottom: 16px;
    width: auto;
  }
}

.task-item {
  padding: 12px 16px;
  border-bottom: 1px solid var(--divider);
  flex-shrink: 0;
}

.task-item:last-child {
  border-bottom: none;
}

.row {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 参考稿 .tag pill 形态 */
.tag {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
  padding: 4px 12px;
  border-radius: var(--radius-pill);
  background: rgba(255, 255, 255, 0.08);
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
}

.tag-primary {
  background: var(--primary-soft);
  color: var(--accent);
}

.tag-success {
  background: var(--success-soft);
  color: var(--success);
}

.tag-warning {
  background: var(--warning-soft);
  color: var(--warning);
}

.tag-danger {
  background: rgba(255, 59, 48, 0.15);
  color: var(--error);
}

.type {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 参考稿 .btn-ghost 小字形态 */
.link-btn {
  appearance: none;
  -webkit-appearance: none;
  flex-shrink: 0;
  padding: 4px 8px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  font-family: inherit;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-secondary);
  cursor: pointer;
  transition: color var(--dur-fast) var(--ease-out),
    background-color var(--dur-fast) var(--ease-out);
}

.link-btn:hover {
  color: var(--text-primary);
  background: rgba(255, 255, 255, 0.06);
}

.err {
  margin-top: var(--space-1);
  font-size: var(--text-xs);
  color: var(--error);
  word-break: break-all;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.done-row {
  opacity: 0.75;
}

.task-item :deep(.el-progress) {
  margin-top: 8px;
}

.task-enter-active,
.task-leave-active {
  transition: opacity 0.3s var(--ease-out),
    transform 0.3s var(--ease-out);
}
.task-enter-from,
.task-leave-to {
  opacity: 0;
  transform: translateY(8px);
}
</style>
