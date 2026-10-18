<template>
  <router-view v-if="isPublicRoute" />
  <div v-else class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">
          <el-icon :size="18"><Cloudy /></el-icon>
        </div>
        <div>
          <div class="brand-name">玖玖云</div>
          <div class="brand-sub">运营控制台</div>
        </div>
      </div>

      <div class="workspace-note">
        <span class="workspace-kicker">WORKSPACE</span>
        <strong>{{ isAdmin ? '管理员工作区' : isManager ? '经理工作区' : '客户工作区' }}</strong>
        <span class="workspace-caption">节点与订阅业务中心</span>
      </div>

      <nav class="nav">
        <div v-for="group in navGroups" :key="group.title" class="nav-group">
          <div class="nav-group-title">{{ group.title }}</div>
          <router-link
            v-for="item in group.items"
            :key="item.path"
            :to="item.path"
            class="nav-item"
            :class="{ active: isActive(item.path) }"
          >
            <el-icon><component :is="item.icon" /></el-icon>
            <span>{{ item.label }}</span>
          </router-link>
        </div>
      </nav>

      <div class="sidebar-footer">
        <div class="user">
          <el-avatar :size="32" class="user-avatar">
            {{ authStore.username.slice(0, 1).toUpperCase() }}
          </el-avatar>
          <div class="user-meta">
            <div class="user-name">{{ authStore.username }}</div>
            <div class="user-role">{{ isAdmin ? '管理员' : isManager ? '经理' : '用户' }}</div>
          </div>
        </div>
        <el-button text class="logout-btn" @click="authStore.logout()">
          退出登录
        </el-button>
      </div>
    </aside>

    <div class="main-area">
      <header class="topbar">
        <el-button
          v-if="isMobile"
          text
          class="menu-btn"
          aria-label="打开导航菜单"
          @click="drawerOpen = true"
        >
          <el-icon :size="18"><Menu /></el-icon>
        </el-button>
        <div class="topbar-title">
          <span class="topbar-kicker">{{ isAdmin ? 'ADMIN CONSOLE' : isManager ? 'MANAGER DESK' : 'CUSTOMER PORTAL' }}</span>
          <h1 class="page-title">{{ pageTitle }}</h1>
          <p class="page-subtitle">{{ pageSubtitle }}</p>
        </div>
        <div class="topbar-actions">
          <el-popover v-if="isAdmin || isManager" placement="bottom-end" :width="360" trigger="click" @show="loadNotifications">
            <template #reference>
              <el-badge :value="unreadCount" :hidden="unreadCount === 0" :max="99" class="notification-badge">
                <el-button text class="notification-btn" aria-label="打开站内收件箱">
                  <el-icon :size="18"><Bell /></el-icon>
                </el-button>
              </el-badge>
            </template>
            <div class="inbox-header">
              <strong>站内收件箱</strong>
              <div class="inbox-header-actions">
                <el-button v-if="unreadCount" link type="primary" @click="markAllRead">全部已读</el-button>
                <el-button link type="primary" @click="router.push('/notifications')">查看全部</el-button>
              </div>
            </div>
            <div v-if="notifications.length" class="inbox-list">
              <button v-for="item in notifications" :key="item.id" class="inbox-item" :class="{ unread: !item.read_at }" @click="readNotification(item)">
                <span class="inbox-dot" />
                <span class="inbox-copy"><strong>{{ item.title }}</strong><span>{{ item.content }}</span><small>{{ formatNotificationTime(item.created_at) }}</small></span>
              </button>
            </div>
            <el-empty v-else description="暂无通知" :image-size="64" />
          </el-popover>
          <div class="system-status">
            <span class="status-pulse" />
            数据面在线
          </div>
          <el-button @click="reloadPage">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </header>
      <main class="content">
        <router-view />
      </main>
    </div>

    <el-drawer
      v-model="drawerOpen"
      direction="ltr"
      size="260px"
      :with-header="false"
      class="mobile-drawer"
    >
      <div class="mobile-brand">
        <div class="brand-mark">
          <el-icon :size="18"><Cloudy /></el-icon>
        </div>
        <div class="brand-name">玖玖云 · 控制台</div>
      </div>
      <nav class="nav">
        <div v-for="group in navGroups" :key="group.title" class="nav-group">
          <div class="nav-group-title">{{ group.title }}</div>
          <router-link
            v-for="item in group.items"
            :key="item.path"
            :to="item.path"
            class="nav-item"
            :class="{ active: isActive(item.path) }"
            @click="drawerOpen = false"
          >
            <el-icon><component :is="item.icon" /></el-icon>
            <span>{{ item.label }}</span>
          </router-link>
        </div>
      </nav>
      <div class="sidebar-footer">
        <div class="user">
          <el-avatar :size="32" class="user-avatar">
            {{ authStore.username.slice(0, 1).toUpperCase() }}
          </el-avatar>
          <div class="user-meta">
            <div class="user-name">{{ authStore.username }}</div>
            <div class="user-role">{{ isAdmin ? '管理员' : isManager ? '经理' : '用户' }}</div>
          </div>
        </div>
        <el-button text class="logout-btn" @click="authStore.logout()">
          退出登录
        </el-button>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { listNotifications, markAllNotificationsRead, markNotificationRead } from './api'
