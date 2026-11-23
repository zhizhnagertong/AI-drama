/**
 * 数据层测试：验证请求拦截、无感刷新、SSE 任务流与全局反馈的边界行为。
 * 用 axios adapter 打桩而非网络请求，因此不需要后端，也不依赖真实定时器。
 */
import axios from 'axios'
import type { AxiosError, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import api, { refreshOnce, unwrap } from '@/api/client'
import { bindFeedback, confirmDialog } from '@/lib/feedback'
import { emitSessionExpired, onSessionExpired } from '@/lib/sessionEvents'
import { useTaskStream } from '@/hooks/useTaskStream'
import { useSessionStore } from '@/store/session'

const ok = (data: unknown, config: InternalAxiosRequestConfig): AxiosResponse => ({
  data,
  status: 200,
  statusText: 'OK',
  headers: {},
  config
})

function httpError(status: number, config: InternalAxiosRequestConfig): AxiosError {
  const e = new Error(`HTTP ${status}`) as AxiosError
  e.config = config
  e.response = { status, data: {}, statusText: '', headers: {}, config }
  return e
}

let originalApiAdapter: typeof api.defaults.adapter
let originalAxiosAdapter: typeof axios.defaults.adapter
let messageCalls: string[] = []
let lastConfirm: { onOk: () => void; onCancel: () => void } | null = null

beforeEach(() => {
  originalApiAdapter = api.defaults.adapter
  originalAxiosAdapter = axios.defaults.adapter
  messageCalls = []
  lastConfirm = null
  useSessionStore.getState().clear()
  bindFeedback(
    {
      success: (c: string) => void messageCalls.push(`success:${c}`),
      error: (c: string) => void messageCalls.push(`error:${c}`),
      warning: (c: string) => void messageCalls.push(`warning:${c}`),
      info: (c: string) => void messageCalls.push(`info:${c}`),
      open: () => ({}) as never,
      destroy: () => {}
    } as never,
    {
      confirm: (opts: { onOk: () => void; onCancel: () => void }) => {
        lastConfirm = opts
        return { destroy() {}, update() {} }
      }
    } as never
  )
})

afterEach(() => {
  api.defaults.adapter = originalApiAdapter
  axios.defaults.adapter = originalAxiosAdapter
  useSessionStore.getState().clear()
  vi.restoreAllMocks()
})

function login() {
  useSessionStore.getState().persist({
    access: 'old-access',
    refresh: 'old-refresh',
    expiresIn: 3600,
    refreshExpiresIn: 7 * 24 * 3600
  })
}

describe('unwrap', () => {
  it('拆开 {code,message,data} 信封', () => {
    expect(unwrap({ data: { code: 0, message: 'ok', data: { id: 7 } } } as AxiosResponse)).toEqual({
      id: 7
    })
  })

  it('保留裸 payload，且不会误拆含 id 的实体对象', () => {
    expect(unwrap({ data: { id: 7, title: 'x' } } as AxiosResponse)).toEqual({ id: 7, title: 'x' })
    expect(unwrap({ data: { code: 0, data: { id: 7 }, id: 9 } } as AxiosResponse)).toEqual({
      code: 0,
      data: { id: 7 },
      id: 9
    })
  })
})

describe('refreshOnce', () => {
  it('并发调用共享同一个 in-flight，只发一次刷新', async () => {
    login()
    let calls = 0
    axios.defaults.adapter = async (config) => {
      calls++
      await new Promise((r) => setTimeout(r, 10))
      return ok({ access_token: 'new-access', expires_in: 3600 }, config)
    }

    const [a, b] = await Promise.all([refreshOnce(), refreshOnce()])
    expect(calls).toBe(1)
    expect(a).toBe('new-access')
    expect(b).toBe('new-access')
    expect(useSessionStore.getState().accessToken).toBe('new-access')
  })

  it('无 refresh token 时直接拒绝', async () => {
    await expect(refreshOnce()).rejects.toThrow('NO_REFRESH')
  })
})

describe('401 拦截与会话清理', () => {
  it('刷新因网络原因失败（无 response）→ 保留会话', async () => {
    login()
    api.defaults.adapter = async (config) => {
      throw httpError(401, config)
    }
    axios.defaults.adapter = async () => {
      throw new Error('Network Error') // 无 response
    }

    await expect(api.get('/projects')).rejects.toBeDefined()
    expect(useSessionStore.getState().accessToken).toBe('old-access')
  })

  it('刷新被服务端明确拒绝（有 response）→ 清空会话并广播', async () => {
    login()
    api.defaults.adapter = async (config) => {
      throw httpError(401, config)
    }
    axios.defaults.adapter = async (config) => {
      throw httpError(401, config)
    }
    const spy = vi.fn()
    const off = onSessionExpired(spy)

    await expect(api.get('/projects')).rejects.toBeDefined()
    expect(useSessionStore.getState().accessToken).toBe('')
    expect(spy).toHaveBeenCalledTimes(1)
    off()
  })

  it('refresh 已过期（NO_REFRESH）→ 清空会话，避免用户卡在 401', async () => {
    useSessionStore.getState().persist({
      access: 'old-access',
      refresh: 'old-refresh',
      expiresIn: 3600,
      refreshExpiresIn: -1, // 已过期
    })
    api.defaults.adapter = async (config) => {
      throw httpError(401, config)
    }
    const spy = vi.fn()
    const off = onSessionExpired(spy)

    await expect(api.get('/projects')).rejects.toBeDefined()
    expect(useSessionStore.getState().accessToken).toBe('')
    expect(spy).toHaveBeenCalledTimes(1)
    off()
  })

  it('认证类接口的 401 不触发刷新', async () => {
    login()
    let refreshCalls = 0
    api.defaults.adapter = async (config) => {
      throw httpError(401, config)
    }
    axios.defaults.adapter = async (config) => {
      refreshCalls++
      return ok({ access_token: 'x' }, config)
    }

    await expect(api.post('/auth/login', {})).rejects.toBeDefined()
    expect(refreshCalls).toBe(0)
    expect(useSessionStore.getState().accessToken).toBe('old-access')
  })
})

describe('confirmDialog', () => {
  it('onOk 才 resolve(true)，点取消 resolve(false)', async () => {
    const okPromise = confirmDialog({ title: 't', content: 'c' })
    expect(lastConfirm).not.toBeNull()
    lastConfirm!.onOk()
    await expect(okPromise).resolves.toBe(true)

    const cancelPromise = confirmDialog({ title: 't', content: 'c' })
    lastConfirm!.onCancel()
    await expect(cancelPromise).resolves.toBe(false)
  })

  it('未绑定 modal 时安全返回 false', async () => {
    bindFeedback({} as never, null as never)
    await expect(confirmDialog({ title: 't', content: 'c' })).resolves.toBe(false)
  })
})

describe('useTaskStream', () => {
  class MockEventSource {
    static last: MockEventSource | null = null
    onmessage: ((e: MessageEvent) => void) | null = null
    onerror: ((e: Event) => void) | null = null
    closed = false
    constructor(public url: string) {
      MockEventSource.last = this
    }
    close() {
      this.closed = true
    }
    emit(data: unknown) {
      this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent)
    }
  }

  it('SSE 事件里的 task_update 不被当成任务类型', () => {
    login()
    const Original = window.EventSource
    // @ts-expect-error 测试桩只需实现用到的接口
    window.EventSource = MockEventSource

    const { result, unmount } = renderHook(() => useTaskStream('1'))
    const es = MockEventSource.last!
    expect(es.url).toContain('/projects/1/stream?token=')

    act(() => {
      es.emit({ task_id: 42, type: 'task_update', task_type: 'image', status: 'succeeded' })
    })

    expect(result.current.tasks['42'].type).toBe('image')
    expect(messageCalls).toContain('success:画面生成完成')

    unmount()
    expect(es.closed).toBe(true)
    window.EventSource = Original
  })

  it('任务失败时按真实任务类型聚合提示', () => {
    login()
    const Original = window.EventSource
    // @ts-expect-error 测试桩只需实现用到的接口
    window.EventSource = MockEventSource

    const { result, unmount } = renderHook(() => useTaskStream('1'))
    act(() => {
      MockEventSource.last!.emit({
        task_id: 7,
        type: 'task_update',
        task_type: 'tts',
        status: 'failed',
        error: '模型超时'
      })
    })

    expect(result.current.failedTasks).toHaveLength(1)
    expect(messageCalls.some((c) => c.includes('配音合成失败'))).toBe(true)

    unmount()
    window.EventSource = Original
  })
})

describe('emitSessionExpired', () => {
  it('单个监听器抛错不影响其他监听器', () => {
    const calls: string[] = []
    const off1 = onSessionExpired(() => {
      throw new Error('boom')
    })
    const off2 = onSessionExpired((r) => calls.push(r))
    emitSessionExpired('expired')
    expect(calls).toEqual(['expired'])
    off1()
    off2()
  })
})
