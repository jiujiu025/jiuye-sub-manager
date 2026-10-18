<template>
  <div class="page">
    <div class="page-header page-toolbar">
      <div>
        <h2 class="page-title">客户管理</h2>
        <p class="page-subtitle">登记客户资料，客户订阅与套餐方案分开管理。</p>
      </div>
      <div class="page-actions">
        <div class="page-header-mark"><el-icon><UserFilled /></el-icon><span>CRM</span></div>
        <el-button type="primary" @click="openCreate"><el-icon><Plus /></el-icon>新增客户</el-button>
      </div>
    </div>

    <div class="toolbar-row">
      <el-input v-model="keyword" clearable placeholder="搜索客户、地区或联系方式" class="search-input">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-select v-model="statusFilter" clearable placeholder="全部状态" class="status-select">
        <el-option label="启用" value="active" />
        <el-option label="停用" value="inactive" />
      </el-select>
    </div>

    <div v-loading="statsLoading" class="stats-strip">
      <div class="stat-cell"><span>客户数</span><strong>{{ stats.customer_count }}</strong></div>
      <div class="stat-cell"><span>有效订阅</span><strong>{{ stats.active_subscription_count }}</strong></div>
      <div class="stat-cell warning"><span>3 天内到期</span><strong>{{ stats.expiring_subscription_count }}</strong></div>
      <div class="stat-cell"><span>销售额</span><strong>¥{{ stats.sales_total }}</strong></div>
      <div class="stat-regions"><span>地区</span><el-tag v-for="region in stats.regions" :key="region.region" size="small">{{ region.region }} {{ region.customer_count }}</el-tag><em v-if="!stats.regions.length">暂无</em></div>
    </div>

    <div v-loading="loading" class="surface-card">
      <el-table :data="filteredCustomers" row-key="id" :row-class-name="tableRowClassName" empty-text="暂无客户资料">
        <el-table-column prop="name" label="客户" min-width="180" />
        <el-table-column prop="region" label="地区" width="120"><template #default="{ row }">{{ row.region || '-' }}</template></el-table-column>
         <el-table-column prop="contact" label="联系方式" min-width="180"><template #default="{ row }">{{ row.contact || '-' }}</template></el-table-column>
         <el-table-column label="备注" min-width="180" show-overflow-tooltip><template #default="{ row }">{{ row.note || '-' }}</template></el-table-column>
        <el-table-column prop="subscription_count" label="订阅数" width="100" />
        <el-table-column label="负责经理" width="130"><template #default="{ row }">{{ row.manager_username || '未分配' }}</template></el-table-column>
        <el-table-column label="登录账号" min-width="150"><template #default="{ row }"><span v-if="row.account_username">{{ row.account_username }}<el-tag v-if="row.account_is_active === false" size="small" type="warning">已停用</el-tag></span><span v-else class="muted">未绑定</span></template></el-table-column>
        <el-table-column label="首次购买" width="170"><template #default="{ row }">{{ formatTime(row.first_purchase_at) }}</template></el-table-column>
        <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? '启用' : '停用' }}</el-tag></template></el-table-column>
         <el-table-column label="操作" width="220" fixed="right"><template #default="{ row }"><el-button link type="primary" @click="openNote(row)">备注</el-button><el-button link type="primary" @click="openEdit(row)">编辑</el-button><el-button v-if="isAdmin" link type="primary" @click="openAccount(row)">账号</el-button></template></el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑客户' : '新增客户'" width="500px" append-to-body>
      <el-form label-width="96px">
        <el-form-item label="客户名称" required><el-input v-model="form.name" maxlength="128" /></el-form-item>
        <el-form-item v-if="isAdmin" label="负责经理"><el-select v-model="form.manager_user_id" clearable filterable placeholder="暂不分配" style="width: 100%"><el-option v-for="manager in managers" :key="manager.id" :label="manager.username" :value="manager.id" /></el-select></el-form-item>
        <el-form-item label="地区"><el-input v-model="form.region" maxlength="64" placeholder="例如：香港、日本" /></el-form-item>
        <el-form-item label="联系方式"><el-input v-model="form.contact" maxlength="128" /></el-form-item>
        <el-form-item label="首次购买"><el-date-picker v-model="form.first_purchase_at" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss" placeholder="可留空" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="form.note" type="textarea" :rows="3" /></el-form-item>
        <el-form-item v-if="editing" label="状态"><el-switch v-model="form.is_active" active-text="启用" inactive-text="停用" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="dialogVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存客户</el-button></template>
    </el-dialog>

    <el-dialog v-model="noteDialogVisible" :title="`客户备注 · ${noteCustomer?.name || ''}`" width="460px" append-to-body>
      <el-input v-model="noteText" type="textarea" :rows="5" maxlength="2000" show-word-limit placeholder="记录客户偏好、跟进事项或交付说明" />
      <template #footer><el-button @click="noteDialogVisible = false">取消</el-button><el-button type="primary" :loading="noteSaving" @click="saveNote">保存备注</el-button></template>
    </el-dialog>

    <el-dialog v-model="accountDialogVisible" :title="`客户登录账号 · ${accountCustomer?.name || ''}`" width="500px" append-to-body>
      <template v-if="accountCustomer?.account_user_id">
        <el-alert title="该客户已经绑定普通用户账号" type="success" :closable="false" show-icon />
        <div class="account-current"><span>登录名</span><strong>{{ accountCustomer.account_username }}</strong></div>
        <p class="account-hint">解除绑定只会断开客户关系，不会删除用户账号。</p>
      </template>
      <el-form v-else label-width="96px">
        <el-form-item label="绑定已有账号"><el-select v-model="accountForm.user_id" clearable filterable placeholder="选择普通用户" style="width: 100%"><el-option v-for="user in ordinaryUsers" :key="user.id" :label="user.username" :value="user.id" /></el-select></el-form-item>
        <div class="account-divider"><span>或创建新账号</span></div>
        <el-form-item label="新用户名"><el-input v-model="accountForm.username" autocomplete="off" /></el-form-item>
        <el-form-item label="初始密码"><el-input v-model="accountForm.password" type="password" show-password autocomplete="new-password" /></el-form-item>
        <p class="account-hint">账号创建后请将用户名和初始密码安全交付给客户。密码不会在系统中明文保存。</p>
      </el-form>
      <template #footer>
        <el-button @click="accountDialogVisible = false">取消</el-button>
        <el-button v-if="accountCustomer?.account_user_id" type="warning" :loading="accountSaving" @click="unbindAccount">解除绑定</el-button>
        <el-button v-else type="primary" :loading="accountSaving" @click="saveAccount">保存账号绑定</el-button>
      </template>
    </el-dialog>

  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { bindCustomerAccount, createCustomer, createCustomerAccount, getManagerStats, listCustomers, listUsers, unbindCustomerAccount, updateCustomer } from '../api'
