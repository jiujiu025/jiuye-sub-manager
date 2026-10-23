<template>
  <div class="page notifications-page">
    <div class="page-header page-toolbar">
      <div><h2 class="page-title">通知中心</h2><p class="page-subtitle">按优先级处理到期、同步和系统提醒。</p></div>
      <div class="page-actions"><el-button v-if="unreadCount" @click="markAll"><el-icon><Check /></el-icon>全部已读</el-button><el-button @click="load"><el-icon><Refresh /></el-icon>刷新</el-button></div>
    </div>

    <div class="notification-toolbar">
      <el-radio-group v-model="status" @change="load"><el-radio-button value="all">全部</el-radio-button><el-radio-button value="unread">未读 {{ unreadCount || '' }}</el-radio-button><el-radio-button value="read">已读</el-radio-button><el-radio-button value="archived">已归档</el-radio-button></el-radio-group>
       <el-select v-model="kind" clearable placeholder="全部类型" style="width: 190px" @change="load"><el-option label="订阅到期提醒" value="subscription_expiry" /><el-option label="今日到期" value="subscription_expiry_today" /><el-option label="订阅分配" value="subscription_assignment" /><el-option label="客户分配" value="customer_assignment" /><el-option label="经理变更" value="manager_assignment" /><el-option label="来源同步" value="source_sync" /><el-option label="节点健康" value="node_health" /><el-option label="Token 安全" value="token" /><el-option label="系统通知" value="system" /></el-select>
    </div>

    <div v-loading="loading" class="notification-list surface-card">
      <div v-for="item in items" :key="item.id" class="notification-row" :class="[{ unread: !item.read_at }, `priority-${item.priority}`]">
        <button class="notification-main" type="button" @click="open(item)">
          <span class="notification-icon"><el-icon><component :is="iconFor(item.kind)" /></el-icon></span>
          <span class="notification-body"><span class="notification-title"><strong>{{ item.title }}</strong><el-tag v-if="item.priority === 'high'" size="small" type="danger">重要</el-tag></span><span class="notification-content">{{ item.content }}</span><small>{{ kindLabel(item.kind) }} · {{ formatTime(item.created_at) }}</small></span>
          <span v-if="!item.read_at" class="unread-mark" aria-label="未读" />
        </button>
        <div class="notification-actions">
          <el-button link type="primary" @click="copyLookup(item)"><el-icon><DocumentCopy /></el-icon>复制定位信息</el-button>
          <el-button v-if="item.target_type && item.target_id" link type="primary" @click="locate(item)"><el-icon><Aim /></el-icon>立即定位</el-button>
          <el-button v-if="!item.read_at" link type="primary" @click="read(item)">标记已读</el-button>
          <el-button v-if="!item.archived_at" link @click="archive(item)">归档</el-button>
        </div>
      </div>
      <el-empty v-if="!loading && !items.length" description="当前筛选下暂无通知" :image-size="90" />
    </div>
    <div v-if="pages > 1" class="notification-pagination"><el-pagination v-model:current-page="page" :page-size="pageSize" :total="total" layout="total, prev, pager, next" background @current-change="load" /></div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { archiveNotification, listNotifications, markAllNotificationsRead, markNotificationRead } from '../api'
import { formatApiDate } from '../utils/datetime'

const router = useRouter()
const items = ref([])
const status = ref('all')
const kind = ref('')
const page = ref(1)
const pageSize = ref(20)
const pages = ref(1)
const total = ref(0)
const unreadCount = ref(0)
const loading = ref(false)
const isManager = localStorage.getItem('admin_role') === 'manager'