import { useAuthStore } from './stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const drawerOpen = ref(false)
const isMobile = ref(false)
const isAdmin = computed(() => authStore.role === 'admin')
const isManager = computed(() => authStore.role === 'manager')
const notifications = ref([])
const unreadCount = ref(0)
const notificationLoading = ref(false)
let notificationTimer
const isPublicRoute = computed(() => ['/login', '/manager-login'].includes(route.path))

const adminNavGroups = [
  {
    title: '工作台',
    items: [
      { path: '/', label: '概览', icon: 'Odometer' },
      { path: '/health', label: '健康大屏', icon: 'DataLine' }
    ]
  },
  {
    title: '资源',
    items: [
      { path: '/sources', label: '来源管理', icon: 'Connection' },
      { path: '/packages', label: '套餐管理', icon: 'Tickets' },
      { path: '/customers', label: '客户管理', icon: 'UserFilled' },
       { path: '/subscriptions', label: '订阅管理', icon: 'List' },
      { path: '/managers', label: '客户经理', icon: 'UserFilled' },
      { path: '/nodes', label: '资源池', icon: 'Grid' }
      ,{ path: '/three-xui', label: '3x-ui 服务器', icon: 'Connection' }
    ]
  },
  {
    title: '系统',
    items: [
      { path: '/notifications', label: '通知中心', icon: 'Bell' },
      { path: '/logs', label: '系统日志', icon: 'Document' },
      { path: '/settings', label: '系统设置', icon: 'Setting' },
      { path: '/users', label: '用户管理', icon: 'User' },
      { path: '/profile', label: '修改密码', icon: 'Lock' }
    ]
  }
]

const userNavGroups = [
  {
    title: '账户',
    items: [{ path: '/my-subscriptions', label: '我的订阅', icon: 'Tickets' }]
  }
]

const managerNavGroups = [
  {
    title: '业务',
    items: [
      { path: '/manager', label: '经理工作台', icon: 'DataAnalysis' },
      { path: '/customers', label: '我的客户', icon: 'UserFilled' },
       { path: '/subscriptions', label: '订阅管理', icon: 'List' },
      { path: '/notifications', label: '通知中心', icon: 'Bell' }
    ]
  }
]

const navGroups = computed(() => {
  if (isAdmin.value) return adminNavGroups
  if (isManager.value) return managerNavGroups
  return userNavGroups
})

const pageTitle = computed(() => route.meta.title || '控制台')
const pageSubtitle = computed(() => route.meta.subtitle || '')

function isActive(path) {
  if (path === '/') {
    return route.path === '/'
  }
  return route.path.startsWith(path)
}

function reloadPage() {
  window.location.reload()
}

