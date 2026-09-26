<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">套餐管理</h2>
        <p class="page-subtitle">管理订阅来源、过滤规则和生成的订阅。</p>
      </div>
      <div class="page-actions">
        <div class="page-header-mark"><el-icon><Tickets /></el-icon><span>SUBSCRIPTIONS</span></div>
        <el-button @click="load">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
        <el-button type="primary" @click="openCreate">
          <el-icon><Plus /></el-icon>
          新建套餐
        </el-button>
      </div>
    </div>

    <div class="filter-bar">
      <el-input
        v-model="searchKeyword"
        placeholder="搜索套餐名称或订阅显示名称"
        clearable
        style="width: 260px"
      />
      <el-select
        v-model="statusFilter"
        placeholder="状态：全部"
        clearable
        style="width: 150px"
      >
        <el-option label="开启" value="enabled" />
        <el-option label="禁用" value="disabled" />
      </el-select>
      <div class="spacer" />
    </div>

    <div
      v-loading="loading"
      class="package-grid"
    >
      <div
        v-for="(pkg, index) in filteredPackages"
        :key="pkg.id"
        class="package-card"
      >
        <div class="package-head">
          <div>
            <div class="package-name">
              <span class="package-index">#{{ index + 1 }}</span>
              {{ pkg.name }}
              <el-tag
                :type="pkg.enabled ? 'success' : 'info'"
                effect="light"
                round
                size="small"
              >
                {{ pkg.enabled ? '开启' : '禁用' }}
              </el-tag>
              <el-tag
                :type="isExpired(pkg) ? 'danger' : 'warning'"
                effect="light"
                round
                size="small"
              >
                {{ expirationLabel(pkg) }}
              </el-tag>
            </div>
          </div>
        </div>

        <div class="package-meta">
          <div class="meta-block">
            <div class="meta-label">订阅显示名称</div>
            <div class="meta-value">{{ pkg.subscription_name }}</div>
          </div>
          <div class="meta-block">
            <div class="meta-label">Token 名称</div>
            <div class="meta-value">{{ pkg.token_name || '未命名' }}</div>
          </div>
          <div class="meta-block">
            <div class="meta-label">订阅源</div>
            <div class="meta-value">{{ summaryOf(pkg).sourceCount }} 个</div>
            <div v-if="missingSourcesOf(pkg).length" class="source-warning">
              已删除：{{ missingSourcesOf(pkg).join('、') }}
            </div>
          </div>
          <div class="meta-block">
            <div class="meta-label">当前可用节点</div>
            <div
              v-if="pkg.token_revoked_at"
              class="meta-value no-nodes"
            >
              Token 已吊销
            </div>
            <div
              v-else-if="(packageNodeCounts[pkg.id] ?? 0) > 0"
              class="meta-value"
            >
              {{ packageNodeCounts[pkg.id] }} 个可用节点
            </div>
            <div v-else class="meta-value no-nodes">
              0 个可用节点 / 当前无匹配节点
            </div>
          </div>
          <div class="meta-block">
            <div class="meta-label">包含关键词</div>
            <div class="meta-value">{{ summaryOf(pkg).includeText || '全部' }}</div>
          </div>
          <div class="meta-block">
            <div class="meta-label">排除关键词</div>
            <div class="meta-value">{{ summaryOf(pkg).excludeText || '无' }}</div>
          </div>
          <div class="meta-block">
            <div class="meta-label">重命名规则</div>
            <div class="meta-value">{{ summaryOf(pkg).renameText || '无' }}</div>
          </div>
          <div class="meta-block">
            <div class="meta-label">排序规则</div>
            <div class="meta-value">{{ summaryOf(pkg).sortText || '默认' }}</div>
          </div>
        </div>

        <div class="package-updated">
          <span class="meta-label">更新时间</span>
          <span class="updated-value">{{ formatTime(pkg.updated_at) }}</span>
        </div>

        <div class="package-actions">
          <el-button size="default" type="primary" plain @click="openEdit(pkg)">
            编辑
          </el-button>
          <el-button
            size="default"
            plain
            @click="copyUrl(pkg)"
          >
            复制订阅
          </el-button>
          <el-button
            size="default"
            plain
            @click="showQr(pkg)"
          >
            二维码
          </el-button>
          <el-dropdown trigger="click" @command="(cmd) => handleMore(cmd, pkg)">
            <el-button size="default" plain>
              更多
              <el-icon><ArrowDown /></el-icon>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="preview">预览节点</el-dropdown-item>
                <el-dropdown-item command="regenerate">刷新 Token</el-dropdown-item>
                <el-dropdown-item command="toggle">
                  {{ pkg.enabled ? '禁用套餐' : '启用套餐' }}
                </el-dropdown-item>
                <el-dropdown-item command="delete" divided>删除套餐</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>

      <div v-if="!loading && !filteredPackages.length" class="empty-state package-empty">
        <p class="empty-state-title">暂无套餐</p>
        <p class="empty-state-desc">创建一个套餐后，可以组合订阅来源并生成独立订阅。</p>
        <el-button type="primary" @click="openCreate">+ 新建套餐</el-button>
      </div>
    </div>

    <el-dialog
      v-model="dialogVisible"
      :title="editing ? '编辑套餐' : '新建套餐'"
      width="720px"
      append-to-body
    >
      <p class="dialog-subtitle">通过规则组合订阅源，生成独立的 Clash/Mihomo 订阅。</p>
      <el-form label-position="top">
        <div class="form-row">
          <el-form-item label="套餐名称" required style="flex: 1">
            <el-input v-model="form.name" placeholder="请输入套餐名称" />
          </el-form-item>
        <el-form-item label="订阅显示名称" style="flex: 1">
          <el-input v-model="form.subscription_name" placeholder="留空默认使用套餐名称" />
        </el-form-item>
        <el-form-item label="Token 名称">
          <el-input v-model="form.token_name" placeholder="例如：手机主订阅、电脑备用订阅" />
          <div class="form-hint">仅用于后台识别，不会改变订阅 Token 本身。</div>
        </el-form-item>
        </div>
        <el-form-item label="说明">
          <el-input v-model="form.description" placeholder="选填" />
        </el-form-item>
        <el-form-item label="归属用户">
          <el-select v-model="form.owner_user_id" clearable placeholder="不指定则仅管理员管理" style="width: 100%">
            <el-option
              v-for="user in userOptions"
              :key="user.id"
              :label="user.username"
              :value="user.id"
            />
          </el-select>
          <div class="form-hint">普通用户登录后只能看到分配给自己的套餐。</div>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
        <el-form-item label="到期时间">
          <el-date-picker
            v-model="form.expires_at"
            type="datetime"
            format="YYYY-MM-DD HH:mm:ss"
            value-format="YYYY-MM-DDTHH:mm:ss"
            placeholder="留空表示永不过期"
            clearable
            style="width: 100%"
          />
          <div class="form-hint">到期后订阅只返回不可连接的续费提示线路，旧缓存不会继续生效。</div>
        </el-form-item>

        <el-divider content-position="left">筛选规则</el-divider>
        <el-form-item label="节点来源">
          <div class="node-source-box">
            <div class="source-group">
              <div class="source-group-title">订阅源</div>
              <div class="source-check-list">
                <el-checkbox-group v-model="form.rules.source_filter">
                  <el-checkbox
                    v-for="source in sourceOptions"
                    :key="source"
                    :value="source"
                    class="source-check"
                  >
                    {{ source }}
                  </el-checkbox>
                </el-checkbox-group>
                <div v-if="!sourceOptions.length" class="form-hint">暂无订阅源</div>
              </div>
              <div v-if="missingFormSources.length" class="source-warning">
                当前套餐仍保留已删除来源：{{ missingFormSources.join('、') }}。这些来源不会扩大为全部来源，清除后才会从筛选规则中移除。
              </div>
              <div class="source-actions">
                <el-button size="small" @click="selectAllSources">全选</el-button>
                <el-button size="small" @click="form.rules.source_filter = []">清空</el-button>
              </div>
            </div>
            <div class="source-group">
              <div class="source-group-title">自有节点</div>
              <el-input
                v-model="selfNodeSearch"
                placeholder="搜索节点名称/服务器/国家"
                clearable
                style="width: 240px"
              />
              <div class="self-node-list">
                <el-checkbox-group v-model="form.rules.node_ids">
                  <el-checkbox
                    v-for="node in filteredSelfNodes"
                    :key="node.id"
                    :value="node.id"
                    class="self-node-check"
                  >
                    <span class="node-option-name">{{ node.name }}</span>
                    <span class="node-option-meta">
                      {{ node.type }} · {{ node.country || '-' }} · {{ node.server }}
                    </span>
                  </el-checkbox>
                </el-checkbox-group>
                <div v-if="!filteredSelfNodes.length" class="form-hint">暂无匹配的自有节点</div>
              </div>
              <div class="source-actions">
                <el-button size="small" @click="selectAllSelfNodes">全选</el-button>
                <el-button size="small" @click="form.rules.node_ids = []">清空</el-button>
              </div>
            </div>
          </div>
        </el-form-item>
        <el-form-item label="地区">
          <el-select v-model="form.rules.country_filter" multiple clearable style="width: 100%">
            <el-option v-for="country in countryOptions" :key="country" :label="country" :value="country" />
          </el-select>
          <div class="form-hint">按节点识别出的国家/地区过滤，例如：香港、台湾、美国。</div>
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="form.rules.type_filter" multiple clearable style="width: 100%">
            <el-option label="VLESS" value="vless" />
            <el-option label="VMess" value="vmess" />
            <el-option label="Shadowsocks" value="shadowsocks" />
            <el-option label="Trojan" value="trojan" />
            <el-option label="AnyTLS" value="anytls" />
          </el-select>
        </el-form-item>

        <el-form-item label="包含关键词">
          <div class="keyword-box">
            <div class="keyword-add">
              <el-input
                v-model="includeKeywordInput"
                placeholder="输入关键词后点击添加，如：美国"
                style="width: 220px"
                @keyup.enter="addKeywordFrom('include_keywords')"
              />
              <el-button @click="addKeywordFrom('include_keywords')">
                添加
              </el-button>
            </div>
            <div v-if="form.rules.include_keywords.length" class="keyword-tags">
              <el-tag
                v-for="(value, index) in form.rules.include_keywords"
                :key="value"
                closable
                @close="removeKeyword('include_keywords', index)"
              >
                {{ value }}
              </el-tag>
            </div>
            <div v-else class="form-hint">尚未添加关键词</div>
          </div>
          <div class="form-hint">
            按节点名称过滤，只保留包含这些关键词的节点；与地区/类型同时设置时为 AND 关系，节点必须同时满足。
          </div>
        </el-form-item>
        <el-form-item label="排除关键词">
          <div class="keyword-box">
            <div class="keyword-add">
              <el-input
                v-model="excludeKeywordInput"
                placeholder="输入关键词后点击添加，如：香港"
                style="width: 220px"
                @keyup.enter="addKeywordFrom('exclude_keywords')"
              />
              <el-button @click="addKeywordFrom('exclude_keywords')">
                添加
              </el-button>
            </div>
            <div v-if="form.rules.exclude_keywords.length" class="keyword-tags">
              <el-tag
                v-for="(value, index) in form.rules.exclude_keywords"
                :key="value"
                closable
                @close="removeKeyword('exclude_keywords', index)"
              >
                {{ value }}
              </el-tag>
            </div>
            <div v-else class="form-hint">尚未添加关键词</div>
          </div>
          <div class="form-hint">
            按节点名称过滤，删除包含这些关键词的节点；与包含关键词同时设置时，先包含再排除。
          </div>
        </el-form-item>

        <el-divider content-position="left">重命名规则</el-divider>
        <el-form-item label="名称替换">
          <div class="rename-list">
            <div v-for="(item, index) in renameForm.replacements" :key="index" class="rename-row">
              <el-input v-model="item.from" placeholder="原名称，如：美国" style="width: 180px" />
              <span class="arrow">→</span>
              <el-input v-model="item.to" placeholder="替换为，如：US" style="width: 180px" />
              <el-button size="small" type="danger" plain @click="removeRename(index)">删除</el-button>
            </div>
            <el-button size="small" @click="addRename">+ 添加规则</el-button>
          </div>
          <div class="rule-options">
            <el-checkbox v-model="renameForm.country_abbr">国家缩写（香港→HK）</el-checkbox>
            <el-checkbox v-model="renameForm.numbered">自动编号（HK-01）</el-checkbox>
          </div>
          <div class="rule-extra">
            <el-input v-model="renameForm.prefix" placeholder="前缀，如：HK-" style="width: 170px" />
            <el-input v-model="renameForm.suffix" placeholder="后缀，如：-专线" style="width: 170px" />
          </div>
        </el-form-item>

        <el-divider content-position="left">排序规则</el-divider>
        <el-form-item label="排序字段">
          <el-select v-model="sortForm.field" style="width: 200px">
            <el-option label="国家" value="country" />
            <el-option label="来源" value="source" />
            <el-option label="类型" value="type" />
            <el-option label="名称" value="name" />
          </el-select>
        </el-form-item>
        <el-form-item label="优先顺序">
          <div class="priority-add">
            <el-input
              v-model="priorityInput"
              placeholder="输入后回车添加，如：日本"
              style="width: 180px"
              @keyup.enter="addPriority"
            />
            <el-button @click="addPriority">添加</el-button>
          </div>
          <div v-if="sortForm.order.length" class="priority-list">
            <div v-for="(value, index) in sortForm.order" :key="value" class="priority-row">
              <span class="priority-index">{{ index + 1 }}</span>
              <span class="priority-value">{{ value }}</span>
              <el-button
                size="small"
                text
                :disabled="index === 0"
                @click="movePriority(index, -1)"
              >
                ↑
              </el-button>
              <el-button
                size="small"
                text
                :disabled="index === sortForm.order.length - 1"
                @click="movePriority(index, 1)"
              >
                ↓
              </el-button>
              <el-button size="small" text type="danger" @click="removePriority(index)">×</el-button>
            </div>
          </div>
          <div v-else class="form-hint">未设置优先顺序，按字段默认排序。</div>
        </el-form-item>
        <el-form-item label="排序方向">
          <el-radio-group v-model="sortForm.direction">
            <el-radio value="custom">自定义顺序</el-radio>
            <el-radio value="asc">正序</el-radio>
            <el-radio value="desc">倒序</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">
          保存套餐
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="previewVisible" title="套餐节点预览" width="760px" append-to-body>
      <el-table :data="previewRows" max-height="480">
        <el-table-column prop="name" label="名称" min-width="140" />
        <el-table-column prop="type" label="类型" width="100" />
        <el-table-column prop="country" label="地区" width="90" />
        <el-table-column prop="server" label="服务器" min-width="150" show-overflow-tooltip />
        <el-table-column prop="port" label="端口" width="80" />
        <el-table-column prop="source_name" label="来源" width="110" />
      </el-table>
    </el-dialog>

    <el-dialog v-model="qrVisible" title="订阅二维码" width="380px" append-to-body>
      <div class="qr-body">
        <img v-if="qrDataUrl" :src="qrDataUrl" alt="订阅二维码" class="qr-image" />
        <div class="qr-url">{{ qrUrl }}</div>
        <el-button type="primary" plain @click="copyQrUrl">复制订阅地址</el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import QRCode from 'qrcode'
