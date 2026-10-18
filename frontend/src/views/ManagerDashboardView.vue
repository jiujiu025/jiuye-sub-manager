<template>
  <div class="page manager-page">
    <section class="manager-hero">
      <div>
        <div class="eyebrow"><span class="pulse" />PARTNER DESK</div>
        <h2>把客户和订阅，交给一个清晰的工作台。</h2>
        <p>这里集中展示你的客户归属、订阅状态和即将到期的业务。</p>
      </div>
      <el-button type="primary" plain @click="router.push('/subscriptions')"><el-icon><Plus /></el-icon>开通订阅</el-button>
    </section>

    <section v-loading="loading" class="manager-stats">
      <div v-for="card in statCards" :key="card.label" class="manager-stat" :class="card.tone">
        <span>{{ card.label }}</span><strong>{{ card.value }}</strong><small>{{ card.hint }}</small>
      </div>
    </section>

    <section class="manager-columns">
      <div class="surface-card manager-panel">
        <div class="panel-heading"><div><h3>即将到期</h3><p>未来 3 天需要跟进的客户订阅</p></div><el-button link type="primary" @click="router.push('/notifications')">查看提醒</el-button></div>
        <div v-if="expiringGroups.length" class="expiring-list">
          <el-collapse v-model="expandedExpiringCustomers" accordion>
            <el-collapse-item v-for="group in expiringGroups" :key="group.customer_id" :name="String(group.customer_id)">
              <template #title>
                <span class="expiring-group-title"><span class="expiry-icon"><el-icon><WarningFilled /></el-icon></span><span class="expiry-copy"><strong>{{ group.customer_name }}</strong><small>{{ group.items.length }} 条订阅即将到期</small></span><span class="expiry-date">{{ formatTime(group.earliest_expires_at) }}</span></span>
              </template>
              <div class="expiring-children">
                <button v-for="item in group.items" :key="item.id" type="button" class="expiring-child" @click="router.push({ path: '/subscriptions', query: { focus: String(item.id) } })">
                  <span class="expiry-copy"><strong>{{ item.package_name }}</strong><small>到期：{{ formatTime(item.expires_at) }}</small></span>
                  <el-icon><ArrowRight /></el-icon>
                </button>
              </div>
            </el-collapse-item>
          </el-collapse>
        </div>
        <el-empty v-else description="当前没有 3 天内到期的订阅" :image-size="68" />
      </div>
      <div class="surface-card manager-panel quick-panel">
        <div class="panel-heading"><div><h3>业务入口</h3><p>快速进入常用工作区</p></div></div>
        <button class="quick-row" type="button" @click="router.push('/customers')"><span class="quick-badge cyan"><el-icon><UserFilled /></el-icon></span><span><strong>客户档案</strong><small>查看地区、联系方式和归属关系</small></span><el-icon><ArrowRight /></el-icon></button>
        <button class="quick-row" type="button" @click="router.push('/subscriptions')"><span class="quick-badge violet"><el-icon><Tickets /></el-icon></span><span><strong>客户订阅</strong><small>开通、复制订阅和管理 Token</small></span><el-icon><ArrowRight /></el-icon></button>
        <button class="quick-row" type="button" @click="router.push('/notifications')"><span class="quick-badge coral"><el-icon><Bell /></el-icon></span><span><strong>通知中心</strong><small>处理未读提醒和历史通知</small></span><el-icon><ArrowRight /></el-icon></button>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { listSubscriptions, getManagerStats } from '../api'

const router = useRouter()
const loading = ref(false)
const stats = ref({})
const subscriptions = ref([])
const expandedExpiringCustomers = ref([])
const statCards = computed(() => [
  { label: '客户总数', value: stats.value.customer_count ?? 0, hint: '当前归属客户', tone: 'cyan' },
  { label: '生效订阅', value: stats.value.active_subscription_count ?? 0, hint: '正在提供服务', tone: 'violet' },
  { label: '3 天内到期', value: stats.value.expiring_subscription_count ?? 0, hint: '需要及时跟进', tone: 'coral' },
  { label: '累计销售额', value: `¥${stats.value.sales_total ?? '0.00'}`, hint: '已记录销售价格', tone: 'amber' }
])
const expiring = computed(() => subscriptions.value.filter((item) => {
  if (item.status !== 'active' || !item.expires_at) return false
  const left = new Date(item.expires_at).getTime() - Date.now()
  return left > 0 && left <= 3 * 24 * 60 * 60 * 1000
}).slice(0, 6))
const expiringGroups = computed(() => {
  const groups = new Map()
  for (const item of expiring.value) {
    let group = groups.get(item.customer_id)
    if (!group) {
      group = { customer_id: item.customer_id, customer_name: item.customer_name, items: [] }
      groups.set(item.customer_id, group)
    }
    group.items.push(item)
  }
  return [...groups.values()].map((group) => ({
    ...group,
    earliest_expires_at: group.items.reduce((earliest, item) => {
      if (!earliest) return item.expires_at
      return new Date(item.expires_at) < new Date(earliest) ? item.expires_at : earliest
    }, null),
  }))
})

