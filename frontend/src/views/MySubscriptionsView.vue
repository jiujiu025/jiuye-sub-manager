<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">我的订阅</h2>
        <p class="page-subtitle">查看名下套餐，复制适合当前客户端的订阅地址。</p>
      </div>
      <div class="page-header-mark"><el-icon><Tickets /></el-icon><span>MY ACCESS</span></div>
    </div>
    <div v-loading="loading" class="subscription-grid">
      <div v-if="customerPortal" class="portal-banner surface-card">
        <div><span class="eyebrow">CUSTOMER PORTAL</span><h3>{{ customerProfile.name }}</h3><p>{{ customerProfile.region || '未设置地区' }} · 仅展示你自己的客户订阅</p></div>
        <el-tag type="success">客户账号</el-tag>
      </div>
      <div v-if="customerPortal && customerNotifications.length" class="portal-notifications surface-card">
        <div class="portal-notification-head"><div><strong>到期提醒</strong><span>请及时联系负责人续费</span></div><el-button link type="primary" @click="markAllCustomerRead">全部已读</el-button></div>
        <button v-for="item in customerNotifications" :key="item.id" type="button" class="portal-notification" @click="readCustomerNotification(item)"><span class="notification-dot" /><span><strong>{{ item.title }}</strong><small>{{ item.content }}</small></span></button>
      </div>
      <el-empty v-if="!loading && !(customerPortal ? customerSubscriptions.length : packages.length)" :description="customerPortal ? '暂无客户订阅' : '暂无分配给你的套餐'" />
      <div v-for="item in customerPortal ? customerSubscriptions : packages" :key="item.id" class="surface-card subscription-card">
        <div class="card-heading">
          <div>
            <h2>{{ customerPortal ? item.package_name : (item.subscription_name || item.name) }}</h2>
            <p>{{ customerPortal ? `Token ${item.token_prefix} · 开通于 ${formatTime(item.started_at)}` : (item.description || '订阅套餐') }}</p>
          </div>
          <el-tag :type="statusType(item)">{{ statusLabel(item) }}</el-tag>
        </div>
        <div class="subscription-meta">
          <span>{{ customerPortal ? '订阅编号' : '套餐名称' }}</span><strong>{{ customerPortal ? `#${item.id}` : item.name }}</strong>
          <span>到期时间</span><strong>{{ expirationLabel(item) }}</strong>
        </div>
        <div class="subscription-actions">
          <el-button type="primary" :disabled="Boolean(item.token_revoked_at)" @click="copyUrl(item)">
            复制订阅地址
          </el-button>
          <el-button :disabled="Boolean(item.token_revoked_at)" @click="copyUrl(item, 'singbox')">
            复制 Sing-box
          </el-button>
          <el-button :disabled="Boolean(item.token_revoked_at)" @click="copyUrl(item, 'uri')">
            复制 URI
          </el-button>
          <el-button :disabled="Boolean(item.token_revoked_at)" @click="copyUrl(item, 'base64')">
            复制 Base64
          </el-button>
          <el-button :disabled="Boolean(item.token_revoked_at)" @click="showQr(item)">显示二维码</el-button>
          <el-button v-if="customerPortal" :disabled="Boolean(item.token_revoked_at)" @click="showPreview(item)">查看节点</el-button>
        </div>
      </div>
    </div>

    <el-dialog v-model="qrVisible" title="订阅二维码" width="360px" append-to-body>
      <div class="qr-body"><img :src="qrDataUrl" alt="订阅二维码" class="qr-image" /><div class="qr-url">{{ qrUrl }}</div></div>
      <template #footer><el-button @click="qrVisible = false">关闭</el-button><el-button type="primary" @click="copyText(qrUrl)">复制订阅地址</el-button></template>
    </el-dialog>
    <el-dialog v-model="previewVisible" title="订阅线路预览" width="720px" append-to-body>
      <el-table v-loading="previewLoading" :data="previewRows" max-height="420" empty-text="暂无可用节点"><el-table-column prop="name" label="名称" min-width="180" /><el-table-column prop="type" label="协议" width="100" /><el-table-column prop="server" label="服务器" min-width="180" /><el-table-column prop="port" label="端口" width="90" /><el-table-column prop="country" label="地区" width="100" /></el-table>
    </el-dialog>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import QRCode from 'qrcode'
import { getCustomerProfile, getCustomerSubscriptionUrl, getMyPackageSubscriptionUrl, listCustomerNotifications, listCustomerSubscriptions, listMyPackages, markAllCustomerNotificationsRead, markCustomerNotificationRead, previewCustomerPortalSubscription } from '../api'
import { useAuthStore } from '../stores/auth'

const packages = ref([])
const loading = ref(false)
const customerPortal = ref(false)
const customerProfile = ref({})
const customerSubscriptions = ref([])
const customerNotifications = ref([])
const qrVisible = ref(false)
const qrDataUrl = ref('')
const qrUrl = ref('')
const previewVisible = ref(false)
const previewLoading = ref(false)
const previewRows = ref([])
const authStore = useAuthStore()
const now = ref(Date.now())
let statusTimer

function isExpired(pkg) {
  return Boolean(pkg.expires_at && new Date(pkg.expires_at).getTime() <= now.value)
}

function statusLabel(pkg) {
  if (pkg.token_revoked_at) return 'Token 已撤销'
  if (pkg.status === 'paused') return '已暂停'
  if (pkg.status === 'cancelled') return '已取消'
  if (pkg.enabled === false) return '已停用'
  if (isExpired(pkg)) return '已到期'
  return '可用'
}