import {
  createPackage,
  deletePackage,
  getPackageSubscriptionUrl,
  getPackage,
  listPackages,
  listNodes,
  listSources,
  previewPackage,
  listUsers,
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
const sourcesLoaded = ref(false)
const userOptions = ref([])
const packageNodeCounts = ref({})
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const previewVisible = ref(false)
const previewRows = ref([])
const editing = ref(null)
const priorityInput = ref('')
const includeKeywordInput = ref('')
const excludeKeywordInput = ref('')
const selfNodes = ref([])
const selfNodeSearch = ref('')
const searchKeyword = ref('')
const statusFilter = ref('')
const qrVisible = ref(false)
const qrDataUrl = ref('')
const qrUrl = ref('')
const renameForm = reactive({
  prefix: '',
  suffix: '',
  replacements: [{ from: '', to: '' }],
  country_abbr: false,
  numbered: false
})
const sortForm = reactive({
  field: 'country',
  order: [],
  direction: 'custom'
})
const extraRenameRules = ref([])
const extraSortRules = ref([])
const form = reactive({
  name: '',
  subscription_name: '',
  token_name: '',
  description: '',
  enabled: true,
  expires_at: null,
  owner_user_id: null,
  rules: {
    source_filter: [],
    node_ids: [],
    country_filter: [],
    type_filter: [],
    include_keywords: [],
    exclude_keywords: []
  }
})

const filteredPackages = computed(() => {
  const keyword = searchKeyword.value.trim().toLowerCase()
  return packages.value.filter((pkg) => {
    if (statusFilter.value === 'enabled' && !pkg.enabled) return false
    if (statusFilter.value === 'disabled' && pkg.enabled) return false
    if (keyword) {
      const name = `${pkg.name} ${pkg.subscription_name || ''}`.toLowerCase()
      if (!name.includes(keyword)) return false
    }
    return true
  })
})

const filteredSelfNodes = computed(() => {
  const keyword = selfNodeSearch.value.trim().toLowerCase()
  if (!keyword) {
    return selfNodes.value
  }
  return selfNodes.value.filter((node) => {
    const text = `${node.name} ${node.server} ${node.country || ''}`.toLowerCase()
    return text.includes(keyword)
  })
})

const missingFormSources = computed(() => {
  if (!sourcesLoaded.value) return []
  const availableSources = new Set(sourceOptions.value)
  return form.rules.source_filter.filter((source) => !availableSources.has(source))
})

function resetRuleForms() {
  Object.assign(renameForm, {
    prefix: '',
    suffix: '',
    replacements: [{ from: '', to: '' }],
    country_abbr: false,
    numbered: false
  })
  Object.assign(sortForm, {
    field: 'country',
    order: [],
    direction: 'custom'
  })
  priorityInput.value = ''
  extraRenameRules.value = []
  extraSortRules.value = []
}

function addRename() {
  renameForm.replacements.push({ from: '', to: '' })
}

function removeRename(index) {
  renameForm.replacements.splice(index, 1)
  if (!renameForm.replacements.length) {
    renameForm.replacements.push({ from: '', to: '' })
  }
}

function addKeywordFrom(key) {
  const inputRef =
    key === 'include_keywords' ? includeKeywordInput : excludeKeywordInput
  const value = inputRef.value.trim()
  if (!value) {
    return
  }
  const list = form.rules[key]
  if (!list.includes(value)) {
    list.push(value)
  }
  inputRef.value = ''
}

function removeKeyword(key, index) {
  form.rules[key].splice(index, 1)
}

function addPriority() {
  const value = priorityInput.value.trim()
  if (value && !sortForm.order.includes(value)) {
    sortForm.order.push(value)
  }
  priorityInput.value = ''
}

function removePriority(index) {
  sortForm.order.splice(index, 1)
}

function movePriority(index, direction) {
  const target = index + direction
  if (target < 0 || target >= sortForm.order.length) {
    return
  }
  const [item] = sortForm.order.splice(index, 1)
  sortForm.order.splice(target, 0, item)
}

function summaryOf(pkg) {
  const rules = pkg.rules || {}
  const replacements = (rules.rename_rules || []).flatMap((rule) => rule.replacements || [])
  return {
    sourceCount: (rules.source_filter || []).length,
    includeText: (rules.include_keywords || []).join(' / '),
    excludeText: (rules.exclude_keywords || []).join(' / '),
    renameText: replacements.map((item) => `${item.from}→${item.to}`).join(' / '),
    sortText: (rules.sort_rules || [])
      .map((rule) => `${rule.field}${rule.order && rule.order.length ? `：${rule.order.join('/')}` : ''}`)
      .join(' / ')
  }
}

function missingSourcesOf(pkg) {
  if (!sourcesLoaded.value) return []
  const availableSources = new Set(sourceOptions.value)
  return (pkg.rules?.source_filter || []).filter((source) => !availableSources.has(source))
}

async function load() {
  loading.value = true
  try {
    const { data } = await listPackages()
    packages.value = data
    await refreshNodeCounts()
  } finally {
    loading.value = false
  }
}

async function refreshNodeCounts() {
  const entries = await Promise.all(
    packages.value.map(async (pkg) => {
      try {
        const { data } = await previewPackage(pkg.id)
        return [pkg.id, data.length]
      } catch {
        return [pkg.id, 0]
      }
    })
  )
  packageNodeCounts.value = Object.fromEntries(entries)
}

async function loadSources() {
  const { data } = await listSources()
  sourceOptions.value = data.items.map((item) => item.name)
  sourcesLoaded.value = true
}

async function loadUsers() {
  const { data } = await listUsers()
  userOptions.value = data.filter((user) => user.role === 'user' && user.is_active)
}

async function loadSelfNodes() {
  const { data } = await listNodes({
    source_name: '自有节点',
    enabled: true,
    page_size: 100
  })
  selfNodes.value = data.items
}

function selectAllSources() {
  form.rules.source_filter = [...sourceOptions.value]
}

function selectAllSelfNodes() {
  const ids = new Set(form.rules.node_ids)
  filteredSelfNodes.value.forEach((node) => ids.add(node.id))
  form.rules.node_ids = [...ids]
}

function resetForm() {
  Object.assign(form, {
    name: '',
    subscription_name: '',
    token_name: '',
    description: '',
    enabled: true,
    expires_at: null,
    owner_user_id: null,
    rules: {
      source_filter: [],
      node_ids: [],
      country_filter: [],
      type_filter: [],
      include_keywords: [],
      exclude_keywords: []
    }
  })
  includeKeywordInput.value = ''
  excludeKeywordInput.value = ''
  resetRuleForms()
}

function padNumber(value) {
  return String(value).padStart(2, '0')
}

function formatDatePickerValue(value) {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  return [
    date.getFullYear(),
    padNumber(date.getMonth() + 1),
    padNumber(date.getDate())
  ].join('-') + `T${padNumber(date.getHours())}:${padNumber(date.getMinutes())}:${padNumber(date.getSeconds())}`
}

function toUtcIso(value) {
  if (!value) return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date.toISOString()
}

function isExpired(pkg) {
  return Boolean(pkg.expires_at && new Date(pkg.expires_at).getTime() <= Date.now())
}

function expirationLabel(pkg) {
  if (!pkg.expires_at) return '长期有效'
  return isExpired(pkg) ? '已到期' : `有效至 ${formatTime(pkg.expires_at)}`
}

function openCreate() {
  editing.value = null
  resetForm()
  loadSelfNodes()
  dialogVisible.value = true
}

async function openEdit(row) {
  editing.value = row
  loadSelfNodes()
  const { data } = await getPackage(row.id)
  Object.assign(form, {
    name: data.name,
    subscription_name: data.subscription_name || '',
    token_name: data.token_name || '',
    description: data.description || '',
    enabled: data.enabled,
    expires_at: formatDatePickerValue(data.expires_at),
    owner_user_id: data.owner_user_id,
    rules: {
      source_filter: data.rules.source_filter || [],
      node_ids: data.rules.node_ids || [],
      country_filter: data.rules.country_filter || [],
      type_filter: data.rules.type_filter || [],
      include_keywords: data.rules.include_keywords || [],
      exclude_keywords: data.rules.exclude_keywords || []
    }
  })

  const renameRules = data.rules.rename_rules || []
  const firstRename = renameRules[0] || {}
  renameForm.prefix = firstRename.prefix || ''
  renameForm.suffix = firstRename.suffix || ''
  renameForm.replacements =
    Array.isArray(firstRename.replacements) && firstRename.replacements.length
      ? firstRename.replacements.map((item) => ({
          from: String(item.from || ''),
          to: String(item.to || '')
        }))
      : [{ from: '', to: '' }]
  renameForm.country_abbr = !!firstRename.country_abbr
  renameForm.numbered = !!firstRename.numbered
  extraRenameRules.value = renameRules.slice(1)

  const sortRules = data.rules.sort_rules || []
  const firstSort = sortRules[0] || {}
  sortForm.field = firstSort.field || 'country'
  sortForm.order = Array.isArray(firstSort.order) ? [...firstSort.order] : []
  sortForm.direction =
    firstSort.direction === 'asc' || firstSort.direction === 'desc'
      ? firstSort.direction
      : 'custom'
  extraSortRules.value = sortRules.slice(1)
  priorityInput.value = ''
  dialogVisible.value = true
}

async function save() {
  if (!form.name.trim()) {
    ElMessage.warning('请填写套餐名称')
    return
  }
  const renameRule = {}
  if (renameForm.prefix) renameRule.prefix = renameForm.prefix
  if (renameForm.suffix) renameRule.suffix = renameForm.suffix
  const replacements = renameForm.replacements
    .filter((item) => item.from && item.from.trim())
    .map((item) => ({ from: item.from.trim(), to: (item.to || '').trim() }))
  if (replacements.length) renameRule.replacements = replacements
  if (renameForm.country_abbr) renameRule.country_abbr = true
  if (renameForm.numbered) renameRule.numbered = true
  const rename_rules = Object.keys(renameRule).length
    ? [renameRule, ...extraRenameRules.value]
    : [...extraRenameRules.value]

  const sortRule = { field: sortForm.field || 'country' }
  if (sortForm.order.length) sortRule.order = [...sortForm.order]
  if (sortForm.direction === 'asc' || sortForm.direction === 'desc') {
    sortRule.direction = sortForm.direction
  }
  const sort_rules = [sortRule, ...extraSortRules.value]

  saving.value = true
  try {
    const payload = {
      ...form,
      expires_at: toUtcIso(form.expires_at),
      rules: {
        ...form.rules,
        rename_rules,
        sort_rules
      }
    }
    if (editing.value) {
      await updatePackage(editing.value.id, payload)
    } else {
      const { data } = await createPackage(payload)
      ElMessageBox.alert(
        `订阅 Token：${data.token}\n订阅地址：${data.subscription_url}`,
        '套餐已创建（Token 仅显示一次）',
        { confirmButtonText: '我已保存' }
      )
    }
    dialogVisible.value = false
    ElMessage.success(editing.value ? '套餐已更新' : '套餐创建成功')
    await load()
  } finally {
    saving.value = false
  }
}

async function copyUrl(row) {
  if ((packageNodeCounts.value[row.id] ?? 0) <= 0) {
    ElMessage.warning('当前套餐暂无可用节点')
    return
  }
  try {
    const { data } = await getPackageSubscriptionUrl(row.id)
    await navigator.clipboard.writeText(data.subscription_url)
    ElMessage.success('订阅地址已复制')
  } catch {
    ElMessage.error('复制失败，请手动复制')
  }
}

async function showQr(row) {
  if ((packageNodeCounts.value[row.id] ?? 0) <= 0) {
    ElMessage.warning('当前套餐暂无可用节点')
    return
  }
  try {
    const { data } = await getPackageSubscriptionUrl(row.id)
    qrUrl.value = data.subscription_url
    qrDataUrl.value = await QRCode.toDataURL(data.subscription_url, {
      width: 240,
      margin: 1
    })
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

async function regenerate(row) {
  const { data } = await regenerateToken(row.id)
  ElMessageBox.alert(
    `新 Token：${data.token}\n订阅地址：${data.subscription_url}`,
    'Token 已重生成（旧 Token 立即失效）',
    { confirmButtonText: '我已保存' }
  )
  await load()
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
  await ElMessageBox.confirm(
    `删除「${row.name}」后，该订阅地址将立即失效。`,
    '删除套餐？',
    {
      type: 'warning',
      confirmButtonText: '确认删除',
      cancelButtonText: '取消'
    }
  )
  await deletePackage(row.id)
  ElMessage.success('已删除')
  await load()
}

async function handleMore(command, row) {
  if (command === 'preview') await preview(row)
  if (command === 'regenerate') await regenerate(row)
  if (command === 'toggle') await toggle(row)
  if (command === 'delete') await remove(row)
}

function formatTime(value) {
  return value ? new Date(value).toLocaleString() : '-'
}

onMounted(() => {
  load()
  loadSources()
  loadUsers()
  loadSelfNodes()
})
</script>

<style scoped>
.spacer {
  flex: 1;
}

.dialog-subtitle {
  margin: 0 0 16px;
  color: var(--app-text-secondary);
  font-size: 13px;
}

.form-row {
  display: flex;
  gap: 16px;
}

.form-hint {
  margin-top: 4px;
  font-size: 12px;
  color: var(--app-text-muted);
}

.package-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  min-height: 200px;
}

.package-card {
  flex: 1 1 520px;
  max-width: 100%;
  display: flex;
  flex-direction: column;
  gap: 16px;
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
  transition: border-color 150ms ease, box-shadow 150ms ease;
}

.package-card:hover {
  border-color: var(--app-border-strong);
  box-shadow: 0 4px 12px rgba(16, 24, 40, 0.06);
}

.package-name {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 19px;
  font-weight: 700;
  color: var(--app-text);
}

.package-index {
  color: var(--app-text-secondary);
  font-variant-numeric: tabular-nums;
}

.package-sub {
  margin-top: 4px;
  font-size: 13px;
  color: var(--app-text-muted);
}

.package-meta {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.meta-block {
  background: #fafbfc;
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-sm);
  padding: 10px 12px;
}

.meta-label {
  font-size: 13px;
  color: var(--app-text-muted);
  margin-bottom: 4px;
}

.meta-value {
  font-size: 15px;
  font-weight: 600;
  color: var(--app-text);
  word-break: break-all;
}

.source-warning {
  margin-top: 6px;
  color: var(--el-color-warning-dark-2);
  font-size: 12px;
  line-height: 1.5;
  word-break: break-word;
}

.no-nodes {
  color: var(--app-text-muted);
  font-weight: 500;
}

.package-updated {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 12px;
  border-top: 1px solid var(--app-border);
}

.updated-value {
  font-size: 13px;
  color: var(--app-text-secondary);
}

.package-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: auto;
  flex-wrap: wrap;
}

.package-actions .el-button {
  height: 36px;
  font-size: 14px;
}

.package-empty {
  width: 100%;
}

.node-source-box {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  width: 100%;
}

.source-group {
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-sm);
  padding: 12px;
}

