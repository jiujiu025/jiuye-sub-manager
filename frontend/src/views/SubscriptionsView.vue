<template>
  <div class="page">
    <div class="page-header page-toolbar">
      <div>
        <h2 class="page-title">客户订阅</h2>
        <p class="page-subtitle">按客户开通独立订阅，Token 生命周期不会影响旧套餐。</p>
      </div>
      <div class="page-actions">
        <div class="page-header-mark"><el-icon><List /></el-icon><span>SALES</span></div>
        <el-button type="primary" @click="openCreate"><el-icon><Plus /></el-icon>开通订阅</el-button>
      </div>
    </div>

    <div class="view-switcher">
      <el-radio-group v-model="viewMode" size="small" @change="switchView">
        <el-radio-button label="customers">客户订阅</el-radio-button>
        <el-radio-button label="lines">全部线路</el-radio-button>
      </el-radio-group>
      <span class="view-switcher-hint">按线路编号和开通时间查看，可筛选后批量导出。</span>
    </div>

    <div v-if="viewMode === 'customers'" class="toolbar-row">
      <el-input v-model="keyword" clearable placeholder="搜索客户或套餐" class="search-input"><template #prefix><el-icon><Search /></el-icon></template></el-input>
      <el-select v-model="statusFilter" clearable placeholder="全部状态" class="status-select"><el-option label="生效中" value="active" /><el-option label="暂停" value="paused" /><el-option label="已取消" value="cancelled" /></el-select>
    </div>

    <div v-if="isAdmin" class="lookup-panel surface-card">
      <div class="lookup-copy"><strong>找回订阅</strong><span>粘贴 Token 或完整订阅链接，查找客户订阅和历史套餐</span></div>
      <el-input v-model="lookupQuery" clearable class="lookup-input" placeholder="输入 Token 或 https://example.com/sub/..." @keyup.enter="findSubscription"><template #prefix><el-icon><Search /></el-icon></template></el-input>
      <el-button type="primary" :loading="lookupLoading" @click="findSubscription">查找</el-button>
    </div>

    <div v-if="lookupResult" class="lookup-result surface-card">
      <div class="lookup-result-main">
        <div class="lookup-result-title"><el-tag size="small" :type="lookupResult.historical ? 'info' : lookupResult.kind === 'package' ? 'warning' : 'success'">{{ lookupResult.historical ? '历史 Token' : lookupResult.kind === 'package' ? '历史套餐' : '客户订阅' }}</el-tag><strong>{{ lookupResult.package_name }}</strong><span class="muted">Token {{ lookupResult.token_prefix }}…</span></div>
        <div class="lookup-result-meta"><span v-if="lookupResult.customer_name">客户：{{ lookupResult.customer_name }}</span><span v-if="lookupResult.manager_username">经理：{{ lookupResult.manager_username }}</span><span>状态：{{ lookupStatusLabel(lookupResult) }}</span><span>到期：{{ formatTime(lookupResult.expires_at, '长期有效') }}</span></div>
        <div class="lookup-result-note">备注：{{ lookupResult.note || '暂无备注' }}</div>
      </div>
      <div class="lookup-result-actions"><el-button v-if="!lookupResult.historical" link type="primary" @click="showLookupQr">二维码</el-button><el-button v-if="!lookupResult.historical" link type="primary" @click="copyLookupUrl">复制订阅</el-button><el-button v-if="lookupResult.historical" link type="primary" @click="openHistoryFromLookup">查看 Token 历史</el-button><el-button v-if="lookupResult.kind === 'customer_subscription'" link type="primary" @click="openNote(lookupResult)">编辑备注</el-button><el-button v-else-if="!lookupResult.historical" link type="primary" @click="router.push('/packages')">打开套餐管理</el-button><el-button link @click="lookupResult = null">关闭</el-button></div>
    </div>

    <div v-if="viewMode === 'lines'" class="line-toolbar">
      <el-input v-model="lineKeyword" clearable placeholder="搜索客户、套餐、线路" class="search-input" @keyup.enter="loadLines" />
      <el-input v-model="lineRegion" clearable placeholder="地区" class="region-input" @keyup.enter="loadLines" />
      <el-select v-model="lineStatus" clearable placeholder="全部状态" class="status-select" @change="loadLines">
        <el-option label="生效中" value="active" />
        <el-option label="暂停" value="paused" />
        <el-option label="已到期" value="expired" />
        <el-option label="已撤销" value="revoked" />
        <el-option label="已取消" value="cancelled" />
      </el-select>
      <el-button type="primary" :disabled="selectedLines.length === 0" @click="exportSelectedLines">导出选中线路</el-button>
      <span class="line-count">共 {{ lineTotal }} 条线路</span>
    </div>

    <div v-if="viewMode === 'lines'" v-loading="lineLoading" class="surface-card subscription-table-card">
      <el-table :data="lineRows" row-key="line_key" empty-text="暂无符合条件的线路" @selection-change="selectedLines = $event">
        <el-table-column type="selection" width="48" />
        <el-table-column prop="line_code" label="线路编号" width="175" />
        <el-table-column label="客户" min-width="150"><template #default="{ row }"><strong>{{ row.customer_name }}</strong><small>{{ row.package_name }}</small></template></el-table-column>
        <el-table-column prop="customer_region" label="地区" width="100" />
        <el-table-column label="线路" min-width="220"><template #default="{ row }"><strong>{{ row.node_name }}</strong><small>{{ row.node_code || '-' }} · {{ row.node_type }}</small></template></el-table-column>
        <el-table-column label="转发状态" width="110"><template #default="{ row }"><el-tag size="small" :type="row.forwarded ? 'success' : 'info'">{{ row.forwarded ? '已转发' : '未转发' }}</el-tag></template></el-table-column>
        <el-table-column label="添加时间" width="170"><template #default="{ row }">{{ formatTime(row.node_created_at) }}</template></el-table-column>
        <el-table-column label="到期时间" width="170"><template #default="{ row }">{{ formatTime(row.expires_at, '长期有效') }}</template></el-table-column>
        <el-table-column label="操作" width="150" fixed="right"><template #default="{ row }"><el-button link type="primary" @click="shareLine(row)">查看线路</el-button><el-button link type="primary" @click="showLineQr(row)">二维码</el-button></template></el-table-column>
      </el-table>
      <div class="line-pagination"><el-pagination v-model:current-page="linePage" v-model:page-size="linePageSize" layout="total, prev, pager, next" :total="lineTotal" @current-change="loadLines" /></div>
    </div>

    <div v-if="viewMode === 'customers'" v-loading="loading" class="surface-card subscription-table-card">
      <div class="group-hint"><el-icon><FolderOpened /></el-icon><span>按客户归类显示，点击客户行左侧箭头展开全部订阅</span><strong>{{ customerGroupCount }} 个客户 · {{ filteredSubscriptions.length }} 个订阅</strong></div>
      <el-table :data="groupedSubscriptions" row-key="rowKey" :tree-props="{ children: 'children' }" :row-class-name="tableRowClassName" empty-text="暂无客户订阅">
        <el-table-column label="客户" min-width="220">
          <template #default="{ row }">
            <div v-if="row.isCustomerGroup" class="customer-group-cell"><strong>{{ row.customer_name }}</strong><small>{{ row.subscription_count }} 个订阅 · {{ row.active_count }} 个生效</small></div>
            <div v-else class="subscription-cell"><strong>{{ row.package_name }}</strong><small>{{ row.token_prefix }}… · {{ tokenModeLabel(row.token_mode) }}</small></div>
          </template>
        </el-table-column>
        <el-table-column label="套餐 / 地区" min-width="190"><template #default="{ row }"><span v-if="row.isCustomerGroup" class="group-summary">{{ row.package_summary }}</span><span v-else>{{ row.package_name }}</span></template></el-table-column>
        <el-table-column label="开通时间" width="170"><template #default="{ row }"><span v-if="row.isCustomerGroup" class="group-label">最近开通 {{ formatTime(row.latest_started_at) }}</span><span v-else>{{ formatTime(row.started_at) }}</span></template></el-table-column>
        <el-table-column label="到期时间" width="170"><template #default="{ row }"><span v-if="row.isCustomerGroup" class="group-label">{{ row.earliest_expiry_label }}</span><span v-else>{{ formatTime(row.expires_at, '长期有效') }}</span></template></el-table-column>
        <el-table-column label="销售价" width="110"><template #default="{ row }"><span v-if="row.isCustomerGroup" class="group-total">¥{{ row.sale_total }}</span><span v-else>{{ row.sale_price == null ? '-' : `¥${row.sale_price}` }}</span></template></el-table-column>
        <el-table-column label="备注" min-width="180" show-overflow-tooltip><template #default="{ row }"><span v-if="row.isCustomerGroup" class="group-label">{{ row.children.some((item) => item.note) ? '有订阅备注' : '-' }}</span><span v-else>{{ row.note || '-' }}</span></template></el-table-column>
        <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag v-if="row.isCustomerGroup" type="success" effect="light">{{ row.active_count ? '有生效' : '已停机' }}</el-tag><el-tag v-else :type="statusType(row)">{{ statusLabel(row) }}</el-tag></template></el-table-column>
        <el-table-column label="操作" width="700" fixed="right"><template #default="{ row }"><template v-if="!row.isCustomerGroup"><el-button link type="primary" @click="openNote(row)">备注</el-button><el-button link type="primary" @click="preview(row)">节点</el-button><el-button link type="primary" @click="showQr(row)">二维码</el-button><el-button link type="primary" @click="copyUrl(row)">复制订阅</el-button><el-button link type="primary" @click="openTokenHistory(row)">Token 历史</el-button><el-button link type="primary" @click="renew(row)">续费</el-button><el-button v-if="row.status === 'paused'" link type="success" @click="resume(row)">恢复</el-button><el-button v-else-if="row.status === 'active' && !isExpired(row)" link type="warning" @click="suspend(row)">暂停</el-button><el-button v-if="row.status !== 'cancelled'" link type="danger" @click="cancel(row)">取消</el-button><el-button link type="primary" @click="regenerate(row)">换 Token</el-button><el-button link type="danger" :disabled="!!row.token_revoked_at || row.status === 'cancelled'" @click="revoke(row)">撤销</el-button></template><span v-else class="group-action-hint">展开查看订阅操作</span></template></el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="dialogVisible" title="开通客户订阅" width="560px" append-to-body>
      <el-form label-width="100px">
        <el-form-item label="客户" required><el-select v-model="form.customer_id" filterable placeholder="选择客户" style="width: 100%"><el-option v-for="item in customers" :key="item.id" :label="`${item.name}${item.region ? ` · ${item.region}` : ''}`" :value="item.id" /></el-select></el-form-item>
        <el-form-item label="套餐" required><el-select v-model="form.package_id" filterable placeholder="选择套餐" style="width: 100%"><el-option v-for="item in packages" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item>
        <el-form-item v-if="isAdmin" label="负责经理"><el-select v-model="form.manager_user_id" clearable filterable placeholder="跟随客户归属" style="width: 100%"><el-option v-for="manager in managers" :key="manager.id" :label="manager.username" :value="manager.id" /></el-select></el-form-item>
        <el-form-item label="Token 策略"><el-radio-group v-model="form.token_mode" class="token-mode-group"><el-radio-button label="generated">生成新 Token</el-radio-button><el-radio-button label="package">接管套餐 Token</el-radio-button><el-radio-button label="manual">手动输入</el-radio-button></el-radio-group><div class="form-hint">接管只允许一个订阅使用该套餐 Token；默认生成新 Token 最安全。</div></el-form-item>
        <el-form-item v-if="form.token_mode === 'manual'" label="自定义 Token"><el-input v-model="form.custom_token" type="password" show-password autocomplete="new-password" placeholder="16-256 位字母、数字或 URL 安全字符" /></el-form-item>
        <div class="form-row"><el-form-item label="开通时间"><el-date-picker v-model="form.started_at" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss" /></el-form-item><el-form-item label="到期时间"><el-date-picker v-model="form.expires_at" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss" placeholder="长期有效" /></el-form-item></div>
        <div class="form-row"><el-form-item label="销售价"><el-input v-model="form.sale_price" type="number" min="0" step="0.01" /></el-form-item><el-form-item label="销售成本价"><el-input v-model="form.sales_cost_price" type="number" min="0" step="0.01" /></el-form-item></div>
        <el-form-item v-if="isAdmin" label="公司成本价"><el-input v-model="form.company_cost_price" type="number" min="0" step="0.01" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="form.note" type="textarea" :rows="3" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="dialogVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="save">生成订阅</el-button></template>
    </el-dialog>

    <el-dialog v-model="tokenHistoryVisible" :title="`Token 历史 · ${tokenHistorySubscription?.customer_name || ''} · ${tokenHistorySubscription?.package_name || ''}`" width="780px" append-to-body>
      <el-alert title="历史版本默认只显示前缀；恢复会让旧 Token 重新成为当前有效 Token，并记录管理员操作。" type="warning" :closable="false" class="history-alert" />
      <el-table v-loading="tokenHistoryLoading" :data="tokenHistoryRows" empty-text="暂无 Token 历史">
        <el-table-column prop="version" label="版本" width="70" />
        <el-table-column label="Token" min-width="150"><template #default="{ row }">{{ row.token_prefix }}…</template></el-table-column>
        <el-table-column label="操作" width="110"><template #default="{ row }">{{ tokenActionLabel(row.action) }}</template></el-table-column>
        <el-table-column label="时间" width="170"><template #default="{ row }">{{ formatTime(row.valid_from) }}</template></el-table-column>
        <el-table-column label="操作人" width="110"><template #default="{ row }">{{ row.actor_username || '系统迁移' }}</template></el-table-column>
        <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag size="small" :type="row.valid_to ? 'info' : 'success'">{{ row.valid_to ? '历史版本' : '当前版本' }}</el-tag></template></el-table-column>
        <el-table-column v-if="isAdmin" label="操作" width="100"><template #default="{ row }"><el-button v-if="row.valid_to" link type="primary" @click="restoreHistory(row)">恢复</el-button></template></el-table-column>
      </el-table>
    </el-dialog>

    <el-dialog v-model="previewVisible" title="订阅节点预览" width="760px" append-to-body>
      <div v-loading="previewLoading">
        <el-table :data="previewRows" max-height="420" empty-text="当前订阅暂无可用节点">
          <el-table-column prop="name" label="节点名称" min-width="190" />
          <el-table-column prop="type" label="协议" width="120" />
          <el-table-column label="服务器" min-width="190"><template #default="{ row }">{{ row.server }}:{{ row.port }}</template></el-table-column>
          <el-table-column prop="country" label="地区" width="100"><template #default="{ row }">{{ row.country || '-' }}</template></el-table-column>
          <el-table-column label="线路到期" width="190"><template #default="{ row }"><el-date-picker v-if="row.line_id" v-model="row.expires_at" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss" clearable placeholder="长期有效" size="small" @change="saveLineExpiry(row)" /><span v-else>-</span></template></el-table-column>
          <el-table-column label="分享" width="130"><template #default="{ row }"><el-button link type="primary" @click="sharePreviewNode(row)">分享</el-button><el-button link type="primary" @click="showPreviewNodeQr(row)">二维码</el-button></template></el-table-column>
        </el-table>
      </div>
    </el-dialog>

    <el-dialog v-model="nodeShareVisible" :title="`分享节点 · ${nodeShareName}`" width="520px" append-to-body>
      <div class="node-share-body">
        <img v-if="nodeShareDataUrl" :src="nodeShareDataUrl" alt="节点分享二维码" class="qr-image" />
        <el-input v-model="nodeShareContent" type="textarea" :rows="4" readonly />
      </div>
      <template #footer><el-button @click="nodeShareVisible = false">关闭</el-button><el-button type="primary" @click="copyNodeShare">复制完整链接</el-button></template>
    </el-dialog>

    <el-dialog v-model="qrVisible" :title="`订阅二维码 · ${qrName}`" width="380px" append-to-body>
      <div class="qr-body">
        <img v-if="qrDataUrl" :src="qrDataUrl" alt="客户订阅二维码" class="qr-image" />
        <div class="qr-url">{{ qrUrl }}</div>
      </div>
      <template #footer>
        <el-button @click="qrVisible = false">关闭</el-button>
        <el-button type="primary" @click="copyQrUrl">复制订阅地址</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="noteDialogVisible" :title="`订阅备注 · ${noteSubscription?.customer_name || ''} · ${noteSubscription?.package_name || ''}`" width="460px" append-to-body>
      <el-input v-model="noteText" type="textarea" :rows="5" maxlength="2000" show-word-limit placeholder="记录线路交付、客户偏好或续费跟进事项" />
      <template #footer><el-button @click="noteDialogVisible = false">取消</el-button><el-button type="primary" :loading="noteSaving" @click="saveNote">保存备注</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import QRCode from 'qrcode'