import { useAuthStore } from '../stores/auth'

const customers = ref([])
const loading = ref(false)
const saving = ref(false)
const keyword = ref('')
const statusFilter = ref('')
const dialogVisible = ref(false)
const editing = ref(null)
const form = reactive({ name: '', manager_user_id: null, region: '', contact: '', first_purchase_at: null, note: '', is_active: true })
const managers = ref([])
const statsLoading = ref(false)
const stats = ref({ customer_count: 0, active_subscription_count: 0, expiring_subscription_count: 0, sales_total: '0.00', regions: [] })
const authStore = useAuthStore()
const isAdmin = computed(() => authStore.role === 'admin')
const accountDialogVisible = ref(false)
const accountSaving = ref(false)
const accountCustomer = ref(null)
const ordinaryUsers = ref([])
const accountForm = reactive({ user_id: null, username: '', password: '' })
const noteDialogVisible = ref(false)
const noteSaving = ref(false)
const noteCustomer = ref(null)
const noteText = ref('')
const route = useRoute()

const filteredCustomers = computed(() => {
  const query = keyword.value.trim().toLowerCase()
  return customers.value.filter((customer) => {
    if (statusFilter.value === 'active' && !customer.is_active) return false
    if (statusFilter.value === 'inactive' && customer.is_active) return false
    return !query || `${customer.name} ${customer.region || ''} ${customer.contact || ''} ${customer.note || ''}`.toLowerCase().includes(query)
  })
})

