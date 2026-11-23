/**
 * 主题与上下文根：ConfigProvider（antd 主题）+ App（主题化的 message/modal）。
 *
 * Vue 版没有这一层，因为 Element Plus 通过 CSS 变量吃主题；
 * antd v5 是 CSS-in-JS，必须用 ConfigProvider 的 token 驱动，
 * 这里把 CSS 变量里的语义色一一映射成 antd token。
 */
import { App as AntApp, ConfigProvider, theme as antdTheme } from 'antd'
import type { ThemeConfig } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { useEffect } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router'

import { bindFeedback } from '@/lib/feedback'
import { onSessionExpired } from '@/lib/sessionEvents'
import { useAuthStore } from '@/store/auth'
import { useThemeStore } from '@/store/theme'

function buildTheme(isDark: boolean): ThemeConfig {
  const dark = {
    colorPrimary: '#0071e3',
    colorInfo: '#0071e3',
    colorSuccess: '#34c759',
    colorWarning: '#ff9f0a',
    colorError: '#ff3b30',
    colorBgBase: '#000000',
    colorBgContainer: '#1c1c1e',
    colorBgElevated: '#2c2c2e',
    colorBorder: 'rgba(255,255,255,0.12)',
    colorBorderSecondary: 'rgba(255,255,255,0.08)',
    colorText: '#ffffff',
    colorTextSecondary: 'rgba(255,255,255,0.6)',
    colorTextTertiary: 'rgba(255,255,255,0.4)',
    colorFillSecondary: 'rgba(255,255,255,0.06)',
    colorFillTertiary: 'rgba(255,255,255,0.04)'
  }
  const light = {
    colorPrimary: '#0071e3',
    colorInfo: '#0071e3',
    colorSuccess: '#248a3d',
    colorWarning: '#cf7f00',
    colorError: '#d70015',
    colorBgBase: '#f5f5f7',
    colorBgContainer: '#ffffff',
    colorBgElevated: '#ffffff',
    colorBorder: 'rgba(29,29,31,0.14)',
    colorBorderSecondary: 'rgba(29,29,31,0.08)',
    colorText: '#1d1d1f',
    colorTextSecondary: 'rgba(29,29,31,0.62)',
    colorTextTertiary: 'rgba(29,29,31,0.45)',
    colorFillSecondary: 'rgba(29,29,31,0.04)',
    colorFillTertiary: 'rgba(29,29,31,0.02)'
  }

  return {
    algorithm: isDark ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
    token: {
      ...(isDark ? dark : light),
      borderRadius: 12,
      fontFamily: 'var(--font-ui)',
      fontSize: 14,
      controlHeight: 36,
      wireframe: false
    },
    components: {
      // 参考稿的胶囊按钮
      Button: { borderRadius: 980, borderRadiusLG: 980, fontWeight: 600 },
      Input: { borderRadius: 12, paddingInline: 14 },
      Modal: { borderRadiusLG: 24 },
      Card: { borderRadiusLG: 18 },
      Dropdown: { borderRadiusLG: 12 },
      Segmented: { borderRadius: 980, borderRadiusSM: 980 }
    }
  }
}

/** 绑定主题化 message/modal + 订阅会话失效（非组件代码无法直接 navigate） */
function Binder() {
  const { message, modal } = AntApp.useApp()
  const navigate = useNavigate()
  const location = useLocation()

  useEffect(() => {
    bindFeedback(message, modal)
  }, [message, modal])

  useEffect(() => {
    return onSessionExpired((reason) => {
      if (reason) message.warning(reason)
      if (location.pathname !== '/login') {
        const redirect = location.pathname + location.search
        navigate(`/login?redirect=${encodeURIComponent(redirect)}`, { replace: true })
      }
    })
  }, [navigate, message, location.pathname, location.search])

  return <Outlet />
}

export function RootProviders() {
  const theme = useThemeStore((s) => s.theme)
  const init = useAuthStore((s) => s.init)
  const initialized = useAuthStore((s) => s.initialized)

  useEffect(() => {
    void init()
  }, [init])

  if (!initialized) {
    // 恢复会话 <5ms，这里只做一次空气泡，避免登录态闪烁
    return null
  }

  return (
    <ConfigProvider locale={zhCN} theme={buildTheme(theme === 'dark')}>
      <AntApp>
        <Binder />
      </AntApp>
    </ConfigProvider>
  )
}