import { AuthLeftPanel } from '@/components/auth/AuthLeftPanel'
import { AuthRightPanel } from '@/components/auth/AuthRightPanel'

/** 登录注册父页：左侧品牌面板 + 右侧表单容器（对齐前端组件结构图）。 */
export function LoginPage() {
  return (
    <div className="auth-screen">
      <AuthLeftPanel />
      <AuthRightPanel />
    </div>
  )
}