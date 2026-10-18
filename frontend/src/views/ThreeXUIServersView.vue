<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">3x-ui 服务器</h2>
        <p class="page-subtitle">维护面板连接信息，并查看异步转发任务。</p>
      </div>
      <el-button type="primary" @click="openCreate">
        <el-icon><Plus /></el-icon>
        添加服务器
      </el-button>
    </div>

    <div class="server-grid" v-loading="loading">
      <div v-for="server in servers" :key="server.id" class="surface-card server-card">
        <div class="server-card-head">
          <div>
            <strong>{{ server.name }}</strong>
            <span class="server-address">{{ server.domain || server.ip || '未填写地址' }}</span>
          </div>
          <el-tag :type="server.enabled ? 'success' : 'info'">{{ server.enabled ? '启用' : '停用' }}</el-tag>
        </div>
        <div class="server-meta">
          <span>版本 {{ server.version }}</span>
          <span>Token {{ server.api_token_prefix }}...</span>
          <span>API {{ apiStatusLabel(server.last_api_status) }}</span>
        </div>
        <p v-if="server.note" class="server-note">{{ server.note }}</p>
        <p v-if="server.last_error" class="server-error">{{ server.last_error }}</p>
        <div class="server-footer">
          <span>检测：{{ formatTime(server.last_api_check_at) }}</span>
          <div>
            <el-button size="small" :loading="checkingId === server.id" @click="checkServer(server)">检测 API</el-button>
            <el-button size="small" type="warning" plain @click="openTestInbound(server)">测试创建入站</el-button>
            <el-button size="small" @click="openEdit(server)">编辑</el-button>
            <el-button size="small" type="danger" plain @click="removeServer(server)">删除</el-button>
          </div>
        </div>
      </div>
      <el-empty v-if="!servers.length && !loading" description="还没有配置 3x-ui 服务器" />
    </div>

    <div class="surface-card task-card">
      <div class="section-heading">
        <div>
          <h3>转发任务</h3>
          <p>任务由后台每 30 秒自动处理，浏览器不会直接连接 3x-ui。</p>
        </div>
        <el-button text @click="loadData">刷新</el-button>
      </div>
      <el-table :data="tasks" size="small">
        <el-table-column prop="id" label="任务" width="80" />
        <el-table-column label="源节点" min-width="160">
          <template #default="{ row }">节点 #{{ row.source_node_id }}</template>
        </el-table-column>
        <el-table-column label="目标服务器" min-width="160">
          <template #default="{ row }">服务器 #{{ row.target_server_id }}</template>
        </el-table-column>
        <el-table-column prop="template" label="模板" width="150" />
        <el-table-column label="转发方式" width="180">
          <template #default="{ row }">{{ forwardModeLabel(row.forward_mode) }}</template>
        </el-table-column>
        <el-table-column prop="listen_port" label="端口" width="80" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }"><el-tag :type="taskTagType(row.status)">{{ taskLabel(row.status) }}</el-tag></template>
        </el-table-column>
        <el-table-column label="进度" min-width="190">
          <template #default="{ row }">
            <div class="task-progress">
              <el-progress
                :percentage="row.progress || 0"
                :status="progressStatus(row)"
                :stroke-width="8"
              />
              <span class="task-stage">{{ row.stage || '等待后台处理' }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="result_node_id" label="转发节点" width="100" />
        <el-table-column label="错误信息" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">{{ row.error_message || '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.status === 'failed'" size="small" type="warning" @click="retryTask(row)">重试</el-button>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑 3x-ui 服务器' : '添加 3x-ui 服务器'" width="620px">
      <el-form label-width="120px">
        <el-form-item label="名称" required><el-input v-model="form.name" maxlength="128" /></el-form-item>
        <el-form-item label="服务器 IP"><el-input v-model="form.ip" placeholder="与域名至少填写一个" /></el-form-item>
        <el-form-item label="服务器域名"><el-input v-model="form.domain" placeholder="生成节点链接时优先使用域名" /></el-form-item>
        <el-form-item label="API 地址" required><el-input v-model="form.api_url" placeholder="支持面板根地址、带 WebBasePath 的地址或 /panel/api-docs" /></el-form-item>
        <el-form-item label="API Token" :required="!editing">
          <el-input v-model="form.api_token" type="password" show-password :placeholder="editing ? '留空表示保留原 Token' : '只在提交时传输，列表不会显示明文'" />
        </el-form-item>
        <el-form-item label="3x-ui 版本"><el-input v-model="form.version" /></el-form-item>
        <el-form-item label="到期时间"><el-date-picker v-model="form.expires_at" type="datetime" value-format="YYYY-MM-DDTHH:mm:ssZ" placeholder="可选" /></el-form-item>
        <el-form-item label="启用"><el-switch v-model="form.enabled" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="form.note" type="textarea" :rows="3" maxlength="2000" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="testInboundVisible" title="测试创建 3x-ui 入站" width="560px">
      <el-alert
        title="这会在目标 3x-ui 面板创建一个真实入站，用于验证 API Token、入站新增和 Xray 重载。"
        type="warning"
        :closable="false"
      />
      <p class="test-inbound-server">目标服务器：{{ testInboundServer?.name }} · {{ testInboundServer?.domain || testInboundServer?.ip }}</p>
      <el-form label-width="100px">
        <el-form-item label="协议模板">
          <el-select v-model="testInboundForm.template" style="width: 100%">
            <el-option label="VLESS TCP" value="vless_tcp" />
            <el-option label="VLESS WebSocket + TLS" value="vless_ws_tls" />
            <el-option label="VMess WebSocket + TLS" value="vmess_ws_tls" />
            <el-option label="Trojan TCP + TLS" value="trojan_tcp_tls" />
            <el-option label="Shadowsocks TCP" value="shadowsocks_tcp" />
          </el-select>
        </el-form-item>
        <el-form-item label="监听端口">
          <el-input-number v-model="testInboundForm.port" :min="1" :max="65535" placeholder="自动从 12900 分配" />
        </el-form-item>
        <el-form-item label="入站备注">
          <el-input v-model="testInboundForm.remark" maxlength="255" placeholder="留空自动生成测试入站备注" />
        </el-form-item>
      </el-form>
      <el-alert v-if="testInboundResult" :title="testInboundResult.message" type="success" :closable="false">
        <p>入站 ID：{{ testInboundResult.inbound_id }} · {{ testInboundResult.protocol }} · 端口 {{ testInboundResult.port }}</p>
      </el-alert>
      <template #footer>
        <el-button @click="testInboundVisible = false">关闭</el-button>
        <el-button type="primary" :loading="testInboundSaving" @click="createTestInbound">调用 API 创建入站</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, onBeforeUnmount, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  checkThreeXUIServer,
  createThreeXUITestInbound,
  createThreeXUIServer,
  deleteThreeXUIServer,
  listThreeXUIServers,
  listThreeXUITasks,
  updateThreeXUIServer,
  retryThreeXUITask
} from '../api'

