<template>
  <div>
    <h2>概览</h2>
    <el-row :gutter="16">
      <el-col v-for="card in cards" :key="card.label" :xs="12" :sm="8" :md="6">
        <div class="stat-card">
          <div class="stat-value">{{ card.value }}</div>
          <div class="stat-label">{{ card.label }}</div>
        </div>
      </el-col>
    </el-row>
    <div v-if="stats.last_sync_at" class="last-sync">
      最后同步时间：{{ formatTime(stats.last_sync_at) }}
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { getStats } from '../api'

const stats = ref({})

onMounted(async () => {
  const { data } = await getStats()
  stats.value = data
})

const cards = computed(() => [
  { label: '上游订阅', value: stats.value.source_count ?? 0 },
  { label: '启用上游', value: stats.value.enabled_source_count ?? 0 },
  { label: '统一节点', value: stats.value.node_count ?? 0 },
  { label: '自有节点', value: stats.value.self_node_count ?? 0 },
  { label: '套餐数量', value: stats.value.package_count ?? 0 },
  { label: '启用套餐', value: stats.value.enabled_package_count ?? 0 },
  { label: '同步失败', value: stats.value.failed_source_count ?? 0 }
])

function formatTime(value) {
  return value ? new Date(value).toLocaleString() : '-'
}
</script>

<style scoped>
.stat-card {
  padding: 18px;
  margin-bottom: 16px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fff;
}

.stat-value {
  font-size: 28px;
  font-weight: 600;
  color: #1f2937;
}

.stat-label {
  margin-top: 6px;
  color: #6b7280;
}

.last-sync {
  margin-top: 8px;
  color: #6b7280;
}
</style>