function resetForm() { Object.assign(form, { name: '', manager_user_id: null, region: '', contact: '', first_purchase_at: null, note: '', is_active: true }) }
function openCreate() { editing.value = null; resetForm(); dialogVisible.value = true }
function openEdit(row) {
  editing.value = row
  Object.assign(form, { name: row.name, manager_user_id: row.manager_user_id, region: row.region || '', contact: row.contact || '', first_purchase_at: row.first_purchase_at ? new Date(row.first_purchase_at) : null, note: row.note || '', is_active: row.is_active })
  dialogVisible.value = true
}
function openNote(row) {
  noteCustomer.value = row
  noteText.value = row.note || ''
  noteDialogVisible.value = true
}
async function saveNote() {
  if (!noteCustomer.value) return
  noteSaving.value = true
  try {
    const { data } = await updateCustomer(noteCustomer.value.id, { note: noteText.value.trim() || null })
    const index = customers.value.findIndex((item) => item.id === data.id)
    if (index !== -1) customers.value[index] = data
    noteDialogVisible.value = false
    ElMessage.success('客户备注已保存')
  } finally {
    noteSaving.value = false
  }
}
async function load() {
  loading.value = true
  try {
    const { data } = await listCustomers()
    customers.value = data
    await nextTick()
    document.querySelector('.notification-focus')?.scrollIntoView({ block: 'center' })
  } finally { loading.value = false }
}
function tableRowClassName({ row }) {
  return String(row.id) === String(route.query.focus || '') ? 'notification-focus' : ''
}
async function loadManagers() {
  if (!isAdmin.value) return
  const { data } = await listUsers({ role: 'manager' })
  managers.value = data.filter((item) => item.is_active)
}
async function loadOrdinaryUsers() {
  if (!isAdmin.value) return
  const { data } = await listUsers({ role: 'user' })
  ordinaryUsers.value = data.filter((item) => item.is_active)
}
function openAccount(row) {
  accountCustomer.value = row
  Object.assign(accountForm, { user_id: null, username: '', password: '' })
  loadOrdinaryUsers()
  accountDialogVisible.value = true
}
async function saveAccount() {
  if (!accountCustomer.value) return
  if (!accountForm.user_id && (!accountForm.username.trim() || accountForm.password.length < 8)) {
    ElMessage.warning('请选择已有普通用户，或填写至少 8 位的新账号密码')
    return
  }
  accountSaving.value = true
  try {
    if (accountForm.user_id) await bindCustomerAccount(accountCustomer.value.id, { user_id: accountForm.user_id })
    else await createCustomerAccount(accountCustomer.value.id, { username: accountForm.username.trim(), password: accountForm.password })
    ElMessage.success('客户登录账号已绑定')
    accountDialogVisible.value = false
    await load()
  } finally { accountSaving.value = false }
}
async function unbindAccount() {
  if (!accountCustomer.value) return
  accountSaving.value = true
  try { await unbindCustomerAccount(accountCustomer.value.id); ElMessage.success('账号绑定已解除'); accountDialogVisible.value = false; await load() } finally { accountSaving.value = false }
}
async function loadStats() {
  statsLoading.value = true
  try { const { data } = await getManagerStats(); stats.value = data } finally { statsLoading.value = false }
}
async function save() {
  if (!form.name.trim()) { ElMessage.warning('请输入客户名称'); return }
  saving.value = true
  try {
    const payload = { ...form, name: form.name.trim() }
    if (form.first_purchase_at instanceof Date) payload.first_purchase_at = form.first_purchase_at.toISOString()
    if (editing.value) await updateCustomer(editing.value.id, payload)
    else await createCustomer(payload)
    dialogVisible.value = false
    ElMessage.success(editing.value ? '客户资料已更新' : '客户已创建')
    await load()
  } finally { saving.value = false }
}
function formatTime(value, fallback = '-') { return value ? new Date(value).toLocaleString() : fallback }
onMounted(() => { load(); loadManagers(); loadStats() })
</script>

<style scoped>
.page-toolbar { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 18px; }
.toolbar-row { display: flex; gap: 12px; margin-bottom: 16px; }
.search-input { max-width: 360px; }
.status-select { width: 140px; }
.stats-strip { display: flex; align-items: stretch; gap: 0; margin-bottom: 16px; padding: 0; border: 1px solid var(--app-border); border-radius: var(--app-radius-md); background: var(--app-card); overflow: hidden; }
.stat-cell, .stat-regions { min-width: 130px; padding: 14px 18px; border-right: 1px solid var(--app-border); }
.stat-cell span, .stat-regions > span { display: block; color: var(--app-text-muted); font-size: 12px; }
.stat-cell strong { display: block; margin-top: 5px; color: var(--app-text); font-size: 20px; font-variant-numeric: tabular-nums; }
.stat-cell.warning strong { color: var(--app-warning); }
.stat-regions { display: flex; align-items: center; gap: 6px; flex: 1; flex-wrap: wrap; border-right: 0; }
.stat-regions > span { width: 100%; }
.stat-regions em { color: var(--app-text-muted); font-size: 12px; font-style: normal; }
@media (max-width: 640px) { .page-toolbar, .toolbar-row { flex-direction: column; } .search-input, .status-select { width: 100%; max-width: none; } }
.muted { color: var(--app-text-muted); }
.account-current { display: flex; justify-content: space-between; margin: 20px 0 8px; padding: 14px; background: var(--app-card-soft); border-radius: var(--app-radius-sm); }
.account-hint { color: var(--app-text-secondary); font-size: 13px; line-height: 1.6; }
.account-divider { margin: 18px 0; border-top: 1px solid var(--app-border); text-align: center; color: var(--app-text-muted); font-size: 12px; }
.account-divider span { position: relative; top: -10px; padding: 0 10px; background: var(--app-card); }
</style>
