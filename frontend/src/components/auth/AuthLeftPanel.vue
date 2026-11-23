<script setup>
/** 左侧品牌展示区：桌面端显示，移动端隐藏（设计规范 15.2）。 */
</script>

<template>
  <aside class="auth-left" aria-hidden="true">
    <div class="left-top-line"></div>
    <div class="left-inner">
      <span class="logo">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M3 8l4-4 5 5 4-4 5 5v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
        </svg>
      </span>
      <h2 class="title">AI 漫剧平台</h2>
      <p class="slogan">一句话灵感，AI 帮你拍成漫剧</p>

      <ul class="features">
        <li>
          <span class="dot"></span>
          <div>
            <strong>剧本 · 分镜 · 画面</strong>
            <em>全流程 AI 智能制作</em>
          </div>
        </li>
        <li>
          <span class="dot"></span>
          <div>
            <strong>多风格视觉预设</strong>
            <em>赛博朋克、水墨国风一键切换</em>
          </div>
        </li>
        <li>
          <span class="dot"></span>
          <div>
            <strong>1080P 竖屏成片</strong>
            <em>自动合成、配音、字幕导出</em>
          </div>
        </li>
      </ul>
    </div>
    <div class="left-glow"></div>
  </aside>
</template>

<style scoped>
.auth-left {
  position: relative;
  display: none;
  flex-direction: column;
  justify-content: center;
  padding: var(--space-8) var(--space-7);
  overflow: hidden;
  border-right: 1px solid var(--border);
  background:
    radial-gradient(680px 420px at 20% 0%, rgba(0, 113, 227, 0.14), transparent 70%),
    radial-gradient(520px 360px at 100% 100%, rgba(0, 113, 227, 0.1), transparent 65%),
    var(--bg);
}

@media (min-width: 1024px) {
  .auth-left {
    display: flex;
  }
}

.left-top-line {
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
}

.left-inner {
  position: relative;
  z-index: 1;
  max-width: 420px;
  animation: fadeUp 0.6s var(--ease-out) both;
}

.logo {
  width: 52px;
  height: 52px;
  border-radius: var(--radius-lg);
  background: var(--brand-grad);
  color: #fff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  box-shadow: var(--shadow);
}

.logo svg {
  width: 26px;
  height: 26px;
}

.title {
  margin: var(--space-5) 0 var(--space-2);
  font-size: var(--text-2xl);
  font-weight: 800;
  letter-spacing: -1.5px;
  color: var(--text-primary);
}

.slogan {
  margin: 0 0 var(--space-7);
  color: var(--text-secondary);
  font-size: var(--text-base);
}

.features {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.features li {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
}

.features .dot {
  flex: none;
  width: 8px;
  height: 8px;
  margin-top: 7px;
  border-radius: 50%;
  background: var(--primary);
  box-shadow: 0 0 0 4px var(--primary-soft);
}

.features strong {
  display: block;
  font-size: var(--text-base);
  font-weight: 700;
  color: var(--text-primary);
}

.features em {
  display: block;
  margin-top: 2px;
  font-style: normal;
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

.left-glow {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
</style>
