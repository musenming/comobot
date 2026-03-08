import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('../views/LoginView.vue'),
  },
  {
    path: '/setup',
    name: 'setup',
    component: () => import('../views/SetupView.vue'),
  },
  {
    path: '/chat',
    name: 'chat',
    component: () => import('../views/ChatView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/',
    name: 'dashboard',
    component: () => import('../views/DashboardView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/workflows',
    name: 'workflows',
    component: () => import('../views/WorkflowsView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/workflows/new',
    name: 'workflow-new',
    component: () => import('../views/WorkflowEditorView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/workflows/:id/edit',
    name: 'workflow-edit',
    component: () => import('../views/WorkflowEditorView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/providers',
    name: 'providers',
    component: () => import('../views/ProvidersView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/channels',
    name: 'channels',
    component: () => import('../views/ChannelsView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/sessions',
    name: 'sessions',
    component: () => import('../views/SessionsView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/sessions/:key',
    name: 'session-detail',
    component: () => import('../views/SessionsView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/skills',
    name: 'skills',
    component: () => import('../views/SkillsView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/cron',
    name: 'cron',
    component: () => import('../views/CronView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/logs',
    name: 'logs',
    component: () => import('../views/LogsView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/memory',
    name: 'memory',
    component: () => import('../views/MemoryView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/settings',
    name: 'settings',
    component: () => import('../views/SettingsView.vue'),
    meta: { requiresAuth: true },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  const token = localStorage.getItem('token')

  // Always allow access to setup and login pages
  if (to.name === 'setup' || to.name === 'login') {
    return
  }

  // Check if first-time setup is needed
  try {
    const res = await fetch('/api/setup/status')
    if (res.ok) {
      const data = await res.json()
      if (!data.setup_complete) {
        return '/setup'
      }
    }
  } catch {
    // If we can't reach the API, fall through to normal auth check
  }

  if (to.meta.requiresAuth && !token) {
    return '/login'
  }
})

export default router