async function load() {
  loading.value = true
  try {
    const [statsResponse, subscriptionsResponse] = await Promise.all([getManagerStats(), listSubscriptions()])
    stats.value = statsResponse.data
    subscriptions.value = subscriptionsResponse.data
  } finally {
    loading.value = false
  }
}

function formatTime(value) { return value ? new Date(value).toLocaleString() : '-' }
onMounted(load)
</script>

<style scoped>
.manager-page { display: flex; flex-direction: column; gap: 20px; }
.manager-hero { display: flex; align-items: flex-end; justify-content: space-between; gap: 24px; min-height: 190px; padding: 30px 34px; border-radius: 20px; color: #fff; background: linear-gradient(120deg, #111b32, #1a2d4a 58%, #146d69); box-shadow: 0 18px 38px rgba(16,23,42,.18); }
.eyebrow { display: flex; align-items: center; gap: 8px; color: #85e3d6; font-size: 11px; font-weight: 800; letter-spacing: .08em; }
.pulse { width: 7px; height: 7px; border-radius: 50%; background: #85e3d6; box-shadow: 0 0 0 5px rgba(133,227,214,.12); }
.manager-hero h2 { max-width: 620px; margin: 14px 0 8px; font-size: clamp(24px, 3vw, 36px); line-height: 1.16; }
.manager-hero p { margin: 0; color: #b9c9dd; }
.manager-stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.manager-stat { padding: 18px 20px; border: 1px solid var(--app-border); border-radius: 12px; background: var(--app-card); box-shadow: inset 0 3px 0 var(--tone); }
.manager-stat.cyan { --tone: var(--app-cyan); } .manager-stat.violet { --tone: var(--app-primary); } .manager-stat.coral { --tone: var(--app-coral); } .manager-stat.amber { --tone: var(--app-warning); }
.manager-stat span,.manager-stat small { display: block; color: var(--app-text-muted); font-size: 12px; } .manager-stat strong { display: block; margin: 8px 0 4px; color: var(--app-text); font-size: 26px; }
.manager-columns { display: grid; grid-template-columns: 1.25fr .75fr; gap: 16px; }
.manager-panel { min-height: 310px; padding: 22px; }
.panel-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 14px; } .panel-heading h3 { margin: 0; } .panel-heading p { margin: 5px 0 0; color: var(--app-text-muted); font-size: 12px; }
.expiring-group-title { display: flex; align-items: center; width: 100%; gap: 12px; padding-right: 12px; }
.expiring-children { padding: 0 10px 6px 44px; border-left: 2px solid rgba(240,113,97,.18); }
.expiring-child,.quick-row { display: flex; align-items: center; width: 100%; gap: 12px; padding: 11px 4px; border: 0; border-bottom: 1px solid var(--app-border); background: transparent; color: var(--app-text); text-align: left; cursor: pointer; }
.expiring-child:last-child { border-bottom: 0; }
.expiring-child:hover,.quick-row:hover { background: var(--app-card-soft); }
.expiry-icon,.quick-badge { display: grid; place-items: center; width: 32px; height: 32px; flex: 0 0 auto; border-radius: 9px; } .expiry-icon { color: var(--app-coral); background: rgba(241,112,115,.12); }
.quick-badge.cyan { color: var(--app-cyan-deep); background: rgba(24,184,178,.12); } .quick-badge.violet { color: var(--app-primary); background: rgba(114,92,213,.12); } .quick-badge.coral { color: var(--app-coral); background: rgba(241,112,115,.12); }
.expiry-copy,.quick-row span:nth-child(2) { min-width: 0; flex: 1; } .expiry-copy strong,.quick-row strong { display: block; font-size: 13px; } .expiry-copy small,.quick-row small { display: block; margin-top: 3px; color: var(--app-text-muted); font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; } .expiry-date { color: var(--app-coral); font-size: 12px; white-space: nowrap; }
@media (max-width: 850px) { .manager-stats { grid-template-columns: repeat(2, 1fr); } .manager-columns { grid-template-columns: 1fr; } }
@media (max-width: 560px) { .manager-hero { align-items: flex-start; flex-direction: column; padding: 24px; } .manager-stats { grid-template-columns: 1fr 1fr; } .manager-stat { padding: 14px; } }
</style>
