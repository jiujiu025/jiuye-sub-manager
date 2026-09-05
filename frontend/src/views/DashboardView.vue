<template>
  <div class="page">
    <div class="welcome">
      <h2 class="welcome-title">欢迎回来，{{ authStore.username }}</h2>
      <p class="welcome-sub">这里是你的订阅、节点与套餐资源总览。</p>
    </div>

    <div class="stats-grid">
      <div v-for="card in cards" :key="card.label" class="stat-card">
        <div class="stat-label">{{ card.label }}</div>
        <div class="stat-value">{{ card.value }}</div>
        <div class="stat-meta">{{ card.meta }}</div>
      </div>
    </div>

    <div class="surface-card sync-card">
      <div>
        <div class="sync-label">最近同步</div>
        <div class="sync-value">{{ stats.last_sync_at ? formatTime(stats.last_sync_at) : '尚未同步' }}</div>
      </div>
      <div class="sync-extra">
        <span>同步失败来源：{{ stats.failed_source_count ?? 0 }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { getStats } from '../api'
import { useAuthStore } from '../stores/auth'

const authStore = useAuthStore()
const stats = ref({})

onMounted(async () => {
  try {
    const { data } = await getStats()
    stats.value = data
  } catch {
    stats.value = {}
  }
})

const cards = computed(() => [
  {
    label: '订阅源',
    value: stats.value.source_count ?? 0,
    meta: `启用 ${stats.value.enabled_source_count ?? 0}`
  },
  {
    label: '套餐',
    value: stats.value.package_count ?? 0,
    meta: `启用 ${stats.value.enabled_package_count ?? 0}`
  },
  {
    label: '节点',
    value: stats.value.node_count ?? 0,
    meta: `自有 ${stats.value.self_node_count ?? 0}`
  },
  {
    label: '同步失败',
    value: stats.value.failed_source_count ?? 0,
    meta: '需要关注的来源'
  }
])

function formatTime(value) {
  return value ? new Date(value).toLocaleString() : '-'
}
</script>

<style scoped>
.welcome {
  margin-bottom: 24px;
}

.welcome-title {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  letter-spacing: 0;
  color: var(--app-text);
}

.welcome-sub {
  margin: 6px 0 0;
  font-size: 13px;
  color: var(--app-text-secondary);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 20px;
}

.stat-card {
  background: var(--app-card);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-md);
  padding: 18px 20px;
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
}

.stat-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--app-text-muted);
}

.stat-value {
  margin: 8px 0 6px;
  font-size: 28px;
  font-weight: 700;
  letter-spacing: 0;
  color: var(--app-text);
  font-variant-numeric: tabular-nums;
}

.stat-meta {
  font-size: 12px;
  color: var(--app-text-secondary);
}

.sync-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.sync-label {
  font-size: 12px;
  color: var(--app-text-muted);
}

.sync-value {
  margin-top: 4px;
  font-size: 15px;
  font-weight: 600;
  color: var(--app-text);
}

.sync-extra {
  font-size: 12px;
  color: var(--app-text-secondary);
}

@media (max-width: 1200px) {
  .stats-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .stats-grid {
    grid-template-columns: 1fr;
  }
}
</style>