async function load() {
  loading.value = true
  try {
    const { data } = await listNotifications({ status: status.value, kind: kind.value || undefined, page: page.value, page_size: pageSize.value })
    items.value = data.items
    unreadCount.value = data.unread_count
    page.value = data.page
    pageSize.value = data.page_size
    pages.value = data.pages
    total.value = data.total
  } finally { loading.value = false }
}
async function read(item) { await markNotificationRead(item.id); item.read_at = new Date().toISOString(); unreadCount.value = Math.max(0, unreadCount.value - 1) }
async function markAll() { await markAllNotificationsRead(); items.value.forEach((item) => { item.read_at = item.read_at || new Date().toISOString() }); unreadCount.value = 0; ElMessage.success('已全部标记为已读') }
async function archive(item) { await archiveNotification(item.id); item.archived_at = new Date().toISOString(); if (status.value !== 'archived') items.value = items.value.filter((row) => row.id !== item.id); ElMessage.success('通知已归档') }
async function open(item) {
  if (!item.read_at) await read(item)
  const targetRoutes = { subscription: '/subscriptions', source: '/sources', package: '/packages', customer: '/customers', node: isManager ? '/health' : '/nodes' }
  const targetPath = targetRoutes[item.target_type]
  if (targetPath && item.target_id) router.push({ path: targetPath, query: { focus: String(item.target_id) } })
}
async function copyLookup(item) {
  const lineName = item.target_type === 'node'
    ? item.content.match(/线路[「"']([^」"']+)[」"']/)?.[1]
    : null
  const lookup = lineName || item.content
  try {
    await navigator.clipboard.writeText(lookup)
    ElMessage.success(lineName ? '线路名称已复制，可粘贴到资源池关键词中搜索' : '通知内容已复制')
  } catch {
    ElMessage.error('复制失败，请手动选择通知内容复制')
  }
}
function locate(item) {
  const targetRoutes = { node: isManager ? '/health' : '/nodes', source: '/sources', package: '/packages', subscription: '/subscriptions', customer: '/customers' }
  const targetPath = targetRoutes[item.target_type]
  if (targetPath) router.push({ path: targetPath, query: { focus: String(item.target_id) } })
}
function kindLabel(value) { return ({ subscription_expiry: '订阅三天内到期', subscription_expiry_today: '订阅今日到期', subscription_assignment: '订阅分配', customer_assignment: '客户分配', manager_assignment: '经理变更', subscription_lifecycle: '订阅状态', source_sync: '来源同步', node_health: '节点健康', token: 'Token 安全', system: '系统通知' })[value] || '其他通知' }
function iconFor(value) { return ({ subscription_expiry: 'WarningFilled', subscription_expiry_today: 'WarningFilled', subscription_assignment: 'Tickets', customer_assignment: 'UserFilled', manager_assignment: 'Switch', subscription_lifecycle: 'Operation', source_sync: 'Refresh', node_health: 'Connection', token: 'Lock', system: 'Bell' })[value] || 'Bell' }
function formatTime(value) { return formatApiDate(value) }
onMounted(load)
</script>

<style scoped>
.notifications-page { display: flex; flex-direction: column; gap: 16px; }
.page-toolbar { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.notification-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.notification-list { overflow: hidden; padding: 0; }
.notification-row { display: flex; align-items: center; gap: 10px; padding: 16px 20px; border-bottom: 1px solid var(--app-border); transition: background 150ms ease; }
.notification-row:last-child { border-bottom: 0; } .notification-row:hover { background: var(--app-card-soft); } .notification-row.unread { background: rgba(24,184,178,.035); }
.notification-main { display: flex; align-items: flex-start; flex: 1; min-width: 0; gap: 12px; padding: 0; border: 0; background: transparent; color: var(--app-text); text-align: left; cursor: pointer; }
.notification-icon { display: grid; place-items: center; width: 36px; height: 36px; flex: 0 0 auto; border-radius: 11px; color: var(--app-primary); background: rgba(114,92,213,.11); } .priority-high .notification-icon { color: var(--app-coral); background: rgba(241,112,115,.12); }
.notification-body { display: flex; flex-direction: column; min-width: 0; gap: 5px; } .notification-title { display: flex; align-items: center; gap: 8px; } .notification-title strong { font-size: 14px; } .notification-content { color: var(--app-text-secondary); font-size: 13px; line-height: 1.5; } .notification-body small { color: var(--app-text-muted); font-size: 11px; }
.unread-mark { width: 7px; height: 7px; flex: 0 0 auto; margin-top: 8px; border-radius: 50%; background: var(--app-cyan); } .notification-actions { display: flex; align-items: center; flex: 0 0 auto; }
.notification-pagination { display: flex; justify-content: flex-end; }
@media (max-width: 640px) { .notification-toolbar { align-items: stretch; flex-direction: column; } .notification-toolbar .el-radio-group,.notification-toolbar .el-select { width: 100%; } .notification-row { align-items: flex-start; padding: 14px; } .notification-actions { flex-direction: column; } }
</style>
