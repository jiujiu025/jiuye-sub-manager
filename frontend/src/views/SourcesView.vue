<template>
  <div>
    <div class="page-header">
      <h2>上游订阅</h2>
      <div>
        <el-button @click="syncAll" :loading="syncingAll">同步全部</el-button>
        <el-button type="primary" @click="openCreate">新增订阅</el-button>
      </div>
    </div>

    <el-table :data="sources" v-loading="loading">
      <el-table-column prop="name" label="名称" min-width="120" />
      <el-table-column prop="url_masked" label="订阅地址" min-width="200" show-overflow-tooltip />
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.enabled ? 'success' : 'info'">
            {{ row.enabled ? '启用' : '停用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="node_count" label="节点数" width="90" />
      <el-table-column label="同步状态" width="110">
        <template #default="{ row }">
          <el-tag :type="statusType(row.last_sync_status)">
            {{ statusText(row.last_sync_status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="最后同步" width="170">
        <template #default="{ row }">
          {{ formatTime(row.last_sync_at) }}
        </template>
      </el-table-column>
      <el-table-column prop="last_error" label="错误信息" min-width="160" show-overflow-tooltip />
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="syncOne(row)">同步</el-button>
          <el-button size="small" type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑订阅' : '新增订阅'" width="520px">
      <el-form label-width="110px">
        <el-form-item label="名称">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="订阅 URL">
          <el-input v-model="form.url" />
        </el-form-item>
        <el-form-item label="格式">
          <el-select v-model="form.format" style="width: 100%">
            <el-option label="自动检测" value="auto" />
            <el-option label="Clash YAML" value="clash" />
            <el-option label="Base64" value="base64" />
            <el-option label="VLESS" value="vless" />
            <el-option label="Shadowsocks" value="ss" />
          </el-select>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
        <el-form-item label="允许空覆盖">
          <el-switch v-model="form.allow_empty_override" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  createSource,
  deleteSource,
  getSource,
  listSources,
  syncAllSources,
  syncSource,
  updateSource
} from '../api'

const sources = ref([])
const loading = ref(false)
const syncingAll = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const editing = ref(null)
const form = reactive({
  name: '',
  url: '',
  format: 'auto',
  enabled: true,
  allow_empty_override: false
})

async function load() {
  loading.value = true
  try {
    const { data } = await listSources()
    sources.value = data.items
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = null
  Object.assign(form, {
    name: '',
    url: '',
    format: 'auto',
    enabled: true,
    allow_empty_override: false
  })
  dialogVisible.value = true
}

async function openEdit(row) {
  editing.value = row
  const { data } = await getSource(row.id)
  Object.assign(form, {
    name: data.name,
    url: data.url,
    format: data.format,
    enabled: data.enabled,
    allow_empty_override: data.allow_empty_override
  })
  dialogVisible.value = true
}

async function save() {
  saving.value = true
  try {
    if (editing.value) {
      await updateSource(editing.value.id, form)
    } else {
      await createSource(form)
    }
    dialogVisible.value = false
    ElMessage.success('保存成功')
    await load()
  } finally {
    saving.value = false
  }
}

async function syncOne(row) {
  const { data } = await syncSource(row.id)
  ElMessage[data.status === 'success' ? 'success' : 'warning'](
    data.status === 'success'
      ? `同步成功：${data.node_count} 个节点`
      : `同步失败：${data.error}`
  )
  await load()
}

async function syncAll() {
  syncingAll.value = true
  try {
    const { data } = await syncAllSources()
    const failed = data.filter((item) => item.status === 'failed')
    if (failed.length) {
      ElMessage.warning(`${failed.length} 个来源同步失败`)
    } else {
      ElMessage.success('全部同步完成')
    }
    await load()
  } finally {
    syncingAll.value = false
  }
}

async function remove(row) {
  await ElMessageBox.confirm(`确认删除订阅「${row.name}」及其节点？`, '删除确认', {
    type: 'warning'
  })
  await deleteSource(row.id)
  ElMessage.success('已删除')
  await load()
}

function statusText(status) {
  return { success: '正常', failed: '失败', never: '未同步' }[status] || status
}

function statusType(status) {
  return { success: 'success', failed: 'danger', never: 'info' }[status] || 'info'
}

function formatTime(value) {
  return value ? new Date(value).toLocaleString() : '-'
}

onMounted(load)
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
</style>
