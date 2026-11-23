/** 左侧品牌展示区：桌面端显示，移动端隐藏（设计规范 15.2）。 */
export function AuthLeftPanel() {
  return (
    <aside className="auth-left" aria-hidden="true">
      <div className="left-top-line" />
      <div className="left-inner">
        <span className="logo">
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M3 8l4-4 5 5 4-4 5 5v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
          </svg>
        </span>
        <h2 className="title">AI 漫剧平台</h2>
        <p className="slogan">一句话灵感，AI 帮你拍成漫剧</p>

        <ul className="features">
          <li>
            <span className="dot" />
            <div>
              <strong>剧本 · 分镜 · 画面</strong>
              <em>全流程 AI 智能制作</em>
            </div>
          </li>
          <li>
            <span className="dot" />
            <div>
              <strong>多风格视觉预设</strong>
              <em>赛博朋克、水墨国风一键切换</em>
            </div>
          </li>
          <li>
            <span className="dot" />
            <div>
              <strong>1080P 竖屏成片</strong>
              <em>自动合成、配音、字幕导出</em>
            </div>
          </li>
        </ul>
      </div>
      <div className="left-glow" />
    </aside>
  )
}