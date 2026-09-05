<template>
  <div>
    <el-tabs v-model="kind" @tab-change="load">
      <el-tab-pane label="同步日志" name="sync" />
      <el-tab-pane label="订阅请求" name="subscription" />
      <el-tab-pane label="管理员操作" name="admin" />
      <el-tab-pane label="系统日志" name="system" />
      <el-tab-pane label="错误日志" name="error" />
    </el-tabs>

    <el-table v-if="kind === 'sync'" :data="rows" v-loading="loading">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="source_id" label="来源 ID" width="90" />
      <el-table-column prop="version" label="版本" width="80" />
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.status === 'success' ? 'success' : 'danger'">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="node_count" label="节点数" width="80" />
      <el-table-column prop="added_count" label="新增" width="70" />
      <el-table-column prop="removed_count" label="删除" width="70" />
      <el-table-column prop="changed_count" label="修改" width="70" />
      <el-table-column prop="error_message" label="错误信息" min-width="180" show-overflow-tooltip />
      <el-table-column label="时间" width="170">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
    </el-table>

    <el-table v-else-if="kind === 'subscription'" :data="rows" v-loading="loading">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="package_id" label="套餐 ID" width="90" />
      <el-table-column prop="status" label="状态" width="90" />
      <el-table-column prop="node_count" label="节点数" width="90" />
      <el-table-column prop="client_ip" label="客户端 IP" width="150" />
      <el-table-column label="时间" width="170">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
    </el-table>

    <el-table v-else-if="kind === 'admin'" :data="rows" v-loading="loading">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="action" label="操作" min-width="150" />
      <el-table-column prop="target_type" label="对象类型" width="110" />
      <el-table-column prop="target_value" label="对象" min-width="140" show-overflow-tooltip />
      <el-table-column label="时间" width="170">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
    </el-table>

    <el-card v-else class="log-card">
      <pre class="log-lines">{{ logText }}</pre>
    </el-card>

    <el-pagination
      v-if="kind !== 'system' && kind !== 'error'"
      class="pagination"
      layout="total, prev, pager, next"
      :total="total"
      :page-size="pageSize"
      :current-page="page"
      @current-change="(value) => { page = value; load() }"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { getLogs } from '../api'

const kind = ref('sync')
const rows = ref([])
const logLines = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 50
const loading = ref(false)

const logText = computed(() => logLines.value.join('\n') || '暂无日志')

async function load() {
  loading.value = true
  try {
    const { data } = await getLogs({
      kind: kind.value,
      page: page.value,
      page_size: pageSize
    })
    if (kind.value === 'system' || kind.value === 'error') {
      logLines.value = data.items
      total.value = data.total
      rows.value = []
    } else {
      rows.value = data.items
      total.value = data.total
      logLines.value = []
    }
  } finally {
    loading.value = false
  }
}

function formatTime(value) {
  return value ? new Date(value).toLocaleString() : '-'
}

onMounted(load)
</script>

<style scoped>
.log-card {
  background: #111827;
  color: #d1d5db;
}

.log-lines {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
  font-size: 12px;
  line-height: 1.6;
}

.pagination {
  margin-top: 16px;
  justify-content: flex-end;
}
</style>
