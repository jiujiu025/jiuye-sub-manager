<template>
  <router-view v-if="$route.path === '/login'" />
  <div v-else class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">
          <el-icon :size="18"><Cloudy /></el-icon>
        </div>
        <div>
          <div class="brand-name">玖玖云</div>
          <div class="brand-sub">控制台</div>
        </div>
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
            <div class="user-role">管理员</div>
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
          @click="drawerOpen = true"
        >
          <el-icon :size="18"><Menu /></el-icon>
        </el-button>
        <div class="topbar-title">
          <h1 class="page-title">{{ pageTitle }}</h1>
          <p class="page-subtitle">{{ pageSubtitle }}</p>
        </div>
        <div class="topbar-actions">
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
            <div class="user-role">管理员</div>
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
import { useRoute } from 'vue-router'
import { useAuthStore } from './stores/auth'

const route = useRoute()
const authStore = useAuthStore()
const drawerOpen = ref(false)
const isMobile = ref(false)

const navGroups = [
  {
    title: '工作台',
    items: [{ path: '/', label: '概览', icon: 'Odometer' }]
  },
  {
    title: '资源',
    items: [
      { path: '/sources', label: '来源管理', icon: 'Connection' },
      { path: '/packages', label: '套餐管理', icon: 'Tickets' },
      { path: '/nodes', label: '节点管理', icon: 'Grid' }
    ]
  },
  {
    title: '系统',
    items: [
      { path: '/logs', label: '系统日志', icon: 'Document' },
      { path: '/settings', label: '系统设置', icon: 'Setting' },
      { path: '/profile', label: '修改密码', icon: 'Lock' }
    ]
  }
]

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

function updateViewport() {
  isMobile.value = window.matchMedia('(max-width: 768px)').matches
}

onMounted(() => {
  updateViewport()
  window.addEventListener('resize', updateViewport)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', updateViewport)
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
  background: var(--app-card);
  border-right: 1px solid var(--app-border);
  flex-shrink: 0;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px 20px 16px;
}

.brand-mark {
  width: 34px;
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  background: var(--app-primary);
  border-radius: 10px;
}

.brand-name {
  font-size: 16px;
  font-weight: 700;
  line-height: 1.2;
  color: var(--app-text);
}

.brand-sub {
  font-size: 11px;
  color: var(--app-text-muted);
}

.nav {
  flex: 1;
  overflow-y: auto;
  padding: 8px 12px;
}

.nav-group-title {
  padding: 16px 10px 6px;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0;
  color: var(--app-text-muted);
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
  color: var(--app-text-secondary);
  font-size: 14px;
  text-decoration: none;
  transition: background 150ms ease, color 150ms ease;
}

.nav-item:hover {
  background: #f2f4f7;
  color: var(--app-text);
}

.nav-item.active {
  background: #eef3fe;
  color: var(--app-primary);
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
  background: var(--app-primary);
}

.sidebar-footer {
  border-top: 1px solid var(--app-border);
  padding: 14px 16px;
}

.user {
  display: flex;
  align-items: center;
  gap: 10px;
}

.user-avatar {
  background: var(--app-primary);
  color: #fff;
  font-weight: 600;
}

.user-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text);
}

.user-role {
  font-size: 11px;
  color: var(--app-text-muted);
}

.logout-btn {
  width: 100%;
  justify-content: flex-start;
  margin-top: 8px;
  color: var(--app-text-muted);
}

.main-area {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.topbar {
  height: var(--app-header-height);
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 24px;
  background: var(--app-card);
  border-bottom: 1px solid var(--app-border);
}

.topbar-title {
  flex: 1;
  min-width: 0;
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
  flex-shrink: 0;
}

.content {
  flex: 1;
  padding: 32px;
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
    padding: 0 16px;
  }
}
</style>
