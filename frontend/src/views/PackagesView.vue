<template>
  <div>
    <div class="page-header">
      <h2>套餐管理</h2>
      <el-button type="primary" @click="openCreate">创建套餐</el-button>
    </div>

    <el-table :data="packages" v-loading="loading">
      <el-table-column prop="name" label="套餐名称" min-width="140" />
      <el-table-column prop="subscription_name" label="订阅显示名称" min-width="140" />
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.enabled ? 'success' : 'info'">
            {{ row.enabled ? '开启' : '禁用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="token_prefix" label="Token 前缀" width="120" />
      <el-table-column label="订阅地址" min-width="220" show-overflow-tooltip>
        <template #default="{ row }">
          <span v-if="row.subscription_url">{{ row.subscription_url }}</span>
          <span v-else class="muted">重新生成 Token 后可见</span>
        </template>
      </el-table-column>
      <el-table-column prop="description" label="说明" min-width="160" show-overflow-tooltip />
      <el-table-column label="创建时间" width="170">
        <template #default="{ row }">
          {{ formatTime(row.created_at) }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="300" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button
            size="small"
            :disabled="!row.subscription_url"
            @click="copyUrl(row)"
          >
            复制地址
          </el-button>
          <el-button size="small" @click="preview(row)">预览</el-button>
          <el-button size="small" @click="regenerate(row)">刷新 Token</el-button>
          <el-button size="small" :type="row.enabled ? 'warning' : 'success'" @click="toggle(row)">
            {{ row.enabled ? '禁用' : '启用' }}
          </el-button>
          <el-button size="small" type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑套餐' : '创建套餐'" width="720px">
      <el-form label-width="110px">
        <el-form-item label="名称">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="订阅显示名称">
          <el-input v-model="form.subscription_name" placeholder="留空默认使用套餐名称" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="form.description" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
        <el-divider content-position="left">筛选规则</el-divider>
        <el-form-item label="来源">
          <el-select v-model="form.rules.source_filter" multiple filterable allow-create default-first-option style="width: 100%">
            <el-option v-for="source in sourceOptions" :key="source" :label="source" :value="source" />
          </el-select>
        </el-form-item>
        <el-form-item label="地区">
          <el-select v-model="form.rules.country_filter" multiple clearable style="width: 100%">
            <el-option v-for="country in countryOptions" :key="country" :label="country" :value="country" />
          </el-select>
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="form.rules.type_filter" multiple clearable style="width: 100%">
            <el-option label="VLESS" value="vless" />
            <el-option label="Shadowsocks" value="shadowsocks" />
          </el-select>
        </el-form-item>
        <el-form-item label="包含关键词">
          <el-select v-model="form.rules.include_keywords" multiple filterable allow-create default-first-option style="width: 100%" />
        </el-form-item>
        <el-form-item label="排除关键词">
          <el-select v-model="form.rules.exclude_keywords" multiple filterable allow-create default-first-option style="width: 100%" />
        </el-form-item>
        <el-form-item label="重命名规则">
          <el-input v-model="renameJson" type="textarea" :rows="3" placeholder='[{"replacements":[{"from":"香港","to":"HK"}],"country_abbr":true,"numbered":true}]' />
        </el-form-item>
        <el-form-item label="排序规则">
          <el-input v-model="sortJson" type="textarea" :rows="2" placeholder='[{"field":"country","order":["香港","日本"]}]' />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="previewVisible" title="套餐节点预览" width="760px">
      <el-table :data="previewRows" max-height="480">
        <el-table-column prop="name" label="名称" min-width="140" />
        <el-table-column prop="type" label="类型" width="100" />
        <el-table-column prop="country" label="地区" width="90" />
        <el-table-column prop="server" label="服务器" min-width="150" show-overflow-tooltip />
        <el-table-column prop="port" label="端口" width="80" />
        <el-table-column prop="source_name" label="来源" width="110" />
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  createPackage,
  deletePackage,
  getPackage,
  listPackages,
  listSources,
  previewPackage,
  regenerateToken,
  togglePackage,
  updatePackage
} from '../api'

const countryOptions = [
  '香港', '台湾', '日本', '韩国', '新加坡', '美国', '英国',
  '德国', '法国', '马来西亚', '墨西哥', '俄罗斯', '澳大利亚',
  '加拿大', '泰国', '越南', '印度', '荷兰', '印尼', '菲律宾'
]

const packages = ref([])
const sourceOptions = ref([])
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const previewVisible = ref(false)
const previewRows = ref([])
const editing = ref(null)
const renameJson = ref('[]')
const sortJson = ref('[]')
const form = reactive({
  name: '',
  subscription_name: '',
  description: '',
  enabled: true,
  rules: {
    source_filter: [],
    country_filter: [],
    type_filter: [],
    include_keywords: [],
    exclude_keywords: []
  }
})

function parseJson(text, fallback) {
  try {
    const value = JSON.parse(text)
    return Array.isArray(value) ? value : fallback
  } catch {
    return fallback
  }
}

async function load() {
  loading.value = true
  try {
    const { data } = await listPackages()
    packages.value = data
  } finally {
    loading.value = false
  }
}

async function loadSources() {
  const { data } = await listSources()
  sourceOptions.value = data.items.map((item) => item.name)
}

function resetForm() {
  Object.assign(form, {
    name: '',
    subscription_name: '',
    description: '',
    enabled: true,
    rules: {
      source_filter: [],
      country_filter: [],
      type_filter: [],
      include_keywords: [],
      exclude_keywords: []
    }
  })
  renameJson.value = '[]'
  sortJson.value = '[]'
}

function openCreate() {
  editing.value = null
  resetForm()
  dialogVisible.value = true
}

async function openEdit(row) {
  editing.value = row
  const { data } = await getPackage(row.id)
  Object.assign(form, {
    name: data.name,
    subscription_name: data.subscription_name || '',
    description: data.description || '',
    enabled: data.enabled,
    rules: {
      source_filter: data.rules.source_filter || [],
      country_filter: data.rules.country_filter || [],
      type_filter: data.rules.type_filter || [],
      include_keywords: data.rules.include_keywords || [],
      exclude_keywords: data.rules.exclude_keywords || []
    }
  })
  renameJson.value = JSON.stringify(data.rules.rename_rules || [])
  sortJson.value = JSON.stringify(data.rules.sort_rules || [])
  dialogVisible.value = true
}

async function save() {
  saving.value = true
  try {
    const payload = {
      ...form,
      rules: {
        ...form.rules,
        rename_rules: parseJson(renameJson.value, []),
        sort_rules: parseJson(sortJson.value, [])
      }
    }
    let result
    if (editing.value) {
      result = await updatePackage(editing.value.id, payload)
    } else {
      result = await createPackage(payload)
      const { token, subscription_url } = result.data
      ElMessageBox.alert(
        `订阅 Token：${token}\n订阅地址：${subscription_url}`,
        '套餐已创建（Token 仅显示一次）',
        { confirmButtonText: '我已保存' }
      )
      await load()
    }
    dialogVisible.value = false
    ElMessage.success('保存成功')
    await load()
  } finally {
    saving.value = false
  }
}

async function regenerate(row) {
  const { data } = await regenerateToken(row.id)
  ElMessageBox.alert(
    `新 Token：${data.token}\n订阅地址：${data.subscription_url}`,
    'Token 已重生成（旧 Token 立即失效）',
    { confirmButtonText: '我已保存' }
  )
  await load()
}

async function copyUrl(row) {
  try {
    await navigator.clipboard.writeText(row.subscription_url)
    ElMessage.success('订阅地址已复制')
  } catch {
    ElMessage.error('复制失败，请手动复制')
  }
}

async function toggle(row) {
  await togglePackage(row.id)
  ElMessage.success(row.enabled ? '已禁用套餐' : '已启用套餐')
  await load()
}

async function preview(row) {
  const { data } = await previewPackage(row.id)
  previewRows.value = data
  previewVisible.value = true
}

async function remove(row) {
  await ElMessageBox.confirm(`确认删除套餐「${row.name}」？`, '删除确认', {
    type: 'warning'
  })
  await deletePackage(row.id)
  ElMessage.success('已删除')
  await load()
}

function formatTime(value) {
  return value ? new Date(value).toLocaleString() : '-'
}

onMounted(() => {
  load()
  loadSources()
})
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.muted {
  color: #9ca3af;
}
</style>
