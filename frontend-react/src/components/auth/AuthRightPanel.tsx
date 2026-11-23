/** 右侧表单容器：登录/注册 Tab 切换 + 忘记密码弹窗托管。 */
import { useState } from 'react'

import { AuthLeftPanel } from './AuthLeftPanel'
import { ForgetPasswordModal } from './ForgetPasswordModal'
import { LoginForm } from './LoginForm'
import { RegisterForm } from './RegisterForm'

type Tab = 'login' | 'register'

export function AuthRightPanel() {
  const [tab, setTab] = useState<Tab>('login')
  const [forgetOpen, setForgetOpen] = useState(false)
  const [prefill, setPrefill] = useState('')

  /** 注册成功后：回填用户名并切回登录（不自动登录） */
  function onRegistered(username: string) {
    setPrefill(username)
    setTab('login')
  }

  /** 找回密码成功后同样回填用户名 */
  function onResetDone(username: string) {
    if (username) setPrefill(username)
    setTab('login')
  }

  return (
    <section className="auth-right">
      <div className="right-top-line" aria-hidden="true" />
      <div className="auth-wrap">
        <div className="brand-mobile">
          <span className="logo" aria-hidden="true">
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
          <h1 className="name">AI 漫剧平台</h1>
          <p className="slogan">一句话灵感，AI 帮你拍成漫剧</p>
        </div>

        <div className="auth-card">
          {/* 胶囊 Tab（设计规范 12.3：胶囊形 + 选中高亮） */}
          <div className="tabs" role="tablist" aria-label="登录或注册">
            <button
              type="button"
              role="tab"
              className={tab === 'login' ? 'tab active' : 'tab'}
              aria-selected={tab === 'login'}
              onClick={() => setTab('login')}
            >
              登录
            </button>
            <button
              type="button"
              role="tab"
              className={tab === 'register' ? 'tab active' : 'tab'}
              aria-selected={tab === 'register'}
              onClick={() => setTab('register')}
            >
              注册
            </button>
          </div>

          {/* Vue 版用 <Transition mode="out-in">，这里用 key 重挂载 + CSS 入场动画 */}
          <div key={tab} className="pane-enter">
            {tab === 'login' ? (
              <LoginForm
                prefill={prefill}
                onSwitch={() => setTab('register')}
                onForget={() => setForgetOpen(true)}
              />
            ) : (
              <RegisterForm onSwitch={() => setTab('login')} onRegistered={onRegistered} />
            )}
          </div>
        </div>

        <p className="foot">登录即代表同意《AI 生成内容使用规范》</p>
      </div>

      <ForgetPasswordModal
        open={forgetOpen}
        onClose={() => setForgetOpen(false)}
        onDone={onResetDone}
      />
    </section>
  )
}

/** 供登录页复用的左栏（保持 import 路径集中） */
export { AuthLeftPanel }