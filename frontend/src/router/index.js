import { createRouter, createWebHistory } from 'vue-router'
import MainLayout from '../layouts/MainLayout.vue'
import { accessToken } from '../api/session'

const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('../views/AuthView.vue'),
    meta: { public: true }
  },
  {
    path: '/',
    component: MainLayout,
    children: [
      { path: '', name: 'workspace', component: () => import('../views/Workspace.vue'), meta: { requiresAuth: true } },
      { path: 'create', name: 'create', component: () => import('../views/Create.vue'), meta: { requiresAuth: true } },
      { path: 'styles', name: 'styles', component: () => import('../views/Styles.vue'), meta: { requiresAuth: true } },
      { path: 'mine', name: 'mine', component: () => import('../views/Mine.vue'), meta: { requiresAuth: true } },
      { path: 'project/:id', name: 'project-detail', component: () => import('../views/ProjectDetail.vue'), meta: { requiresAuth: true } }
    ]
  },
  {
    path: '/editor/:id',
    name: 'editor',
    component: () => import('../views/Editor.vue'),
    meta: { requiresAuth: true }
  },
  { path: '/:pathMatch(.*)*', redirect: '/' }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to) => {
  // 令牌真源在 api/session.js（内存 ref），启动时由 main.js init() 恢复
  const loggedIn = !!accessToken.value
  if (to.meta.requiresAuth && !loggedIn) {
    return { path: '/login', query: to.fullPath === '/' ? {} : { redirect: to.fullPath } }
  }
  if (to.path === '/login' && loggedIn) {
    return { path: '/' }
  }
  return true
})

export default router
