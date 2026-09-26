<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">来源管理</h2>
        <p class="page-subtitle">管理上游订阅地址，观察同步状态与节点变化。</p>
      </div>
      <div class="page-header-mark"><el-icon><Connection /></el-icon><span>UPSTREAMS</span></div>
    </div>
    <div class="filter-bar">
      <el-input
        v-model="filters.keyword"
        placeholder="搜索订阅名称或地址"
        clearable
        style="width: 260px"
        @keyup.enter="load"
      />
      <el-select
        v-model="filters.status"
        placeholder="同步状态"
        clearable
        style="width: 140px"
        @change="load"
      >
        <el-option label="正常" value="success" />
        <el-option label="失败" value="failed" />
        <el-option label="未同步" value="never" />
      </el-select>
      <el-button @click="load">
        <el-icon><Refresh /></el-icon>
        刷新
      </el-button>
      <div class="spacer" />
      <el-button @click="syncAll" :loading="syncingAll">同步全部</el-button>
      <el-button type="primary" @click="openCreate">
        <el-icon><Plus /></el-icon>
        添加订阅
      </el-button>
    </div>

    <div class="surface-card">
      <el-table :data="displayedSources" v-loading="loading">
        <el-table-column prop="name" label="名称" min-width="140">
          <template #default="{ row }">
            <span class="node-name">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="url_masked" label="地址" min-width="220" show-overflow-tooltip />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'success' : 'info'" effect="light" round>
              {{ row.enabled ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="同步状态" width="110">
          <template #default="{ row }">
            <el-tag :type="syncTagType(row.last_sync_status)" effect="light" round>
              {{ syncTagText(row.last_sync_status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="node_count" label="节点数" width="90" align="right" />
        <el-table-column label="最后同步" width="170">
          <template #default="{ row }">
            <span class="muted-text">{{ formatTime(row.last_sync_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="last_error" label="错误信息" min-width="140" show-overflow-tooltip />
        <el-table-column label="操作" width="240" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="syncOne(row)" :loading="row.syncing">同步</el-button>
            <el-button size="small" type="primary" plain @click="openEdit(row)">编辑</el-button>
            <el-button size="small" plain @click="copyUrl(row)">复制链接</el-button>
            <el-button size="small" type="danger" plain @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <div class="empty-state">
            <p class="empty-state-title">还没有订阅源</p>
            <p class="empty-state-desc">添加第一个订阅源后，系统会自动获取并解析节点。</p>
            <el-button type="primary" @click="openCreate">+ 添加订阅</el-button>
          </div>
        </template>
      </el-table>
    </div>

    <el-dialog
      v-model="dialogVisible"
      :title="editing ? '编辑订阅' : '添加订阅'"
      width="560px"
      append-to-body
    >
      <p class="dialog-subtitle">
        添加一个上游订阅地址，系统会自动获取并解析节点。
      </p>
      <el-form
        ref="formRef"
        :model="form"
        :rules="formRules"
        label-position="top"
      >
        <el-form-item label="订阅名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入订阅名称" />
          <div class="form-hint">建议填写容易识别的名称，例如：日本线路、供应商 A</div>
        </el-form-item>
        <el-form-item label="订阅地址" prop="url">
          <el-input v-model="form.url" placeholder="https://example.com/subscribe/xxxxx" />
        </el-form-item>
        <el-form-item label="格式">
          <el-select v-model="form.format" style="width: 100%">
            <el-option label="自动检测" value="auto" />
            <el-option label="Clash YAML" value="clash" />
            <el-option label="Base64" value="base64" />
            <el-option label="Sing-box JSON" value="singbox" />
            <el-option label="V2Ray JSON" value="v2ray-json" />
            <el-option label="VLESS" value="vless" />
            <el-option label="VMess" value="vmess" />
            <el-option label="Shadowsocks" value="ss" />
            <el-option label="Trojan" value="trojan" />
          </el-select>
        </el-form-item>
        <div class="form-row">
          <el-form-item label="启用">
            <el-switch v-model="form.enabled" />
          </el-form-item>
          <el-form-item label="允许空覆盖">
            <el-switch v-model="form.allow_empty_override" />
          </el-form-item>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">
          保存订阅
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
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
const formRef = ref(null)
const filters = reactive({
  keyword: '',
  status: ''
})
const form = reactive({
  name: '',
  url: '',
  format: 'auto',
  enabled: true,
  allow_empty_override: false
})

const formRules = {
  name: [{ required: true, message: '请填写订阅名称', trigger: 'blur' }],
  url: [{ required: true, message: '请填写订阅地址', trigger: 'blur' }]
}

const displayedSources = computed(() => {
  if (!filters.status) {
    return sources.value
  }
  return sources.value.filter(
    (source) => source.last_sync_status === filters.status
  )
})

async function load() {
  loading.value = true
  try {
    const { data } = await listSources({ keyword: filters.keyword || undefined })
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
  formRef.value?.clearValidate()
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
  formRef.value?.clearValidate()
  dialogVisible.value = true
}

async function save() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) {
    return
  }
  saving.value = true
  try {
    if (editing.value) {
      await updateSource(editing.value.id, form)
    } else {
      await createSource(form)
    }
    dialogVisible.value = false
    ElMessage.success(editing.value ? '订阅已更新' : '订阅添加成功')
    await load()
  } finally {
    saving.value = false
  }
}

async function syncOne(row) {
  row.syncing = true
  try {
    const { data } = await syncSource(row.id)
    ElMessage[data.status === 'success' ? 'success' : 'warning'](
      data.status === 'success'
        ? `同步成功：${data.node_count} 个节点`
        : `同步失败：${data.error}`
    )
    await load()
  } finally {
    row.syncing = false
  }
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

async function copyUrl(row) {
  const { data } = await getSource(row.id)
  try {
    await navigator.clipboard.writeText(data.url)
    ElMessage.success('订阅链接已复制')
  } catch {
    ElMessage.error('复制失败，请手动复制')
  }
}

async function remove(row) {
  await ElMessageBox.confirm(
    `删除「${row.name}」后，相关配置将无法继续获取该订阅的数据。`,
    '删除订阅？',
    {
      type: 'warning',
      confirmButtonText: '确认删除',
      cancelButtonText: '取消'
    }
  )
  await deleteSource(row.id)
  ElMessage.success('已删除')
  await load()
}

function syncTagType(status) {
  return { success: 'success', failed: 'danger', never: 'info' }[status] || 'info'
}

function syncTagText(status) {
  return { success: '正常', failed: '异常', never: '未同步' }[status] || status
}

function formatTime(value) {
  return value ? new Date(value).toLocaleString() : '-'
}

onMounted(load)
</script>

<style scoped>
.spacer {
  flex: 1;
}

.node-name {
  font-weight: 600;
  color: var(--app-text);
}

.muted-text {
  color: var(--app-text-secondary);
  font-size: 12px;
}

.dialog-subtitle {
  margin: 0 0 16px;
  color: var(--app-text-secondary);
  font-size: 13px;
}

.form-hint {
  margin-top: 4px;
  font-size: 12px;
  color: var(--app-text-muted);
}

.form-row {
  display: flex;
  gap: 24px;
}

@media (max-width: 768px) {
  .form-row {
    flex-direction: column;
    gap: 0;
  }
}
</style>