function statusType(pkg) {
  if (pkg.token_revoked_at || pkg.status === 'cancelled' || pkg.enabled === false || isExpired(pkg)) return 'danger'
  return 'success'
}

function expirationLabel(pkg) {
  if (!pkg.expires_at) return '长期有效'
  return new Date(pkg.expires_at).toLocaleString()
}

function formatTime(value) { return value ? new Date(value).toLocaleString() : '-' }
async function copyUrl(item, client = '') {
  try {
    const { data } = customerPortal.value
      ? await getCustomerSubscriptionUrl(item.id)
      : await getMyPackageSubscriptionUrl(item.id)
    const url = client ? `${data.subscription_url}?client=${client}` : data.subscription_url
    await copyText(url)
  } catch {
    ElMessage.error('复制失败，请检查浏览器权限')
  }
}
async function copyText(value) { await navigator.clipboard.writeText(value); ElMessage.success('订阅地址已复制') }
async function showQr(item) {
  try { const { data } = customerPortal.value ? await getCustomerSubscriptionUrl(item.id) : await getMyPackageSubscriptionUrl(item.id); qrUrl.value = data.subscription_url; qrDataUrl.value = await QRCode.toDataURL(qrUrl.value, { width: 240, margin: 1 }); qrVisible.value = true } catch { ElMessage.error('订阅二维码生成失败') }
}
async function showPreview(item) {
  previewVisible.value = true; previewLoading.value = true
  try { const { data } = await previewCustomerPortalSubscription(item.id); previewRows.value = data } finally { previewLoading.value = false }
}
async function readCustomerNotification(item) {
  if (!item.read_at) {
    await markCustomerNotificationRead(item.id)
    item.read_at = new Date().toISOString()
  }
  customerNotifications.value = customerNotifications.value.filter((row) => !row.read_at)
}
async function markAllCustomerRead() {
  await markAllCustomerNotificationsRead()
  customerNotifications.value = []
  ElMessage.success('提醒已全部标记为已读')
}

async function load() {
  loading.value = true
  try {
    if (authStore.role !== 'user') {
      const { data } = await listMyPackages()
      packages.value = data
      return
    }
    const { data: profile } = await getCustomerProfile()
    customerPortal.value = profile.bound
    customerProfile.value = profile
    if (profile.bound) {
      const [{ data }, { data: warningData }, { data: todayData }] = await Promise.all([
        listCustomerSubscriptions(),
        listCustomerNotifications({ status: 'unread', kind: 'subscription_expiry', page: 1, page_size: 5 }),
        listCustomerNotifications({ status: 'unread', kind: 'subscription_expiry_today', page: 1, page_size: 5 })
      ])
      customerSubscriptions.value = data
      customerNotifications.value = [...warningData.items, ...todayData.items]
        .sort((left, right) => new Date(right.created_at) - new Date(left.created_at))
        .slice(0, 5)
    } else {
      const { data } = await listMyPackages()
      packages.value = data
    }
  } catch {
    customerPortal.value = false
    const { data } = await listMyPackages()
    packages.value = data
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  load()
  statusTimer = window.setInterval(() => { now.value = Date.now() }, 60 * 1000)
})

onBeforeUnmount(() => {
  if (statusTimer) window.clearInterval(statusTimer)
})
</script>

<style scoped>
.subscription-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 16px;
}

.subscription-card {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.card-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.card-heading h2 {
  margin: 0;
  font-size: 18px;
}

.card-heading p {
  margin: 6px 0 0;
  color: var(--app-text-secondary);
  font-size: 13px;
}

.subscription-meta {
  display: grid;
  grid-template-columns: 90px 1fr;
  gap: 10px;
  font-size: 13px;
}

.subscription-meta span {
  color: var(--app-text-muted);
}

.subscription-meta strong {
  color: var(--app-text);
  word-break: break-word;
}

.subscription-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: auto;
}
.portal-banner { display: flex; align-items: center; justify-content: space-between; gap: 16px; grid-column: 1 / -1; }
.portal-banner h3 { margin: 4px 0; font-size: 18px; }
.portal-banner p { margin: 0; color: var(--app-text-secondary); font-size: 13px; }
.portal-notifications { grid-column: 1 / -1; padding: 16px 18px; }
.portal-notification-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 6px; }
.portal-notification-head div { display: flex; flex-direction: column; gap: 3px; }
.portal-notification-head span, .portal-notification small { color: var(--app-text-secondary); font-size: 12px; }
.portal-notification { display: flex; align-items: flex-start; width: 100%; gap: 9px; padding: 10px 2px; border: 0; border-top: 1px solid var(--app-border); background: transparent; color: var(--app-text); text-align: left; cursor: pointer; }
.portal-notification span:last-child { display: flex; flex-direction: column; gap: 3px; }
.notification-dot { width: 7px; height: 7px; margin-top: 5px; border-radius: 50%; background: var(--app-coral); flex: 0 0 auto; }
.eyebrow { color: var(--app-cyan); font-size: 11px; font-weight: 700; letter-spacing: 0.08em; }
.qr-body { display: flex; flex-direction: column; align-items: center; gap: 14px; }
.qr-image { width: 240px; height: 240px; border: 1px solid var(--app-border); border-radius: var(--app-radius-sm); }
.qr-url { max-width: 100%; color: var(--app-text-secondary); font-size: 12px; word-break: break-all; text-align: center; }
</style>
