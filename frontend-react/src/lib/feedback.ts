/**
 * 全局提示与确认框的绑定层。
 *
 * 为什么不直接用 antd 的 `message` 静态方法：静态方法拿不到 ConfigProvider 的
 * 主题上下文（antd 会告警 "Static function can not consume context"），
 * 深色主题下弹窗会是白底。这里把 <App> 内的实例注册进来，
 * 使得 axios 拦截器这类非组件代码也能用上主题化的反馈。
 */
import type { MessageInstance } from 'antd/es/message/interface'
import type { HookAPI as ModalHookAPI } from 'antd/es/modal/useModal'

let messageApi: MessageInstance | null = null
let modalApi: ModalHookAPI | null = null

export function bindFeedback(m: MessageInstance, modal: ModalHookAPI): void {
  messageApi = m
  modalApi = modal
}

export const toast = {
  success(content: string): void {
    messageApi?.success(content)
  },
  error(content: string): void {
    messageApi?.error(content)
  },
  warning(content: string, duration = 5): void {
    messageApi?.warning(content, duration)
  },
  info(content: string): void {
    messageApi?.info(content)
  }
}

export function getModal(): ModalHookAPI | null {
  return modalApi
}

export interface ConfirmOptions {
  title: string
  content: string
  okText?: string
  cancelText?: string
  danger?: boolean
}

/**
 * 把 antd 的命令式 confirm 桥接成 Promise<boolean>。
 *
 * 坑：`modal.confirm()` 返回的是 { destroy, update } 控制器对象，**不是 Promise**。
 * 直接 `await modal.confirm(...)` 拿到的是 truthy 对象，点"取消"也会继续往下执行。
 * 必须显式接 onOk / onCancel。
 */
export function confirmDialog(opts: ConfirmOptions): Promise<boolean> {
  const api = modalApi
  if (!api) return Promise.resolve(false)
  return new Promise<boolean>((resolve) => {
    api.confirm({
      title: opts.title,
      content: opts.content,
      okText: opts.okText ?? '确定',
      cancelText: opts.cancelText ?? '取消',
      okButtonProps: opts.danger ? { danger: true } : undefined,
      onOk: () => resolve(true),
      onCancel: () => resolve(false)
    })
  })
}