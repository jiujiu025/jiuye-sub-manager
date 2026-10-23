import { createRouter, createWebHistory } from 'vue-router'

import LoginView from '../views/LoginView.vue'
import ManagerLoginView from '../views/ManagerLoginView.vue'

// 登录页保持首屏同步加载，其余业务页按路由拆包，避免用户登录前下载整个后台。
const DashboardView = () => import('../views/DashboardView.vue')
const HealthDashboardView = () => import('../views/HealthDashboardView.vue')
const SourcesView = () => import('../views/SourcesView.vue')
const NodesView = () => import('../views/NodesView.vue')
const PackagesView = () => import('../views/PackagesView.vue')
const LogsView = () => import('../views/LogsView.vue')
const SystemSettingsView = () => import('../views/SystemSettingsView.vue')
const ProfileView = () => import('../views/ProfileView.vue')
const MySubscriptionsView = () => import('../views/MySubscriptionsView.vue')
const UsersView = () => import('../views/UsersView.vue')
const CustomersView = () => import('../views/CustomersView.vue')
const SubscriptionsView = () => import('../views/SubscriptionsView.vue')
const ManagerDashboardView = () => import('../views/ManagerDashboardView.vue')
const NotificationsView = () => import('../views/NotificationsView.vue')
const ThreeXUIServersView = () => import('../views/ThreeXUIServersView.vue')

const routes = [
  { path: '/login', component: LoginView },
  { path: '/manager-login', component: ManagerLoginView },
  {
    path: '/',
    component: DashboardView,
    meta: { auth: true, admin: true, title: '概览', subtitle: '管理你的订阅、节点与套餐' }
  },
  {
    path: '/health',
    component: HealthDashboardView,
    meta: { auth: true, staff: true, title: '健康大屏', subtitle: '查看自己客户线路的健康状态' }
  },
  {
    path: '/sources',
    component: SourcesView,
    meta: { auth: true, admin: true, title: '来源管理', subtitle: '管理上游订阅地址与解析状态' }
  },
  {
    path: '/packages',
    component: PackagesView,
    meta: { auth: true, admin: true, title: '套餐管理', subtitle: '通过规则组合来源并生成独立订阅' }
  },
  {
    path: '/nodes',
    component: NodesView,
    meta: { auth: true, admin: true, title: '资源池', subtitle: '管理上游订阅节点与导入外部节点' }
  },
  {
    path: '/three-xui',
    component: ThreeXUIServersView,
    meta: { auth: true, admin: true, title: '3x-ui 服务器', subtitle: '管理转发目标服务器与异步任务' }
  },
  {
    path: '/logs',
    component: LogsView,
    meta: { auth: true, admin: true, title: '系统日志', subtitle: '查看同步、订阅与操作记录' }
  },
  {
    path: '/manager-logs',
    component: LogsView,
    meta: { auth: true, staff: true, title: '系统日志', subtitle: '查看自己的操作记录' }
  },
  {
    path: '/settings',
    component: SystemSettingsView,
    meta: { auth: true, admin: true, title: '系统设置', subtitle: '调整同步、缓存与去重优先级' }
  },
  {
    path: '/profile',
    component: ProfileView,
    meta: { auth: true, admin: true, title: '账号设置', subtitle: '更新当前管理员资料' }
  },
  {
    path: '/my-subscriptions',
    component: MySubscriptionsView,
    meta: { auth: true, title: '我的订阅', subtitle: '查看你名下的套餐和订阅地址' }
  },
  {
    path: '/manager',
    component: ManagerDashboardView,
    meta: { auth: true, staff: true, title: '经理工作台', subtitle: '客户、订阅与到期提醒一站式处理' }
  },
  {
    path: '/notifications',
    component: NotificationsView,
    meta: { auth: true, staff: true, title: '通知中心', subtitle: '集中处理到期、同步和系统提醒' }
  },
  {
    path: '/users',
    component: UsersView,
    meta: { auth: true, admin: true, title: '用户管理', subtitle: '创建用户并分配订阅套餐' }
  },
  {
    path: '/managers',
    component: UsersView,
    meta: { auth: true, admin: true, title: '客户经理', subtitle: '创建、停用与管理销售经理账号' }
  },
  {
    path: '/customers',
    component: CustomersView,
    meta: { auth: true, staff: true, title: '客户管理', subtitle: '维护客户资料与购买关系' }
  },
  {
    path: '/subscriptions',
    component: SubscriptionsView,
    meta: { auth: true, staff: true, title: '订阅管理', subtitle: '管理员管理全部订阅，经理管理自己负责的订阅' }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to) => {
  const token = localStorage.getItem('admin_token')
  const role = localStorage.getItem('admin_role')
  if (to.meta.auth && !token) {
    return '/login'
  }
  if (to.meta.admin && role !== 'admin') {
    return '/my-subscriptions'
  }
  if (to.meta.staff && !['admin', 'manager'].includes(role)) {
    return '/my-subscriptions'
  }
  if (to.path === '/login' && token) {
    return role === 'admin' ? '/' : role === 'manager' ? '/manager' : '/my-subscriptions'
  }
  if (to.path === '/manager-login' && token) {
    return role === 'manager' ? '/manager' : role === 'admin' ? '/' : '/my-subscriptions'
  }
  return true
})

export default router
