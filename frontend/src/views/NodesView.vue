<template>
  <div>
    <div class="page-header">
      <h2>节点池</h2>
      <div>
        <el-button
          :disabled="!selected.length"
          @click="batchAction('enable')"
        >
          批量启用
        </el-button>
        <el-button
          :disabled="!selected.length"
          @click="batchAction('disable')"
        >
          批量禁用
        </el-button>
        <el-button
          type="danger"
          :disabled="!selected.length"
          @click="batchAction('delete')"
        >
          批量删除
        </el-button>
        <el-button type="primary" @click="openCreate">添加自有节点</el-button>
      </div>
    </div>

    <el-form inline class="filters">
      <el-form-item label="关键词">
        <el-input v-model="filters.keyword" clearable placeholder="名称/服务器" @keyup.enter="load" />
      </el-form-item>
      <el-form-item label="来源">
        <el-input v-model="filters.source_name" clearable placeholder="来源名称" @keyup.enter="load" />
      </el-form-item>
      <el-form-item label="类型">
        <el-select v-model="filters.node_type" clearable placeholder="全部" @change="load">
          <el-option label="VLESS" value="vless" />
          <el-option label="Shadowsocks" value="shadowsocks" />
        </el-select>
      </el-form-item>
      <el-form-item label="地区">
        <el-select v-model="filters.country" clearable placeholder="全部" @change="load">
          <el-option v-for="country in countryOptions" :key="country" :label="country" :value="country" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="load">查询</el-button>
      </el-form-item>
    </el-form>

    <el-table
      :data="rows"
      v-loading="loading"
      @selection-change="(items) => (selected = items.map((item) => item.id))"
    >
      <el-table-column type="selection" width="45" />
      <el-table-column prop="name" label="名称" min-width="150" />
      <el-table-column prop="type" label="类型" width="110" />
      <el-table-column prop="country" label="地区" width="90" />
      <el-table-column prop="server" label="服务器" min-width="150" show-overflow-tooltip />
      <el-table-column prop="port" label="端口" width="80" />
      <el-table-column prop="source_name" label="来源" width="110" />
      <el-table-column label="凭证" width="120">
        <template #default="{ row }">
          {{ row.uuid_masked || row.password_masked || '-' }}
        </template>
      </el-table-column>
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <el-tag :type="row.enabled ? 'success' : 'info'">
            {{ row.enabled ? '启用' : '停用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="150" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      class="pagination"
      layout="total, prev, pager, next"
      :total="total"
      :page-size="pageSize"
      :current-page="page"
      @current-change="(value) => { page = value; load() }"
    />

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑节点' : '添加自有节点'" width="640px">
      <el-form label-width="120px">
        <el-form-item label="名称">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="form.type" style="width: 100%">
            <el-option label="VLESS" value="vless" />
            <el-option label="Shadowsocks" value="shadowsocks" />
          </el-select>
        </el-form-item>
        <el-form-item label="服务器">
          <el-input v-model="form.server" />
        </el-form-item>
        <el-form-item label="端口">
          <el-input-number v-model="form.port" :min="1" :max="65535" />
        </el-form-item>
        <template v-if="form.type === 'vless'">
          <el-form-item label="UUID">
            <el-input v-model="form.uuid" />
          </el-form-item>
          <el-form-item label="传输">
            <el-input v-model="form.network" placeholder="tcp / ws" />
          </el-form-item>
          <el-form-item label="安全">
            <el-input v-model="form.security" placeholder="reality / tls" />
          </el-form-item>
          <el-form-item label="TLS">
            <el-switch v-model="form.tls" />
          </el-form-item>
          <el-form-item label="SNI">
            <el-input v-model="form.sni" />
          </el-form-item>
          <el-form-item label="指纹">
            <el-input v-model="form.fingerprint" placeholder="chrome" />
          </el-form-item>
          <el-form-item label="Public Key">
            <el-input v-model="form.public_key" />
          </el-form-item>
          <el-form-item label="Short ID">
            <el-input v-model="form.short_id" />
          </el-form-item>
          <el-form-item label="Path">
            <el-input v-model="form.path" />
          </el-form-item>
          <el-form-item label="Host">
            <el-input v-model="form.host" />
          </el-form-item>
        </template>
        <template v-else>
          <el-form-item label="密码">
            <el-input v-model="form.password" show-password />
          </el-form-item>
          <el-form-item label="加密方式">
            <el-input v-model="form.cipher" placeholder="aes-256-gcm" />
          </el-form-item>
        </template>
        <el-form-item label="地区">
          <el-input v-model="form.country" placeholder="留空自动识别" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
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
  batchNodes,
  createNode,
  deleteNode,
  getNode,
  listNodes,
  updateNode
} from '../api'

const countryOptions = [
  '香港', '台湾', '日本', '韩国', '新加坡', '美国', '英国',
  '德国', '法国', '马来西亚', '墨西哥', '俄罗斯', '澳大利亚',
  '加拿大', '泰国', '越南', '印度', '荷兰', '印尼', '菲律宾'
]

const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const loading = ref(false)
const saving = ref(false)
const selected = ref([])
const dialogVisible = ref(false)
const editing = ref(null)
const filters = reactive({
  keyword: '',
  source_name: '',
  node_type: '',
  country: ''
})
const form = reactive({
  name: '',
  type: 'vless',
  server: '',
  port: 443,
  uuid: '',
  password: '',
  cipher: '',
  network: '',
  security: '',
  tls: false,
  sni: '',
  fingerprint: '',
  public_key: '',
  short_id: '',
  path: '',
  host: '',
  country: '',
  enabled: true
})

async function load() {
  loading.value = true
  try {
    const params = {
      page: page.value,
      page_size: pageSize
    }
    if (filters.keyword) params.keyword = filters.keyword
    if (filters.source_name) params.source_name = filters.source_name
    if (filters.node_type) params.node_type = filters.node_type
    if (filters.country) params.country = filters.country
    const { data } = await listNodes(params)
    rows.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = null
  Object.assign(form, {
    name: '',
    type: 'vless',
    server: '',
    port: 443,
    uuid: '',
    password: '',
    cipher: '',
    network: '',
    security: '',
    tls: false,
    sni: '',
    fingerprint: '',
    public_key: '',
    short_id: '',
    path: '',
    host: '',
    country: '',
    enabled: true
  })
  dialogVisible.value = true
}

async function openEdit(row) {
  editing.value = row
  const { data } = await getNode(row.id)
  Object.assign(form, {
    name: data.name,
    type: data.type,
    server: data.server,
    port: data.port,
    uuid: data.uuid || '',
    password: data.password || '',
    cipher: data.cipher || '',
    network: data.network || '',
    security: data.security || '',
    tls: !!data.tls,
    sni: data.sni || '',
    fingerprint: data.fingerprint || '',
    public_key: data.public_key || '',
    short_id: data.short_id || '',
    path: data.path || '',
    host: data.host || '',
    country: data.country || '',
    enabled: data.enabled
  })
  dialogVisible.value = true
}

async function save() {
  saving.value = true
  try {
    const payload = { ...form }
    for (const key of Object.keys(payload)) {
      if (payload[key] === '') payload[key] = null
    }
    if (editing.value) {
      await updateNode(editing.value.id, payload)
    } else {
      await createNode(payload)
    }
    dialogVisible.value = false
    ElMessage.success('保存成功')
    await load()
  } finally {
    saving.value = false
  }
}

async function remove(row) {
  await ElMessageBox.confirm(`确认删除节点「${row.name}」？`, '删除确认', {
    type: 'warning'
  })
  await deleteNode(row.id)
  ElMessage.success('已删除')
  await load()
}

async function batchAction(action) {
  const label = { enable: '启用', disable: '禁用', delete: '删除' }[action]
  if (action === 'delete') {
    await ElMessageBox.confirm(`确认删除选中的 ${selected.value.length} 个节点？`, '批量删除', {
      type: 'warning'
    })
  }
  await batchNodes({ ids: selected.value, action })
  ElMessage.success(`已${label} ${selected.value.length} 个节点`)
  await load()
}

onMounted(load)
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.filters {
  margin-bottom: 8px;
}

.pagination {
  margin-top: 16px;
  justify-content: flex-end;
}
</style>
