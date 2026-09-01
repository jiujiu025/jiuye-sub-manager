<template>
  <router-view v-if="$route.path === '/login'" />
  <el-container v-else class="layout">
    <el-aside width="220px">
      <div class="brand">订阅管理系统</div>
      <el-menu router :default-active="$route.path">
        <el-menu-item index="/">
          <el-icon><Odometer /></el-icon>
          <span>概览</span>
        </el-menu-item>
        <el-menu-item index="/sources">
          <el-icon><Connection /></el-icon>
          <span>上游订阅</span>
        </el-menu-item>
        <el-menu-item index="/nodes">
          <el-icon><Grid /></el-icon>
          <span>节点池</span>
        </el-menu-item>
        <el-menu-item index="/packages">
          <el-icon><Tickets /></el-icon>
          <span>套餐管理</span>
        </el-menu-item>
        <el-menu-item index="/logs">
          <el-icon><Document /></el-icon>
          <span>系统日志</span>
        </el-menu-item>
        <el-menu-item index="/settings">
          <el-icon><Setting /></el-icon>
          <span>系统设置</span>
        </el-menu-item>
        <el-menu-item index="/profile">
          <el-icon><Lock /></el-icon>
          <span>修改密码</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <span>管理员：{{ authStore.username }}</span>
        <el-button type="danger" size="small" @click="authStore.logout()">
          退出登录
        </el-button>
      </el-header>
      <el-main>
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { useAuthStore } from './stores/auth'

const authStore = useAuthStore()
</script>

<style>
html,
body,
#app {
  height: 100%;
  margin: 0;
  font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
}

.layout {
  height: 100vh;
}

.brand {
  height: 56px;
  line-height: 56px;
  text-align: center;
  font-weight: 600;
  color: #fff;
  background: #1f2937;
}

.el-aside {
  background: #1f2937;
}

.el-aside .el-menu {
  border-right: none;
  background: transparent;
}

.el-aside .el-menu-item {
  color: #d1d5db;
}

.el-aside .el-menu-item.is-active {
  color: #fff;
  background: #374151;
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #e5e7eb;
}
</style>
