<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import api, { unwrap } from '../api'
import { asList } from '../utils'
import ProjectCard from '../components/ProjectCard.vue'

const router = useRouter()

const projects = ref([])
const loading = ref(false)
const keyword = ref('')
const status = ref('')

/* 参考稿 filter-chip：全部/待开始/进行中/已完成（值仍走现有 status ref 过滤逻辑） */
const filterChips = [
  { value: '', label: '全部' },
  { value: 'draft', label: '待开始' },
  { value: 'producing', label: '进行中' },
  { value: 'completed', label: '已完成' }
]

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return projects.value.filter((p) => {
    if (status.value && p.status !== status.value) return false
    if (!kw) return true
    return [p.title, p.genre, p.style]
      .some((f) => String(f || '').toLowerCase().includes(kw))
  })
})

const stats = computed(() => {
  const total = projects.value.length
  const inProgress = projects.value.filter((p) =>
    ['draft', 'script_ready', 'producing'].includes(p.status)
  ).length
  const completed = projects.value.filter((p) => p.status === 'completed').length
  return { total, inProgress, completed }
})

async function load() {
  loading.value = true
  try {
    const data = unwrap(await api.get('/projects', { params: { page: 1, page_size: 100 } }))
    projects.value = asList(data, 'projects', 'list')
  } finally {
    loading.value = false
  }
}

onMounted(load)

function onDeleted(id) {
  projects.value = projects.value.filter((p) => p.id !== id)
}
</script>

<template>
  <div class="g-page">
    <!-- 参考稿 home-hero 大卡 -->
    <section class="home-hero">
      <div class="hero-left">
        <h1>AI 漫剧工作台</h1>
        <p>从一个创意到一部漫剧，AI 全流程为你代工</p>
        <div class="home-stats">
          <div class="home-stat">
            <b>{{ stats.total }}</b>
            <span>项目总数</span>
          </div>
          <div class="home-stat">
            <b>{{ stats.inProgress }}</b>
            <span>进行中</span>
          </div>
          <div class="home-stat">
            <b>{{ stats.completed }}</b>
            <span>已完成</span>
          </div>
        </div>
      </div>
    </section>

    <!-- 参考稿 toolbar：搜索 + 筛选 chips -->
    <div class="toolbar">
      <div class="search-box">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
          <circle cx="11" cy="11" r="7" />
          <path d="m21 21-4.35-4.35" />
        </svg>
        <el-input
          v-model="keyword"
          placeholder="搜索项目标题 / 题材 / 风格"
          clearable
        />
      </div>
      <div class="chip-row" role="group" aria-label="按状态筛选">
        <button
          v-for="c in filterChips"
          :key="c.value"
          type="button"
          class="filter-chip"
          :class="{ on: status === c.value }"
          @click="status = c.value"
        >
          {{ c.label }}
        </button>
      </div>
    </div>

    <!-- 参考稿 project-grid -->
    <div v-loading="loading" class="grid-wrap">
      <div v-if="filtered.length" class="grid">
        <ProjectCard
          v-for="(p, i) in filtered"
          :key="p.id"
          v-reveal="Math.min(i + 1, 6)"
          :project="p"
          @deleted="onDeleted"
        />
      </div>
      <div v-else-if="!loading" class="g-empty">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
          <rect x="3" y="3" width="7" height="7" rx="1.5" />
          <rect x="14" y="3" width="7" height="7" rx="1.5" />
          <rect x="3" y="14" width="7" height="7" rx="1.5" />
          <rect x="14" y="14" width="7" height="7" rx="1.5" />
        </svg>
        <h3>暂无项目</h3>
        <p>点击右上角「新建」开始你的第一个漫剧</p>
        <el-button type="primary" round @click="router.push('/create')">开始创作</el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ---------- home-hero（参考稿） ---------- */
.home-hero {
  background: linear-gradient(135deg, rgba(0, 113, 227, 0.08), transparent 60%);
  border-radius: var(--radius-xl);
  border: 1px solid var(--border);
  padding: 40px 48px;
  margin-bottom: 40px;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  flex-wrap: wrap;
}

.home-hero h1 {
  font-size: 32px;
  font-weight: 800;
  letter-spacing: -1px;
  line-height: 1.15;
  color: var(--text-primary);
  margin: 0;
}

.home-hero p {
  color: var(--text-secondary);
  margin-top: 8px;
  font-size: 15px;
}

.home-stats {
  display: flex;
  gap: 32px;
  margin-top: 20px;
}

.home-stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.home-stat b {
  font-size: 24px;
  font-weight: 800;
  font-family: var(--font-mono);
  letter-spacing: -1px;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.home-stat span {
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 500;
}

/* ---------- toolbar（参考稿） ---------- */
.toolbar {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 28px;
  flex-wrap: wrap;
}

.search-box {
  position: relative;
  width: 280px;
  max-width: 100%;
}

.search-box > svg {
  position: absolute;
  left: 14px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-tertiary);
  pointer-events: none;
  z-index: 1;
}

.search-box :deep(.el-input),
.search-box :deep(.el-input__wrapper) {
  width: 100%;
}

.search-box :deep(.el-input__wrapper) {
  padding-left: 42px;
  border-radius: var(--radius-pill);
  background-color: rgba(255, 255, 255, 0.04);
  box-shadow: none;
  border: 1px solid transparent;
  transition: background-color 0.2s var(--ease-out),
    border-color 0.2s var(--ease-out), box-shadow 0.2s var(--ease-out);
}

.search-box :deep(.el-input__wrapper:hover) {
  box-shadow: none;
  background-color: rgba(255, 255, 255, 0.07);
}

.search-box :deep(.el-input__wrapper.is-focus) {
  background-color: var(--surface);
  border-color: var(--primary);
  box-shadow: none;
}

.chip-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.filter-chip {
  appearance: none;
  -webkit-appearance: none;
  border: none;
  height: 34px;
  padding: 0 16px;
  border-radius: var(--radius-pill);
  background: rgba(255, 255, 255, 0.06);
  color: var(--text-secondary);
  font-family: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  transition: background-color 0.18s var(--ease-out),
    color 0.18s var(--ease-out);
}

.filter-chip:hover {
  background: rgba(255, 255, 255, 0.1);
  color: var(--text-primary);
}

.filter-chip.on {
  background: var(--text-primary);
  color: #000;
}

[data-theme='light'] .filter-chip.on {
  color: var(--bg);
}

/* ---------- project-grid（参考稿） ---------- */
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

/* ---------- 响应式（≤768px） ---------- */
@media (max-width: 768px) {
  .home-hero {
    padding: 28px 24px;
    margin-bottom: 28px;
  }
  .home-hero h1 {
    font-size: 24px;
  }
  .toolbar {
    gap: 12px;
  }
  .search-box {
    width: 100%;
    flex: 1 1 100%;
  }
}
</style>
