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
      <el-empty v-if="!loading && !packages.length" description="暂无分配给你的套餐" />
      <div v-for="pkg in packages" :key="pkg.id" class="surface-card subscription-card">
        <div class="card-heading">
          <div>
            <h2>{{ pkg.subscription_name || pkg.name }}</h2>
            <p>{{ pkg.description || '订阅套餐' }}</p>
          </div>
          <el-tag :type="statusType(pkg)">{{ statusLabel(pkg) }}</el-tag>
        </div>
        <div class="subscription-meta">
          <span>套餐名称</span><strong>{{ pkg.name }}</strong>
          <span>到期时间</span><strong>{{ expirationLabel(pkg) }}</strong>
        </div>
        <div class="subscription-actions">
          <el-button type="primary" :disabled="Boolean(pkg.token_revoked_at)" @click="copyPackageUrl(pkg)">
            复制 Clash 订阅
          </el-button>
          <el-button :disabled="Boolean(pkg.token_revoked_at)" @click="copyPackageUrl(pkg, 'singbox')">
            复制 Sing-box
          </el-button>
          <el-button :disabled="Boolean(pkg.token_revoked_at)" @click="copyPackageUrl(pkg, 'uri')">
            复制 URI
          </el-button>
          <el-button :disabled="Boolean(pkg.token_revoked_at)" @click="copyPackageUrl(pkg, 'base64')">
            复制 Base64
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getMyPackageSubscriptionUrl, listMyPackages } from '../api'

const packages = ref([])
const loading = ref(false)

function isExpired(pkg) {
  return Boolean(pkg.expires_at && new Date(pkg.expires_at).getTime() <= Date.now())
}

function statusLabel(pkg) {
  if (!pkg.enabled) return '已停用'
  if (isExpired(pkg)) return '已到期'
  return '可用'
}

function statusType(pkg) {
  if (!pkg.enabled || isExpired(pkg)) return 'danger'
  return 'success'
}

function expirationLabel(pkg) {
  if (!pkg.expires_at) return '长期有效'
  return new Date(pkg.expires_at).toLocaleString()
}

async function copyPackageUrl(pkg, client = '') {
  try {
    const { data } = await getMyPackageSubscriptionUrl(pkg.id)
    const url = client ? `${data.subscription_url}?client=${client}` : data.subscription_url
    await navigator.clipboard.writeText(url)
    ElMessage.success('订阅地址已复制')
  } catch {
    ElMessage.error('复制失败，请检查浏览器权限')
  }
}

async function load() {
  loading.value = true
  try {
    const { data } = await listMyPackages()
    packages.value = data
  } finally {
    loading.value = false
  }
}

onMounted(load)
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
</style>
