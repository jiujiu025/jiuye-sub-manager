<template>
  <div class="page">
    <div class="surface-card settings-card">
    <el-form label-width="200px">
      <el-form-item label="自动同步间隔（分钟）">
        <el-input-number v-model="form.sync_interval_minutes" :min="1" :max="1440" />
      </el-form-item>
      <el-form-item label="定时同步开关">
        <el-switch v-model="form.sync_enabled" />
      </el-form-item>
      <el-form-item label="订阅缓存 TTL（秒）">
        <el-input-number v-model="form.cache_ttl_seconds" :min="30" :max="86400" />
      </el-form-item>
      <el-form-item label="来源去重优先级">
        <el-select
          v-model="form.dedup_source_priority"
          multiple
          filterable
          allow-create
          default-first-option
          style="width: 100%"
        >
          <el-option v-for="source in sourceOptions" :key="source" :label="source" :value="source" />
        </el-select>
        <div class="hint">排在前面的来源优先保留，自有节点始终最高</div>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :loading="saving" @click="save">保存设置</el-button>
      </el-form-item>
    </el-form>
    <el-alert
      type="info"
      :closable="false"
      title="生效说明"
      description="同步间隔、定时同步开关、缓存 TTL、去重优先级保存后立即生效；JWT 密钥、管理员密码、HTTP 超时等配置需修改 .env 后重启服务。"
    />
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getSystemSettings, listSources, updateSystemSettings } from '../api'

const saving = ref(false)
const sourceOptions = ref(['自有节点'])
const form = reactive({
  sync_interval_minutes: 5,
  sync_enabled: true,
  cache_ttl_seconds: 300,
  dedup_source_priority: []
})

async function load() {
  const { data } = await getSystemSettings()
  Object.assign(form, data)
}

async function loadSources() {
  const { data } = await listSources()
  const names = data.items.map((item) => item.name)
  sourceOptions.value = ['自有节点', ...names]
}

async function save() {
  saving.value = true
  try {
    await updateSystemSettings(form)
    ElMessage.success('设置已保存并生效')
    await load()
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  load()
  loadSources()
})
</script>

<style scoped>
.settings-card {
  max-width: 720px;
}

.hint {
  margin-top: 4px;
  color: #9ca3af;
  font-size: 12px;
}
</style>
