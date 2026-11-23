/**
 * 页面渲染冒烟测试。
 *
 * 目的不是测业务逻辑（那是后端 pytest 的事），而是回答一个此前完全没有验证过的问题：
 * **「这些页面到底能不能渲染出来，会不会白屏」**。
 * 每个用例都把页面挂到真实路由上下文里渲染，断言关键文案出现。
 */
import { render, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { describe, expect, it } from 'vitest'

import { Create } from '@/pages/Create'
import { EditorPage } from '@/pages/EditorPage'
import { LoginPage } from '@/pages/LoginPage'
import { Mine } from '@/pages/Mine'
import { ProjectDetail } from '@/pages/ProjectDetail'
import { Styles } from '@/pages/Styles'
import { Workspace } from '@/pages/Workspace'
import { TaskProgress } from '@/components/TaskProgress'

function renderAt(ui: ReactElement, initialPath = '/', pattern = '*') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path={pattern} element={ui} />
      </Routes>
    </MemoryRouter>
  )
}

describe('页面渲染冒烟', () => {
  it('登录页渲染品牌区与表单', async () => {
    renderAt(<LoginPage />, '/login')
    expect(await screen.findByPlaceholderText('请输入用户名')).toBeTruthy()
    expect(await screen.findByPlaceholderText('请输入密码')).toBeTruthy()
    // 左品牌面板 + 移动端品牌区都会出现同名标题
    expect(screen.getAllByText('AI 漫剧平台').length).toBeGreaterThan(0)
  })

  it('工作台渲染 hero 与空状态', async () => {
    renderAt(<Workspace />, '/')
    expect(await screen.findByText('AI 漫剧工作台')).toBeTruthy()
    expect(await screen.findByText('暂无项目')).toBeTruthy()
  })

  it('创作页渲染灵感输入与风格区', async () => {
    renderAt(<Create />, '/create')
    expect(await screen.findByText('开始创作')).toBeTruthy()
    expect(await screen.findByLabelText('创作灵感')).toBeTruthy()
    expect(await screen.findByText('视觉风格')).toBeTruthy()
  })

  it('我的渲染账号设置', async () => {
    renderAt(<Mine />, '/mine')
    expect(await screen.findByText('账号设置')).toBeTruthy()
    expect(await screen.findByText('深色模式')).toBeTruthy()
  })

  it('风格预设渲染页头与工具栏', async () => {
    renderAt(<Styles />, '/styles')
    expect(await screen.findByText('风格预设')).toBeTruthy()
    expect(await screen.findByText('显示已停用')).toBeTruthy()
  })

  it('项目详情渲染头部与两个 Tab', async () => {
    renderAt(<ProjectDetail />, '/project/1', '/project/:id')
    expect(await screen.findByText('未命名项目')).toBeTruthy()
    expect(await screen.findByText('剧集')).toBeTruthy()
    expect(await screen.findByText('素材库')).toBeTruthy()
  })

  it('导演工作台渲染五个步骤与剧本空态', async () => {
    renderAt(<EditorPage />, '/editor/1', '/editor/:id')
    for (const label of ['剧本', '角色', '画面分镜', '配音', '成片']) {
      // 步骤导航与分区标题都会出现同名文案，因此用 findAllByText
      expect((await screen.findAllByText(label)).length).toBeGreaterThan(0)
    }
    expect(await screen.findByText(/还没有分镜脚本/)).toBeTruthy()
  })

  it('任务面板在无任务时自隐藏', () => {
    const { container } = render(<TaskProgress tasks={[]} onRetry={() => {}} onCancel={() => {}} />)
    expect(container.querySelector('.tp-wrap')).toBeNull()
  })

  it('任务面板渲染摘要与失败重试入口', async () => {
    renderAt(
      <TaskProgress
        tasks={[
          { task_id: 1, type: 'image', status: 'failed', progress: 0, error: '模型超时' },
          { task_id: 2, type: 'tts', status: 'running', progress: 40 }
        ]}
        onRetry={() => {}}
        onCancel={() => {}}
      />
    )
    // 摘要优先显示「生成中」数量
    expect(await screen.findByText('生成中 1')).toBeTruthy()
  })
})