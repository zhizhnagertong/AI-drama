/** 主布局：磨砂玻璃顶栏 + 导航 + 主题切换 + 用户菜单 + 移动端菜单。 */
import { PlusOutlined } from '@ant-design/icons'
import { Button, Dropdown, Switch } from 'antd'
import type { MenuProps } from 'antd'
import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router'

import { displayNameOf, firstChar } from '@/lib/format'
import { useAuthStore } from '@/store/auth'
import { useSessionStore } from '@/store/session'
import { useThemeStore } from '@/store/theme'

/* ---------------- 线性图标（与参考稿一致，避免额外图标依赖） ---------------- */

function IconGrid() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" />
    </svg>
  )
}

function IconSparkle() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M12 2l2.4 7.2L22 11l-7.6 2.8L12 22l-2.4-8.2L2 11l7.6-1.8z" />
    </svg>
  )
}

function IconUser() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <circle cx="12" cy="8" r="4" />
      <path d="M4 21v-1a6 6 0 0 1 6-6h4a6 6 0 0 1 6 6v1" />
    </svg>
  )
}

const NAVS = [
  { label: '工作台', to: '/', icon: <IconGrid />, end: true },
  { label: '创作', to: '/create', icon: <IconSparkle />, end: false },
  { label: '我的', to: '/mine', icon: <IconUser />, end: false }
]

export function MainLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const theme = useThemeStore((s) => s.theme)
  const toggleTheme = useThemeStore((s) => s.toggle)
  const user = useSessionStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)

  const [scrolled, setScrolled] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)

  useEffect(() => {
    function onScroll() {
      setScrolled(window.scrollY > 10)
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    onScroll()
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  // 路由变化时收起移动端菜单
  useEffect(() => {
    setMobileOpen(false)
  }, [location.pathname])

  const menuItems: MenuProps['items'] = [
    { key: 'name', label: displayNameOf(user), disabled: true },
    { type: 'divider' },
    { key: 'mine', label: '我的主页' },
    { key: 'logout', label: '退出登录', danger: true }
  ]

  async function onUserCommand({ key }: { key: string }) {
    if (key === 'mine') navigate('/mine')
    if (key === 'logout') {
      await logout()
      navigate('/login', { replace: true })
    }
  }

  return (
    <div className="layout">
      <header className={scrolled ? 'topbar glass-bar scrolled' : 'topbar glass-bar'}>
        <div className="topbar-inner">
          <Link to="/" className="brand">
            <span className="brand-logo" aria-hidden="true">
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
            <span className="brand-name">AI 漫剧平台</span>
          </Link>

          <nav className="nav">
            {NAVS.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.end}
                className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}
              >
                {n.icon}
                {n.label}
              </NavLink>
            ))}
          </nav>

          <div className="right">
            <Switch
              className="theme-switch"
              checked={theme === 'dark'}
              checkedChildren="深色"
              unCheckedChildren="浅色"
              aria-label="切换深色/浅色主题"
              onChange={toggleTheme}
            />
            <Button
              className="new-project-btn"
              type="primary"
              shape="round"
              aria-label="新建项目"
              onClick={() => navigate('/create')}
            >
              <PlusOutlined />
              <span className="new-project-label">新建</span>
            </Button>

            <Dropdown
              menu={{ items: menuItems, onClick: onUserCommand }}
              trigger={['click']}
              placement="bottomRight"
            >
              <span
                className="avatar"
                role="button"
                tabIndex={0}
                aria-label="用户菜单"
                aria-haspopup="menu"
              >
                {firstChar(displayNameOf(user))}
              </span>
            </Dropdown>

            <button
              className="mobile-toggle"
              type="button"
              aria-label="打开导航菜单"
              aria-expanded={mobileOpen}
              onClick={() => setMobileOpen((v) => !v)}
            >
              <span />
              <span />
              <span />
            </button>
          </div>
        </div>
      </header>

      <div className={mobileOpen ? 'mobile-menu open' : 'mobile-menu'}>
        {NAVS.map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            end={n.end}
            className={({ isActive }) => (isActive ? 'active' : undefined)}
          >
            {n.icon}
            {n.label}
          </NavLink>
        ))}
      </div>

      <main className="layout-main">
        <Outlet />
      </main>
    </div>
  )
}