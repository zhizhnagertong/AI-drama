/** 会话失效广播：让非组件代码（axios 拦截器）通知 React 层跳登录页。 */

type Listener = (reason: string) => void

const listeners = new Set<Listener>()

/** 订阅会话失效，返回取消订阅函数 */
export function onSessionExpired(fn: Listener): () => void {
  listeners.add(fn)
  return () => {
    listeners.delete(fn)
  }
}

export function emitSessionExpired(reason = ''): void {
  listeners.forEach((fn) => {
    try {
      fn(reason)
    } catch {
      /* 单个监听器异常不影响其他 */
    }
  })
}