import { cancelSubscription, createSubscription, exportManagerSubscriptionNode, exportSubscriptionLines, getPackageSubscriptionUrl, getSubscriptionTokenHistory, getSubscriptionUrl, listCustomers, listPackages, listSubscriptionLines, listSubscriptions, listUsers, lookupSubscription, previewCustomerSubscription, regenerateSubscriptionToken, renewSubscription, restoreSubscriptionToken, resumeSubscription, revokeSubscriptionToken, suspendSubscription, updateSubscription, updateSubscriptionLine } from '../api'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const subscriptions = ref([])
const viewMode = ref('customers')
const lineRows = ref([])
const selectedLines = ref([])
const lineLoading = ref(false)
const lineKeyword = ref('')
const lineRegion = ref('')
const lineStatus = ref('')
const linePage = ref(1)
const linePageSize = ref(50)
const lineTotal = ref(0)
const customers = ref([])
const packages = ref([])
const loading = ref(false)
const saving = ref(false)
const keyword = ref('')
const statusFilter = ref('')
const dialogVisible = ref(false)
const previewVisible = ref(false)
const previewLoading = ref(false)
const previewRows = ref([])
const previewSubscriptionId = ref(null)
const qrVisible = ref(false)
const qrDataUrl = ref('')
const qrUrl = ref('')
const qrName = ref('')
const noteDialogVisible = ref(false)
const noteSaving = ref(false)
const noteSubscription = ref(null)
const noteText = ref('')
const lookupQuery = ref('')
const lookupResult = ref(null)
const lookupLoading = ref(false)
const nodeShareVisible = ref(false)
const nodeShareName = ref('')
const nodeShareContent = ref('')
const nodeShareDataUrl = ref('')
const tokenHistoryVisible = ref(false)
const tokenHistoryLoading = ref(false)
const tokenHistoryRows = ref([])
const tokenHistorySubscription = ref(null)
const form = reactive({ customer_id: null, package_id: null, manager_user_id: null, token_mode: 'generated', custom_token: '', started_at: null, expires_at: null, sale_price: '', company_cost_price: '', sales_cost_price: '', note: '' })
const managers = ref([])
const authStore = useAuthStore()
const router = useRouter()
const route = useRoute()
const isAdmin = computed(() => authStore.role === 'admin')
const filteredSubscriptions = computed(() => subscriptions.value.filter((item) => {
  if (statusFilter.value && statusLabel(item) !== ({ active: '生效中', paused: '暂停', cancelled: '已取消' }[statusFilter.value])) return false
  const query = keyword.value.trim().toLowerCase()
  return !query || `${item.customer_name} ${item.package_name} ${item.note || ''}`.toLowerCase().includes(query)
}))
const groupedSubscriptions = computed(() => {
  const groups = new Map()
  for (const item of filteredSubscriptions.value) {
    let group = groups.get(item.customer_id)
    if (!group) {
      group = {
        rowKey: `customer-${item.customer_id}`,
        isCustomerGroup: true,
        customer_id: item.customer_id,
        customer_name: item.customer_name,
        children: [],
      }
      groups.set(item.customer_id, group)
    }
    group.children.push({ ...item, rowKey: `subscription-${item.id}`, isCustomerGroup: false })
  }
  return [...groups.values()].map((group) => {
    const children = group.children
    const activeCount = children.filter((item) => statusLabel(item) === '生效中').length
    const finiteExpiries = children.filter((item) => item.expires_at).map((item) => new Date(item.expires_at).getTime())
    const latestStartedAt = children.reduce((latest, item) => {
      const value = new Date(item.started_at).getTime()
      return value > latest ? value : latest
    }, 0)
    const saleTotal = children.reduce((total, item) => total + (item.sale_price == null ? 0 : Number(item.sale_price)), 0)
    const earliestExpiry = finiteExpiries.length ? Math.min(...finiteExpiries) : null
    return {
      ...group,
      subscription_count: children.length,
      active_count: activeCount,
      package_summary: children.map((item) => item.package_name).join('、'),
      latest_started_at: latestStartedAt ? new Date(latestStartedAt).toISOString() : null,
      earliest_expiry_label: earliestExpiry ? `最近到期 ${formatTime(new Date(earliestExpiry).toISOString())}` : '均为长期有效',
      sale_total: saleTotal.toFixed(2),
    }
  })
})
const customerGroupCount = computed(() => groupedSubscriptions.value.length)
function resetForm() { Object.assign(form, { customer_id: null, package_id: null, manager_user_id: null, token_mode: 'generated', custom_token: '', started_at: null, expires_at: null, sale_price: '', company_cost_price: '', sales_cost_price: '', note: '' }) }
async function openCreate() { await Promise.all([loadCustomers(), loadPackages(), loadManagers()]); resetForm(); dialogVisible.value = true }
async function load() { loading.value = true; try { const { data } = await listSubscriptions(); subscriptions.value = data; await nextTick(); document.querySelector('.notification-focus')?.scrollIntoView({ block: 'center' }) } finally { loading.value = false } }
async function loadLines() {
  lineLoading.value = true
  try {
    const { data } = await listSubscriptionLines({ page: linePage.value, page_size: linePageSize.value, keyword: lineKeyword.value || undefined, region: lineRegion.value || undefined, status: lineStatus.value || undefined })
    lineRows.value = data.items
    lineTotal.value = data.total
    selectedLines.value = []
  } finally { lineLoading.value = false }
}
async function switchView(mode) { if (mode === 'lines' && lineRows.value.length === 0) await loadLines() }
async function exportSelectedLines() {
  if (!selectedLines.value.length) return
  const { data } = await exportSubscriptionLines({ line_keys: selectedLines.value.map((row) => row.line_key), keyword: lineKeyword.value || null, region: lineRegion.value || null, status: lineStatus.value || null })
  const url = URL.createObjectURL(data)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = '客户线路清单.xlsx'
  anchor.click()
  URL.revokeObjectURL(url)
  ElMessage.success(`已导出 ${selectedLines.value.length} 条线路`)
}
async function loadCustomers() { const { data } = await listCustomers(); customers.value = data.filter((item) => item.is_active) }
async function loadPackages() { const { data } = await listPackages(); packages.value = data.filter((item) => item.enabled && !item.token_revoked_at) }
async function loadManagers() { if (!isAdmin.value) return; const { data } = await listUsers({ role: 'manager' }); managers.value = data.filter((item) => item.is_active) }
async function save() {
  if (!form.customer_id || !form.package_id) { ElMessage.warning('请选择客户和套餐'); return }
  if (form.token_mode === 'manual' && !form.custom_token.trim()) { ElMessage.warning('请输入自定义 Token'); return }
  saving.value = true
  try { const payload = { ...form }; for (const key of ['sale_price', 'company_cost_price', 'sales_cost_price']) if (payload[key] === '') payload[key] = null; if (payload.token_mode !== 'manual') delete payload.custom_token; const { data } = await createSubscription(payload); dialogVisible.value = false; await ElMessageBox.alert(`新 Token：${data.token}\n订阅地址：${data.subscription_url}`, '订阅已开通（仅显示一次）', { confirmButtonText: '我已保存' }); await load() } finally { saving.value = false }
}
async function copyUrl(row) { const { data } = await getSubscriptionUrl(row.id); await navigator.clipboard.writeText(data.subscription_url); ElMessage.success('订阅地址已复制') }
async function showQr(row) {
  try {
    const { data } = await getSubscriptionUrl(row.id)
    qrUrl.value = data.subscription_url
    qrName.value = `${row.customer_name} · ${row.package_name}`
    qrDataUrl.value = await QRCode.toDataURL(data.subscription_url, { width: 240, margin: 1 })
    qrVisible.value = true
  } catch {
    ElMessage.error('订阅地址或二维码生成失败')
  }
}
async function copyQrUrl() {
  try {
    await navigator.clipboard.writeText(qrUrl.value)
    ElMessage.success('订阅地址已复制')
  } catch {
    ElMessage.error('复制失败，请手动复制')
  }
}
async function findSubscription() {
  const query = lookupQuery.value.trim()
  if (!query) { ElMessage.warning('请输入 Token 或订阅链接'); return }
  lookupLoading.value = true
  try {
    const { data } = await lookupSubscription(query)
    lookupResult.value = data
  } catch (error) {
    lookupResult.value = null
    if (error.response?.status === 404) ElMessage.warning('未找到匹配的订阅记录')
    else ElMessage.error('查找订阅失败')
  } finally {
    lookupLoading.value = false
  }
}
async function openTokenHistory(row) {
  tokenHistorySubscription.value = row
  tokenHistoryVisible.value = true
  tokenHistoryLoading.value = true
  try {
    const { data } = await getSubscriptionTokenHistory(row.id)
    tokenHistoryRows.value = data
  } finally {
    tokenHistoryLoading.value = false
  }
}
async function openHistoryFromLookup() {
  if (!lookupResult.value?.historical) return
  const row = subscriptions.value.find((item) => item.id === lookupResult.value.id) || {
    id: lookupResult.value.id,
    customer_name: lookupResult.value.customer_name,
    package_name: lookupResult.value.package_name,
  }
  await openTokenHistory(row)
}
async function restoreHistory(row) {
  try {
    await ElMessageBox.confirm('恢复后该历史 Token 会重新成为当前有效 Token，当前 Token 将进入历史记录。确认继续吗？', '恢复历史 Token', { type: 'warning', confirmButtonText: '确认恢复', cancelButtonText: '取消' })
  } catch { return }
  const { data } = await restoreSubscriptionToken(tokenHistorySubscription.value.id, { version_id: row.id })
  await ElMessageBox.alert(`已恢复 Token：${data.token}\n订阅地址：${data.subscription_url}`, 'Token 已恢复（仅显示一次）', { confirmButtonText: '我已保存' })
  tokenHistoryVisible.value = false
  await load()
}
function lookupStatusLabel(item) {
  if (item.historical) return '历史 Token（已失效）'
  if (item.status === 'revoked') return '已撤销'
  if (item.status === 'disabled') return '已停用'
  if (item.status === 'paused') return '暂停'
  if (item.status === 'cancelled') return '已取消'
  if (item.expires_at && new Date(item.expires_at) <= new Date()) return '已到期'
  return '生效中'
}
async function getLookupUrl() {
  if (lookupResult.value.historical) throw new Error('历史 Token 不可直接使用')
  if (lookupResult.value.kind === 'package') return (await getPackageSubscriptionUrl(lookupResult.value.id)).data.subscription_url
  return (await getSubscriptionUrl(lookupResult.value.id)).data.subscription_url
}
async function copyLookupUrl() {
  try {
    await navigator.clipboard.writeText(await getLookupUrl())
    ElMessage.success('订阅地址已复制')
  } catch {
    ElMessage.error('当前订阅地址不可用')
  }
}
async function showLookupQr() {
  try {
    qrUrl.value = await getLookupUrl()
    qrName.value = lookupResult.value.package_name
    qrDataUrl.value = await QRCode.toDataURL(qrUrl.value, { width: 240, margin: 1 })
    qrVisible.value = true
  } catch {
    ElMessage.error('订阅地址或二维码生成失败')
  }
}
function openNote(row) {
  noteSubscription.value = row
  noteText.value = row.note || ''
  noteDialogVisible.value = true
}
async function saveNote() {
  if (!noteSubscription.value) return
  noteSaving.value = true
  try {
    const { data } = await updateSubscription(noteSubscription.value.id, { note: noteText.value.trim() || null })
    const index = subscriptions.value.findIndex((item) => item.id === data.id)
    if (index !== -1) subscriptions.value[index] = data
    noteDialogVisible.value = false
    ElMessage.success('订阅备注已保存')
  } finally {
    noteSaving.value = false
  }
}
async function preview(row) { previewSubscriptionId.value = row.id; previewLoading.value = true; previewVisible.value = true; try { const { data } = await previewCustomerSubscription(row.id); previewRows.value = data } finally { previewLoading.value = false } }
async function saveLineExpiry(row) {
  if (!row.line_id || !previewSubscriptionId.value) return
  try {
    await updateSubscriptionLine(previewSubscriptionId.value, row.line_id, { expires_at: row.expires_at || null })
    ElMessage.success('线路到期时间已更新')
    const { data } = await previewCustomerSubscription(previewSubscriptionId.value)
    previewRows.value = data
  } catch {
    ElMessage.error('线路到期时间更新失败')
  }
}
async function shareLine(row) { previewSubscriptionId.value = row.subscription_id; await sharePreviewNode({ id: row.node_id, name: row.node_name }) }
async function showLineQr(row) { await shareLine(row) }
async function sharePreviewNode(row) {
  try {
    const { data } = await exportManagerSubscriptionNode(previewSubscriptionId.value, row.id)
    nodeShareName.value = data.name
    nodeShareContent.value = data.content
    nodeShareDataUrl.value = await QRCode.toDataURL(data.content, { width: 240, margin: 1 })
    nodeShareVisible.value = true
  } catch (error) {
    ElMessage.error(error.response?.status === 404 ? '订阅已失效或节点不属于当前订阅' : '节点分享生成失败')
  }
}
async function showPreviewNodeQr(row) { await sharePreviewNode(row) }
async function copyNodeShare() { try { await navigator.clipboard.writeText(nodeShareContent.value); ElMessage.success('节点链接已复制') } catch { ElMessage.error('复制失败，请手动复制') } }
async function regenerate(row) { try { await ElMessageBox.confirm('旧 Token 会立即失效，确认生成新的订阅 Token 吗？', '更换 Token', { type: 'warning', confirmButtonText: '确认更换', cancelButtonText: '取消' }) } catch { return } const { data } = await regenerateSubscriptionToken(row.id); await ElMessageBox.alert(`新 Token：${data.token}\n订阅地址：${data.subscription_url}`, 'Token 已更换（仅显示一次）', { confirmButtonText: '我已保存' }); await load() }
async function revoke(row) { try { await ElMessageBox.confirm('撤销后订阅地址立即失效，确认继续吗？', '撤销 Token', { type: 'warning', confirmButtonText: '确认撤销', cancelButtonText: '取消' }) } catch { return } await revokeSubscriptionToken(row.id); ElMessage.success('Token 已撤销'); await load() }
async function renew(row) { const value = await ElMessageBox.prompt('请输入续费天数（1-3650）', '续费订阅', { inputPattern: /^[1-9]\d{0,3}$/, inputErrorMessage: '请输入 1-3650 的整数', confirmButtonText: '确认续费', cancelButtonText: '取消' }).catch(() => null); if (!value) return; await renewSubscription(row.id, { days: Number(value.value) }); ElMessage.success('订阅已续费'); await load() }
async function suspend(row) { try { await ElMessageBox.confirm('暂停后订阅链接将立即停止提供节点，确认继续吗？', '暂停订阅', { type: 'warning', confirmButtonText: '确认暂停', cancelButtonText: '取消' }) } catch { return } await suspendSubscription(row.id); ElMessage.success('订阅已暂停'); await load() }
async function resume(row) { await resumeSubscription(row.id); ElMessage.success('订阅已恢复'); await load() }
async function cancel(row) { try { await ElMessageBox.confirm('取消后将不能直接续费，只能保留历史记录，确认继续吗？', '取消订阅', { type: 'warning', confirmButtonText: '确认取消', cancelButtonText: '取消' }) } catch { return } await cancelSubscription(row.id); ElMessage.success('订阅已取消'); await load() }
function statusLabel(row) { if (row.token_revoked_at) return '已撤销'; if (row.status === 'paused') return '暂停'; if (row.status === 'cancelled') return '已取消'; if (row.expires_at && new Date(row.expires_at) <= new Date()) return '已到期'; return '生效中' }
function tokenModeLabel(mode) { return ({ generated: '新 Token', package: '套餐 Token', manual: '手动 Token', restored: '恢复 Token' }[mode] || 'Token') }
function tokenActionLabel(action) { return ({ created: '创建', regenerated: '重新生成', restored: '恢复', legacy: '历史迁移' }[action] || action) }
function statusType(row) { return statusLabel(row) === '生效中' ? 'success' : 'info' }
function isExpired(row) { return row.expires_at && new Date(row.expires_at) <= new Date() }
function formatTime(value, fallback = '-') { return value ? new Date(value).toLocaleString() : fallback }
function tableRowClassName({ row }) {
  if (String(row.id) === String(route.query.focus || '')) return 'notification-focus'
  return row.isCustomerGroup ? 'customer-group-row' : 'subscription-child-row'
}
onMounted(load)
</script>