async function loadNotifications() {
  if (!isAdmin.value && !isManager.value) return
  if (document.hidden) return
  if (notificationLoading.value) return
  notificationLoading.value = true
  try {
    const { data } = await listNotifications(
      { status: 'all', page: 1, page_size: 5 },
      { silent: true },
    )
    notifications.value = data.items
    unreadCount.value = data.unread_count
  } catch {
    // 全局壳层不阻断页面操作，接口错误由请求拦截器统一提示。
  } finally {
    notificationLoading.value = false
  }
}

async function readNotification(item) {
  try {
    if (!item.read_at) {
      await markNotificationRead(item.id)
      item.read_at = new Date().toISOString()
      unreadCount.value = Math.max(0, unreadCount.value - 1)
    }
    const targetRoutes = {
      subscription: '/subscriptions',
      source: '/sources',
      package: '/packages',
      customer: '/customers',
      node: '/nodes',
    }
    const targetPath = targetRoutes[item.target_type]
    router.push(targetPath && item.target_id ? { path: targetPath, query: { focus: String(item.target_id) } } : '/notifications')
  } catch {
    ElMessage.error('通知状态更新失败')
  }
}

async function markAllRead() {
  try {
    await markAllNotificationsRead()
    notifications.value.forEach((item) => { item.read_at = item.read_at || new Date().toISOString() })
    unreadCount.value = 0
  } catch {
    ElMessage.error('通知状态更新失败')
  }
}

function formatNotificationTime(value) {
  return value ? new Date(value).toLocaleString() : ''
}

function updateViewport() {
  isMobile.value = window.matchMedia('(max-width: 768px)').matches
}

function refreshNotificationsWhenVisible() {
  if (!document.hidden) loadNotifications()
}

onMounted(() => {
  updateViewport()
  window.addEventListener('resize', updateViewport)
  document.addEventListener('visibilitychange', refreshNotificationsWhenVisible)
  loadNotifications()
  notificationTimer = window.setInterval(loadNotifications, 30 * 1000)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', updateViewport)
  document.removeEventListener('visibilitychange', refreshNotificationsWhenVisible)
  if (notificationTimer) window.clearInterval(notificationTimer)
})
</script>

<style scoped>
.app-shell {
  display: flex;
  min-height: 100vh;
  background: var(--app-bg);
}

.sidebar {
  position: sticky;
  top: 0;
  height: 100vh;
  width: var(--app-sidebar-width);
  display: flex;
  flex-direction: column;
  background: #11192d;
  border-right: 1px solid rgba(255, 255, 255, 0.07);
  flex-shrink: 0;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 22px 20px 16px;
}

.brand-mark {
  width: 34px;
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--app-ink);
  background: #73ded5;
  border-radius: 11px;
  box-shadow: 0 8px 18px rgba(24, 184, 178, 0.24);
}

.brand-name {
  font-size: 16px;
  font-weight: 700;
  line-height: 1.2;
  color: #fff;
}

.brand-sub {
  font-size: 11px;
  color: #8794b0;
}

.workspace-note {
  display: flex;
  flex-direction: column;
  gap: 5px;
  margin: 0 12px 8px;
  padding: 13px 14px;
  border: 1px solid rgba(255, 255, 255, 0.09);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.045);
}

.workspace-kicker,
.topbar-kicker {
  color: #6fddd5;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.08em;
}

.workspace-note strong {
  color: #f3f6ff;
  font-size: 13px;
}

.workspace-caption {
  color: #7f8ba5;
  font-size: 11px;
}

.nav {
  flex: 1;
  overflow-y: auto;
  padding: 4px 12px 8px;
}

.nav-group-title {
  padding: 17px 10px 7px;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0;
  color: #697795;
  text-transform: uppercase;
}

.nav-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 12px;
  margin-bottom: 2px;
  border-radius: var(--app-radius-sm);
  color: #9aa6be;
  font-size: 14px;
  text-decoration: none;
  transition: background 150ms ease, color 150ms ease;
}

.nav-item:hover {
  background: rgba(255, 255, 255, 0.07);
  color: #fff;
}

.nav-item.active {
  background: rgba(24, 184, 178, 0.14);
  color: #72e4dc;
  font-weight: 600;
}

.nav-item.active::before {
  content: "";
  position: absolute;
  left: 0;
  top: 22%;
  height: 56%;
  width: 3px;
  border-radius: 2px;
  background: var(--app-cyan);
}