.source-group-title {
  margin-bottom: 10px;
  font-size: 14px;
  font-weight: 600;
  color: var(--app-text);
}

.source-check-list {
  max-height: 220px;
  overflow-y: auto;
  margin-bottom: 8px;
}

.source-group > .source-warning {
  margin-bottom: 8px;
}

.source-check,
.self-node-check {
  display: flex;
  width: 100%;
  height: auto;
  margin-right: 0;
  padding: 6px 0;
  white-space: normal;
}

.self-node-list {
  max-height: 220px;
  overflow-y: auto;
  margin-top: 8px;
  margin-bottom: 8px;
}

.self-node-check {
  flex-direction: column;
  align-items: flex-start;
}

.node-option-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--app-text);
}

.node-option-meta {
  margin-top: 2px;
  font-size: 13px;
  color: var(--app-text-secondary);
}

.source-actions {
  display: flex;
  gap: 8px;
}

.qr-body {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
}

.qr-image {
  width: 240px;
  height: 240px;
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-sm);
}

.qr-url {
  max-width: 100%;
  font-size: 13px;
  color: var(--app-text-secondary);
  word-break: break-all;
  text-align: center;
}

.keyword-box {
  width: 100%;
}

.keyword-add {
  display: flex;
  gap: 8px;
}

.keyword-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.rename-list {
  width: 100%;
}

.rename-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.arrow {
  color: var(--app-text-muted);
}

.rule-options {
  display: flex;
  gap: 16px;
  margin-top: 8px;
}

.rule-extra {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.priority-add {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}

.priority-list {
  width: 100%;
}

.priority-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-sm);
  margin-bottom: 6px;
}

.priority-index {
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  background: #f2f4f7;
  color: var(--app-text-secondary);
  font-size: 12px;
  font-weight: 600;
}

.priority-value {
  flex: 1;
  font-size: 13px;
  color: var(--app-text);
}

@media (max-width: 768px) {
  .package-meta {
    grid-template-columns: 1fr;
  }

  .node-source-box {
    grid-template-columns: 1fr;
  }

  .form-row {
    flex-direction: column;
    gap: 0;
  }
}
</style>
