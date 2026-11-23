/**
 * 前端测试环境准备。
 *
 * 两件事：
 * 1. 补上 jsdom 缺失、但 antd 依赖的浏览器 API（matchMedia / ResizeObserver）；
 * 2. 把 axios 适配器换成确定性桩，避免测试真的去打后端——
 *    各页面仍会走完整的「请求 → unwrap → 渲染」链路，只是返回空数据，
 *    因此能验证空态与渲染不崩，而不会因网络超时变成假失败。
 */
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

import api from '@/api/client'

if (!window.matchMedia) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false
    })
  })
}

if (!window.ResizeObserver) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ;(window as any).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
}

// 兜底：jsdom 没有 EventSource（useTaskStream 的 SSE 连接）
if (!window.EventSource) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ;(window as any).EventSource = class {
    onmessage: ((e: MessageEvent) => void) | null = null
    onerror: ((e: Event) => void) | null = null
    constructor(public url: string) {}
    close() {}
  }
}

// 兜底：jsdom 没有 IntersectionObserver（useReveal 用）
if (!window.IntersectionObserver) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ;(window as any).IntersectionObserver = class {
    constructor(private cb: (entries: unknown[]) => void) {}
    observe() {}
    unobserve() {}
    disconnect() {}
  }
}

api.defaults.adapter = async (config) => ({
  data: {},
  status: 200,
  statusText: 'OK',
  headers: {},
  config
})

afterEach(() => {
  cleanup()
})