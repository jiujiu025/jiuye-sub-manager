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
  {
    path: '/',
    component: DashboardView,
    meta: { auth: true, title: '概览', subtitle: '管理你的订阅、节点与套餐' }
  },
  {
    path: '/sources',
    component: SourcesView,
    meta: { auth: true, title: '来源管理', subtitle: '管理上游订阅地址与解析状态' }
  },
  {
    path: '/packages',
    component: PackagesView,
    meta: { auth: true, title: '套餐管理', subtitle: '通过规则组合来源并生成独立订阅' }
  },
  {
    path: '/nodes',
    component: NodesView,
    meta: { auth: true, title: '节点管理', subtitle: '查看统一节点池并导入自有节点' }
  },
  {
    path: '/logs',
    component: LogsView,
    meta: { auth: true, title: '系统日志', subtitle: '查看同步、订阅与操作记录' }
  },
  {
    path: '/settings',
    component: SystemSettingsView,
    meta: { auth: true, title: '系统设置', subtitle: '调整同步、缓存与去重优先级' }
  },
  {
    path: '/profile',
    component: ProfileView,
    meta: { auth: true, title: '修改密码', subtitle: '更新当前管理员密码' }
  }
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