const servers = ref([])
const tasks = ref([])
const loading = ref(false)
const saving = ref(false)
const checkingId = ref(null)
const testInboundSaving = ref(false)
const testInboundVisible = ref(false)
const testInboundServer = ref(null)
const testInboundResult = ref(null)
const dialogVisible = ref(false)
const editing = ref(null)
const form = reactive({
  name: '', ip: '', domain: '', api_url: '', api_token: '', version: '3.8.5',
  expires_at: null, enabled: true, note: ''
})
const testInboundForm = reactive({ template: 'vless_tcp', port: null, remark: '' })
let timer = null

async function loadData() {
  loading.value = true
  try {
    const [serverResponse, taskResponse] = await Promise.all([listThreeXUIServers(), listThreeXUITasks({ limit: 100 })])
    servers.value = serverResponse.data
    tasks.value = taskResponse.data
  } finally {
    loading.value = false
  }
}

function resetForm() {
  Object.assign(form, { name: '', ip: '', domain: '', api_url: '', api_token: '', version: '3.8.5', expires_at: null, enabled: true, note: '' })
}

function openCreate() { editing.value = null; resetForm(); dialogVisible.value = true }

function openEdit(server) {
  editing.value = server
  Object.assign(form, { name: server.name, ip: server.ip || '', domain: server.domain || '', api_url: server.api_url, api_token: '', version: server.version, expires_at: server.expires_at, enabled: server.enabled, note: server.note || '' })
  dialogVisible.value = true
}

function openTestInbound(server) {
  testInboundServer.value = server
  testInboundResult.value = null
  Object.assign(testInboundForm, { template: 'vless_tcp', port: null, remark: '' })
  testInboundVisible.value = true
}