<style scoped>
.page-toolbar { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 18px; }
.toolbar-row { display: flex; gap: 12px; margin-bottom: 16px; }
.view-switcher { display: flex; align-items: center; gap: 14px; margin-bottom: 14px; }
.view-switcher-hint, .line-count { color: var(--app-text-muted); font-size: 12px; }
.line-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.region-input { width: 140px; }
.line-count { margin-left: auto; }
.line-pagination { display: flex; justify-content: flex-end; padding: 14px 18px; border-top: 1px solid var(--app-border); }
.search-input { max-width: 360px; }
.status-select { width: 140px; }
.lookup-panel, .lookup-result { display: flex; align-items: center; gap: 14px; margin-bottom: 16px; padding: 14px 16px; }
.lookup-copy { display: flex; flex-direction: column; gap: 4px; min-width: 210px; }
.lookup-copy strong, .lookup-result-title strong { color: var(--app-text); }
.lookup-copy span, .lookup-result-meta, .lookup-result-note { color: var(--app-text-muted); font-size: 12px; }
.lookup-input { flex: 1; }
.lookup-result { align-items: flex-start; justify-content: space-between; border-color: color-mix(in srgb, var(--app-primary) 28%, var(--app-border)); }
.lookup-result-main { min-width: 0; }
.lookup-result-title, .lookup-result-meta { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.lookup-result-meta { margin-top: 8px; color: var(--app-text-secondary); }
.lookup-result-note { margin-top: 8px; color: var(--app-text-secondary); white-space: pre-wrap; overflow-wrap: anywhere; }
.lookup-result-actions { display: flex; align-items: center; flex-wrap: wrap; white-space: nowrap; }
.token-mode-group { display: flex; flex-wrap: wrap; max-width: 100%; }
.form-hint { margin-top: -8px; color: var(--app-text-muted); font-size: 12px; line-height: 1.5; }
.history-alert { margin-bottom: 14px; }
.subscription-table-card { padding: 0; overflow: hidden; }
.group-hint { display: flex; align-items: center; gap: 8px; padding: 13px 18px; border-bottom: 1px solid var(--app-border); color: var(--app-text-secondary); background: #fbfcfe; font-size: 12px; }
.group-hint > .el-icon { color: var(--app-primary); }
.group-hint strong { margin-left: auto; color: var(--app-text); font-size: 12px; font-weight: 600; }
.customer-group-cell, .subscription-cell { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.customer-group-cell strong { color: var(--app-text); font-size: 14px; }
.customer-group-cell small, .subscription-cell small { color: var(--app-text-muted); font-size: 11px; }
.group-summary, .group-label { color: var(--app-text-secondary); font-size: 12px; }
.group-total { color: var(--app-primary); font-weight: 700; font-variant-numeric: tabular-nums; }
.group-action-hint { color: var(--app-text-muted); font-size: 11px; }
.qr-body { display: flex; flex-direction: column; align-items: center; gap: 14px; }
.qr-image { width: 240px; height: 240px; border: 1px solid var(--app-border); border-radius: var(--app-radius-sm); }
.qr-url { max-width: 100%; color: var(--app-text-secondary); font-size: 13px; word-break: break-all; text-align: center; }
.form-row { display: flex; gap: 16px; }
.form-row > .el-form-item { flex: 1; }
small { display: block; margin-top: 3px; color: var(--app-text-muted); font-size: 12px; }
@media (max-width: 760px) { .page-toolbar, .toolbar-row, .line-toolbar, .form-row, .lookup-panel, .lookup-result, .view-switcher { flex-direction: column; align-items: stretch; } .search-input, .region-input, .status-select, .lookup-input { width: 100%; max-width: none; } .group-hint { align-items: flex-start; flex-wrap: wrap; } .group-hint strong { width: 100%; margin-left: 24px; } .lookup-result-actions { justify-content: flex-start; } .token-mode-group { display: grid; grid-template-columns: 1fr; } .token-mode-group .el-radio-button, .token-mode-group .el-radio-button :deep(.el-radio-button__inner) { width: 100%; } .line-count { margin-left: 0; } }
</style>
