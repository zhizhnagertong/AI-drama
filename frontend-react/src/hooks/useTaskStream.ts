/**
 * SSE 任务进度流（移植自 Editor.vue 的 connectStream / handleTaskEvent / showErrorOnce / scheduleRefresh）。
 *
 * 原实现的三层保护在 React 里必须全部保留：
 * 1) 连接前若 access 临期（<=60s）先无感续期 —— EventSource 无法带 Header，
 *    否则令牌过期会触发 401 重连风暴；
 * 2) onerror 关闭后 3s 重连；
 * 3) 卸载时关闭连接并清理所有定时器 —— StrictMode 双挂载时尤其重要。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { refreshOnce } from '@/api/client'
import { editorApi } from '@/api/editor'
import { toast } from '@/lib/feedback'
import { taskTypeLabel } from '@/lib/entities'
import { useSessionStore } from '@/store/session'
import type { TaskInfo } from '@/types'

const ACTIVE_STATUS = ['pending', 'queued', 'running', 'processing']

export interface TaskStream {
  tasks: Record<string, TaskInfo>
  taskList: TaskInfo[]
  activeCount: number
  failedTasks: TaskInfo[]
  retry: (t: TaskInfo) => Promise<void>
  cancel: (t: TaskInfo) => Promise<void>
  retryAllFailed: () => Promise<void>
}

export function useTaskStream(projectId: string, onSettled?: () => void): TaskStream {
  const [tasks, setTasks] = useState<Record<string, TaskInfo>>({})

  // tasks 的镜像：SSE 回调需要读最新字典，又不能把 tasks 放进连接 effect 的依赖，
  // 否则每个事件都会重建连接。在每次更新里同步写 ref，避免独立 effect 的时序滞后。
  const tasksRef = useRef(tasks)
  function writeTasks(next: Record<string, TaskInfo>) {
    tasksRef.current = next
    setTasks(next)
  }

  // 回调放 ref，避免它变化导致整条连接重建
  const onSettledRef = useRef(onSettled)
  useEffect(() => {
    onSettledRef.current = onSettled
  }, [onSettled])

  useEffect(() => {
    let closed = false
    let es: EventSource | null = null
    let reconnectTimer: number | null = null
    let refreshTimer: number | null = null

    // 同类错误合并提示：批量失败时避免刷屏（跨渲染持久，必须用闭包变量而非 state）
    let lastErrText = ''
    let lastErrAt = 0
    let errCount = 0
    let errTimer: number | null = null

    function showErrorOnce(text: string) {
      const now = Date.now()
      if (text === lastErrText && now - lastErrAt < 4000) {
        errCount++
        lastErrAt = now
        if (errTimer) window.clearTimeout(errTimer)
        errTimer = window.setTimeout(() => {
          toast.error(`${text}（同类失败共 ${errCount + 1} 次）`)
          errCount = 0
        }, 2500)
        return
      }
      lastErrText = text
      lastErrAt = now
      errCount = 0
      toast.error(text)
    }

    function scheduleRefresh() {
      if (refreshTimer) window.clearTimeout(refreshTimer)
      refreshTimer = window.setTimeout(() => onSettledRef.current?.(), 500)
    }

    function handleTaskEvent(data: Record<string, unknown>) {
      if (!data || typeof data !== 'object') return
      const tid = (data.task_id ?? data.id) as number | string | undefined
      if (!tid) return

      const base = tasksRef.current[String(tid)] || { task_id: tid }
      // SSE 里 type 是事件名（task_update），真实任务类型在 task_type；轮询接口则直接是 type
      const ttype =
        (data.task_type as string) ??
        (data.type === 'task_update' ? base.type : (data.type as string))

      writeTasks({
        ...tasksRef.current,
        [String(tid)]: { ...base, ...data, task_id: tid, type: ttype } as TaskInfo
      })

      if (data.status === 'succeeded') {
        toast.success(`${taskTypeLabel(ttype)}完成`)
        scheduleRefresh()
      } else if (data.status === 'failed') {
        showErrorOnce(`${taskTypeLabel(ttype)}失败：${(data.error as string) || '请重试'}`)
      }
    }

    async function connect() {
      if (closed) return
      es?.close()
      es = null

      const { accessToken, accessExpiresAt } = useSessionStore.getState()
      if (!accessToken) return
      if (accessExpiresAt && accessExpiresAt <= Date.now() + 60_000) {
        try {
          await refreshOnce()
        } catch {
          /* 刷新失败由请求层广播处理，仍用当前令牌尝试 */
        }
      }
      if (closed) return
      const token = useSessionStore.getState().accessToken
      if (!token) return

      es = new EventSource(
        `/api/v1/projects/${projectId}/stream?token=${encodeURIComponent(token)}`
      )
      es.onmessage = (e) => {
        let data: Record<string, unknown>
        try {
          data = JSON.parse(e.data) as Record<string, unknown>
        } catch {
          return
        }
        handleTaskEvent(data)
      }
      es.onerror = () => {
        es?.close()
        es = null
        if (!closed) reconnectTimer = window.setTimeout(() => void connect(), 3000)
      }
    }

    void connect()

    return () => {
      closed = true
      es?.close()
      if (reconnectTimer) window.clearTimeout(reconnectTimer)
      if (refreshTimer) window.clearTimeout(refreshTimer)
      if (errTimer) window.clearTimeout(errTimer)
    }
  }, [projectId])

  const taskList = useMemo(() => Object.values(tasks), [tasks])
  const activeCount = useMemo(
    () => taskList.filter((t) => ACTIVE_STATUS.includes(String(t.status))).length,
    [taskList]
  )
  const failedTasks = useMemo(() => taskList.filter((t) => t.status === 'failed'), [taskList])

  const retry = useCallback(async (t: TaskInfo) => {
    try {
      await editorApi.retryTask(t.task_id)
      writeTasks({
        ...tasksRef.current,
        [String(t.task_id)]: {
          ...tasksRef.current[String(t.task_id)],
          status: 'pending',
          error: ''
        }
      })
      toast.success('已重新提交任务')
    } catch {
      /* 拦截器已提示 */
    }
  }, [])

  const cancel = useCallback(async (t: TaskInfo) => {
    try {
      await editorApi.cancelTask(t.task_id)
      writeTasks({
        ...tasksRef.current,
        [String(t.task_id)]: { ...tasksRef.current[String(t.task_id)], status: 'canceled' }
      })
      toast.success('已取消任务')
    } catch {
      /* 拦截器已提示 */
    }
  }, [])

  const retryAllFailed = useCallback(async () => {
    for (const t of failedTasks) await retry(t)
  }, [failedTasks, retry])

  return { tasks, taskList, activeCount, failedTasks, retry, cancel, retryAllFailed }
}