.sidebar-footer {
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  padding: 14px 16px;
}

.user {
  display: flex;
  align-items: center;
  gap: 10px;
}

.user-avatar {
  background: var(--app-lilac);
  color: #fff;
  font-weight: 600;
}

.user-name {
  font-size: 13px;
  font-weight: 600;
  color: #fff;
}

.user-role {
  font-size: 11px;
  color: #8794b0;
}

.logout-btn {
  width: 100%;
  justify-content: flex-start;
  margin-top: 8px;
  color: #9aa6be;
}

.logout-btn:hover {
  color: #fff;
  background: rgba(255, 255, 255, 0.07);
}

.main-area {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.topbar {
  position: sticky;
  top: 0;
  z-index: 10;
  min-height: var(--app-header-height);
  height: auto;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 24px;
  background: rgba(255, 255, 255, 0.96);
  border-bottom: 1px solid var(--app-border);
}

.topbar-title {
  flex: 1;
  min-width: 0;
}

.topbar-kicker {
  display: block;
  margin-bottom: 2px;
  color: var(--app-primary);
  font-size: 9px;
}

.topbar-title .page-title {
  margin: 0;
  font-size: 17px;
}

.topbar-title .page-subtitle {
  margin: 3px 0 0;
  font-size: 13px;
}

.topbar-actions {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-shrink: 0;
}

.notification-badge {
  display: inline-flex;
}

.notification-btn {
  color: var(--app-text-secondary);
}

.notification-btn:hover {
  color: var(--app-cyan);
  background: var(--app-card-soft);
}

.inbox-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--app-border);
}

.inbox-header-actions {
  display: flex;
  align-items: center;
  gap: 2px;
}

.inbox-list {
  max-height: 360px;
  overflow-y: auto;
}

.inbox-item {
  display: flex;
  width: 100%;
  gap: 9px;
  padding: 12px 4px;
  border: 0;
  border-bottom: 1px solid var(--app-border);
  background: transparent;
  color: var(--app-text);
  text-align: left;
  cursor: pointer;
}

.inbox-item:hover {
  background: var(--app-card-soft);
}

.inbox-dot {
  width: 7px;
  height: 7px;
  margin-top: 5px;
  border-radius: 50%;
  background: var(--app-border-strong);
  flex-shrink: 0;
}

.inbox-item.unread .inbox-dot {
  background: var(--app-cyan);
}

.inbox-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.inbox-copy strong {
  font-size: 13px;
}

.inbox-copy span {
  color: var(--app-text-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.inbox-copy small {
  color: var(--app-text-muted);
  font-size: 11px;
}

.system-status {
  display: flex;
  align-items: center;
  gap: 7px;
  color: var(--app-text-secondary);
  font-size: 12px;
  font-weight: 600;
}

.status-pulse {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--app-cyan);
  box-shadow: 0 0 0 0 rgba(24, 184, 178, 0.45);
  animation: status-pulse 2.2s ease-out infinite;
}

.content {
  flex: 1;
  padding: 30px 32px 42px;
  max-width: 1600px;
  width: 100%;
  margin: 0 auto;
}

.menu-btn {
  padding: 6px;
}

.mobile-drawer :deep(.el-drawer__body) {
  display: flex;
  flex-direction: column;
  padding: 0;
}

.mobile-drawer :deep(.el-drawer) {
  background: var(--app-ink);
}

@keyframes status-pulse {
  0% { box-shadow: 0 0 0 0 rgba(24, 184, 178, 0.45); }
  70% { box-shadow: 0 0 0 7px rgba(24, 184, 178, 0); }
  100% { box-shadow: 0 0 0 0 rgba(24, 184, 178, 0); }
}

.mobile-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px 20px 8px;
}

@media (max-width: 768px) {
  .sidebar {
    display: none;
  }

  .content {
    padding: 16px;
  }

  .topbar {
    padding: 12px 16px;
  }

  .topbar-actions .system-status {
    display: none;
  }

  .topbar-title .page-title {
    font-size: 16px;
  }
}
</style>
