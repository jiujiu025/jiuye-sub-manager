import { createRouter, createWebHistory } from 'vue-router'

import LoginView from '../views/LoginView.vue'
import DashboardView from '../views/DashboardView.vue'
import SourcesView from '../views/SourcesView.vue'
import NodesView from '../views/NodesView.vue'
import PackagesView from '../views/PackagesView.vue'
import LogsView from '../views/LogsView.vue'
import SystemSettingsView from '../views/SystemSettingsView.vue'
import ProfileView from '../views/ProfileView.vue'

const routes = [
  { path: '/login', component: LoginView },
  { path: '/', component: DashboardView, meta: { auth: true } },
  { path: '/sources', component: SourcesView, meta: { auth: true } },
  { path: '/nodes', component: NodesView, meta: { auth: true } },
  { path: '/packages', component: PackagesView, meta: { auth: true } },
  { path: '/logs', component: LogsView, meta: { auth: true } },
  { path: '/settings', component: SystemSettingsView, meta: { auth: true } },
  { path: '/profile', component: ProfileView, meta: { auth: true } }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to) => {
  const token = localStorage.getItem('admin_token')
  if (to.meta.auth && !token) {
    return '/login'
  }
  if (to.path === '/login' && token) {
    return '/'
  }
  return true
})

export default router