async function createTestInbound() {
  if (!testInboundServer.value) return
  testInboundSaving.value = true
  try {
    const payload = { template: testInboundForm.template, remark: testInboundForm.remark.trim() || null }
    if (testInboundForm.port) payload.port = testInboundForm.port
    const { data } = await createThreeXUITestInbound(testInboundServer.value.id, payload)
    testInboundResult.value = data
    ElMessage.success(`测试入站创建成功，ID ${data.inbound_id}`)
    await loadData()
  } finally {
    testInboundSaving.value = false
  }
}

async function save() {
  if (!form.name.trim() || !form.api_url.trim() || (!form.ip.trim() && !form.domain.trim()) || (!editing.value && !form.api_token.trim())) {
    ElMessage.warning('请填写名称、服务器地址、API 地址和 API Token')
    return
  }
  saving.value = true
  try {
    const payload = { ...form }
    if (editing.value && !payload.api_token) delete payload.api_token
    await (editing.value ? updateThreeXUIServer(editing.value.id, payload) : createThreeXUIServer(payload))
    dialogVisible.value = false
    ElMessage.success('保存成功')
    await loadData()
  } finally { saving.value = false }
}

async function checkServer(server) {
  checkingId.value = server.id
  try {
    const { data } = await checkThreeXUIServer(server.id)
    ElMessage[data.status === 'healthy' ? 'success' : 'error'](`${data.message}${data.inbound_count == null ? '' : `，入站 ${data.inbound_count} 个`}`)
    await loadData()
  } finally { checkingId.value = null }
}

async function retryTask(task) {
  try {
    await retryThreeXUITask(task.id)
    ElMessage.success('任务已重新排队')
    await loadData()
  } catch {
    // 请求错误由统一客户端提示，避免重复弹窗。
  }
}

async function removeServer(server) {
  try {
    await ElMessageBox.confirm(`确认删除服务器「${server.name}」？有转发任务或映射时系统会阻止删除。`, '删除确认', { type: 'warning' })
    await deleteThreeXUIServer(server.id)
    ElMessage.success('服务器已删除')
    await loadData()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') throw error
  }
}

function formatTime(value) { return value ? new Date(value).toLocaleString() : '-' }
function apiStatusLabel(value) { return ({ healthy: '正常', failed: '失败', unknown: '未检测' })[value] || '未知' }
function taskLabel(value) { return ({ pending: '待处理', running: '执行中', succeeded: '成功', failed: '失败' })[value] || value }
function taskTagType(value) { return ({ pending: 'info', running: 'warning', succeeded: 'success', failed: 'danger' })[value] || 'info' }
function progressStatus(task) {
  return ({ succeeded: 'success', failed: 'exception' })[task.status] || undefined
}
function forwardModeLabel(value) { return value === 'port_forward' ? '端口转发' : '新建入站 + 原始出站' }

onMounted(() => { loadData(); timer = window.setInterval(loadData, 10000) })
onBeforeUnmount(() => { if (timer) window.clearInterval(timer) })
</script>

<style scoped>
.server-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; min-height: 120px; }
.server-card { padding: 18px; }
.server-card-head, .server-footer, .section-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.server-card-head strong { display: block; font-size: 16px; }
.server-address { display: block; margin-top: 5px; color: var(--app-text-secondary); font-size: 12px; word-break: break-all; }
.server-meta { display: flex; flex-wrap: wrap; gap: 8px 14px; margin-top: 18px; color: var(--app-text-secondary); font-size: 12px; }
.server-note, .server-error { margin: 14px 0 0; color: var(--app-text-secondary); font-size: 12px; line-height: 1.6; }
.server-error { color: var(--el-color-danger); }
.server-footer { margin-top: 18px; padding-top: 12px; border-top: 1px solid var(--app-border); color: var(--app-text-muted); font-size: 11px; }
.task-card { margin-top: 20px; padding: 18px; }
.section-heading { margin-bottom: 14px; }
.section-heading h3 { margin: 0; font-size: 16px; }
.section-heading p { margin: 5px 0 0; color: var(--app-text-muted); font-size: 12px; }
.task-progress { min-width: 160px; }
.task-stage { display: block; margin-top: 4px; color: var(--app-text-muted); font-size: 11px; line-height: 1.3; }
.test-inbound-server { margin: 16px 0; color: var(--app-text-secondary); font-size: 13px; }
@media (max-width: 768px) { .server-grid { grid-template-columns: 1fr; } .task-card { overflow-x: auto; } }
</style>
