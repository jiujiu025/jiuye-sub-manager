<template>
  <div class="health-page">
    <header class="health-header">
      <div class="health-title-block">
        <div class="health-live-line"><span class="live-dot" />线路信号台 <span class="live-rule" />{{ lastUpdated ? `最近采样 ${lastUpdated}` : '等待首轮采样' }}</div>
        <h2>线路健康大屏</h2>
        <p>只显示启用中的导入外部线路，异常线路会自动排到最前。</p>
      </div>
      <div class="health-actions">
        <label class="auto-refresh-control">
          <span>自动刷新</span>
          <el-switch v-model="autoRefresh" size="small" />
        </label>
        <el-tooltip content="立即刷新线路状态" placement="bottom">
          <el-button class="icon-button" :loading="refreshing" aria-label="立即刷新" @click="loadNodes()">
            <el-icon><Refresh /></el-icon>
          </el-button>
        </el-tooltip>
        <el-button class="manage-button" @click="router.push('/nodes')">
          <el-icon><Grid /></el-icon>
          资源池
        </el-button>
      </div>
    </header>

    <section class="signal-deck" aria-label="线路总览">
      <div class="signal-copy">
        <div class="signal-mark"><el-icon><Connection /></el-icon><span>LIVE NODE TELEMETRY</span></div>
        <h1><strong>{{ summary.healthy }}</strong><span> / {{ summary.total }}</span> 条线路正常</h1>
        <p v-if="summary.total">当前有 {{ summary.attention }} 条线路需要关注，检测覆盖率 {{ summary.checkedRate }}%。</p>
        <p v-else>还没有启用的外部线路，导入线路后这里会开始采样。</p>
        <div class="signal-actions">
          <button class="signal-link" type="button" @click="setStatusFilter('attention')">
            <span class="signal-link-dot alert" />查看异常线路 <el-icon><ArrowRight /></el-icon>
          </button>
          <button class="signal-link quiet" type="button" @click="router.push('/settings')">
            检查检测设置 <el-icon><ArrowRight /></el-icon>
          </button>
        </div>
      </div>
      <div class="signal-monitor" aria-label="当前线路序列信号">
        <div class="monitor-topline"><span>线路序列信号</span><strong>{{ summary.healthRate }}<small>% HEALTH</small></strong></div>
        <div class="monitor-grid">
          <span v-for="(bar, index) in signalBars" :key="index" class="monitor-bar" :class="{ dim: bar === 0 }" :style="{ height: `${bar}%` }" />
          <span class="monitor-scanline" />
        </div>
        <div class="monitor-scale"><span>0</span><span>12</span><span>24</span></div>
      </div>
    </section>

    <section class="metric-strip" aria-label="健康指标">
      <div class="metric-cell metric-main">
        <span class="metric-label">正常线路</span>
        <strong>{{ summary.healthy }}</strong>
        <span class="metric-tail">条</span>
      </div>
      <div class="metric-cell">
        <span class="metric-label">异常 / 离线</span>
        <strong class="metric-alert">{{ summary.attention }}</strong>
        <span class="metric-tail">条</span>
      </div>
      <div class="metric-cell">
        <span class="metric-label">平均延迟</span>
        <strong>{{ summary.averageLatency }}</strong>
        <span class="metric-tail">ms</span>
      </div>
      <div class="metric-cell">
        <span class="metric-label">已检测</span>
        <strong>{{ summary.checked }}</strong>
        <span class="metric-tail">/ {{ summary.total }}</span>
      </div>
      <div class="metric-cell metric-last">
        <span class="metric-label">检测模式</span>
        <strong class="mode-value">实时</strong>
        <span class="metric-tail">外部线路</span>
      </div>
    </section>

    <section class="analysis-grid">
      <article class="data-panel state-panel">
        <div class="panel-heading">
          <div><h3>状态分布</h3><p>所有启用外部线路的当前快照</p></div>
          <span class="panel-index">01 / STATE</span>
        </div>
        <div class="state-rail" aria-label="健康状态比例">
          <span v-for="item in statusItems" :key="item.key" :class="`rail-${item.key}`" :style="{ width: `${item.percent}%` }" />
        </div>
        <div class="state-legend">
          <button v-for="item in statusItems" :key="item.key" type="button" class="legend-item" @click="setStatusFilter(item.key)">
            <span class="legend-swatch" :class="`swatch-${item.key}`" />
            <span>{{ item.label }}</span>
            <strong>{{ item.count }}</strong>
          </button>
        </div>
      </article>

      <article class="data-panel latency-panel">
        <div class="panel-heading">
          <div><h3>延迟分布</h3><p>按最近一次探测耗时统计</p></div>
          <span class="panel-index">02 / LATENCY</span>
        </div>
        <div class="latency-bars">
          <div v-for="band in latencyBands" :key="band.label" class="latency-item">
            <div class="latency-value"><span>{{ band.label }}</span><strong>{{ band.count }}</strong></div>
            <div class="latency-track"><span :style="{ width: `${band.percent}%` }" /></div>
          </div>
        </div>
      </article>

      <article class="data-panel protocol-panel">
        <div class="panel-heading">
          <div><h3>协议构成</h3><p>当前线路池的协议分布</p></div>
          <span class="panel-index">03 / PROTOCOL</span>
        </div>
        <div v-if="protocols.length" class="protocol-list">
          <div v-for="protocol in protocols" :key="protocol.type" class="protocol-item">
            <span class="protocol-dot" :style="{ background: protocol.color }" />
            <span class="protocol-name">{{ protocol.type }}</span>
            <span class="protocol-track"><i :style="{ width: `${protocol.percent}%`, background: protocol.color }" /></span>
            <strong>{{ protocol.count }}</strong>
          </div>
        </div>
        <div v-else class="panel-empty">暂无协议数据</div>
      </article>
    </section>

    <section class="line-board data-panel">
      <div class="board-heading">
        <div>
          <div class="board-title-line"><h3>线路矩阵</h3><span class="board-count">{{ filteredRows.length }} / {{ summary.total }}</span></div>
          <p>异常优先排列，点击线路可进入资源池。</p>
        </div>
        <div class="board-tools">
          <el-input v-model="search" class="search-input" clearable placeholder="搜索名称或服务器">
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
          <el-select v-model="protocolFilter" class="protocol-select" placeholder="协议">
            <el-option label="全部协议" value="all" />
            <el-option v-for="protocol in protocols" :key="protocol.type" :label="protocol.type" :value="protocol.type" />
          </el-select>
        </div>
      </div>
      <div class="status-tabs" role="tablist" aria-label="线路状态筛选">
        <button v-for="item in filterItems" :key="item.key" type="button" :class="{ active: statusFilter === item.key }" @click="setStatusFilter(item.key)">
          {{ item.label }} <span>{{ item.count }}</span>
        </button>
      </div>

      <div class="matrix-head" role="row">
        <span>线路 / 服务器</span><span>协议</span><span>状态</span><span>延迟</span><span>TCP / TLS</span><span>最近检测</span><span />
      </div>
      <div v-if="loading" class="matrix-state"><el-icon class="is-loading"><Loading /></el-icon><span>正在读取线路信号...</span></div>
      <div v-else-if="error" class="matrix-state matrix-error"><el-icon><WarningFilled /></el-icon><span>{{ error }}</span><button type="button" @click="loadNodes()">重试</button></div>
      <div v-else-if="!filteredRows.length" class="matrix-state"><el-icon><Search /></el-icon><span>{{ rows.length ? '没有符合当前筛选的线路' : '暂无启用的外部线路' }}</span></div>
      <div v-else class="matrix-body" role="rowgroup">
        <div v-for="row in filteredRows" :key="row.id" class="matrix-row" role="row" tabindex="0" @click="openNode(row)" @keydown.enter="openNode(row)">
          <div class="line-identity">
            <span class="status-light" :class="`light-${statusOf(row)}`" />
            <div><strong>{{ row.name }}</strong><small>{{ row.server }}:{{ row.port }}</small></div>
          </div>
          <span class="protocol-code">{{ row.type }}</span>
          <span class="status-word" :class="`word-${statusOf(row)}`">{{ statusLabel(statusOf(row)) }}</span>
          <strong class="latency-number">{{ row.health_latency_ms ?? '—' }}<small v-if="row.health_latency_ms"> ms</small></strong>
          <div class="probe-breakdown" :title="row.health_detail || '暂无分项结果'">
            <span :class="`probe-${probeState(row.health_tcp_status)}`">TCP {{ probeLabel(row.health_tcp_status) }}</span>
            <span :class="`probe-${probeState(row.health_tls_status)}`">TLS {{ probeLabel(row.health_tls_status) }}</span>
          </div>
          <span class="checked-time">{{ formatChecked(row.health_checked_at) }}</span>
          <el-icon class="row-arrow"><ArrowRight /></el-icon>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { listNodes } from '../api'

const router = useRouter()
const rows = ref([])
const loading = ref(true)
const refreshing = ref(false)
const error = ref('')
const search = ref('')
const statusFilter = ref('all')
const protocolFilter = ref('all')
const autoRefresh = ref(true)
const lastUpdated = ref('')
let refreshTimer

const statusMeta = {
  healthy: { label: '正常', color: '#63e6be' },
  degraded: { label: '异常', color: '#f3b562' },
  offline: { label: '离线', color: '#ff6b6b' },
  unknown: { label: '待检测', color: '#8995a7' }
}

const summary = computed(() => {
  const total = rows.value.length
  const healthy = rows.value.filter((row) => statusOf(row) === 'healthy').length
  const attention = rows.value.filter((row) => ['degraded', 'offline'].includes(statusOf(row))).length
  const checked = rows.value.filter((row) => statusOf(row) !== 'unknown').length
  const latencies = rows.value.map((row) => row.health_latency_ms).filter((value) => Number.isFinite(value))
  const average = latencies.length ? Math.round(latencies.reduce((sum, value) => sum + value, 0) / latencies.length) : 0
  return {
    total,
    healthy,
    attention,
    checked,
    averageLatency: average || '—',
    healthRate: total ? Math.round((healthy / total) * 100) : 0,
    checkedRate: total ? Math.round((checked / total) * 100) : 0
  }
})

const statusItems = computed(() => Object.entries(statusMeta).map(([key, meta]) => {
  const count = rows.value.filter((row) => statusOf(row) === key).length
  return { key, ...meta, count, percent: summary.value.total ? (count / summary.value.total) * 100 : 0 }
}))

const filterItems = computed(() => [
  { key: 'all', label: '全部', count: summary.value.total },
  { key: 'attention', label: '需关注', count: summary.value.attention },
  { key: 'healthy', label: '正常', count: summary.value.healthy },
  { key: 'unknown', label: '待检测', count: rows.value.filter((row) => statusOf(row) === 'unknown').length }
])

const latencyBands = computed(() => {
  const bands = [
    { label: '0—100', min: 0, max: 100 },
    { label: '101—300', min: 101, max: 300 },
    { label: '301—800', min: 301, max: 800 },
    { label: '800+', min: 801, max: Infinity }
  ]
  const values = rows.value.map((row) => row.health_latency_ms).filter((value) => Number.isFinite(value))
  const maxCount = Math.max(1, ...bands.map((band) => values.filter((value) => value >= band.min && value <= band.max).length))
  return bands.map((band) => {
    const count = values.filter((value) => value >= band.min && value <= band.max).length
    return { ...band, count, percent: (count / maxCount) * 100 }
  })
})

const protocols = computed(() => {
  const counts = rows.value.reduce((result, row) => {
    result[row.type] = (result[row.type] || 0) + 1
    return result
  }, {})
  const colors = ['#63e6be', '#6ea8fe', '#f3b562', '#d8a7ff', '#ff7b72', '#9aa6b2']
  const total = rows.value.length || 1
  return Object.entries(counts)
    .sort(([, left], [, right]) => right - left)
    .map(([type, count], index) => ({ type, count, color: colors[index % colors.length], percent: (count / total) * 100 }))
})

const filteredRows = computed(() => {
  const keyword = search.value.trim().toLowerCase()
  return [...rows.value]
    .filter((row) => {
      const status = statusOf(row)
      const matchesStatus = statusFilter.value === 'all'
        || (statusFilter.value === 'attention' && ['degraded', 'offline'].includes(status))
        || status === statusFilter.value
      const matchesProtocol = protocolFilter.value === 'all' || row.type === protocolFilter.value
      const matchesKeyword = !keyword || [row.name, row.server, row.type].some((value) => String(value || '').toLowerCase().includes(keyword))
      return matchesStatus && matchesProtocol && matchesKeyword
    })
    .sort((left, right) => {
      const priority = { offline: 0, degraded: 1, unknown: 2, healthy: 3 }
      const statusDiff = priority[statusOf(left)] - priority[statusOf(right)]
      if (statusDiff) return statusDiff
      return (right.health_latency_ms || -1) - (left.health_latency_ms || -1)
    })
})

const signalBars = computed(() => {
  const source = rows.value.length ? rows.value : Array.from({ length: 24 }, () => ({ health_status: 'unknown' }))
  return Array.from({ length: 24 }, (_, index) => {
    const start = Math.floor((index / 24) * source.length)
    const end = Math.max(start + 1, Math.floor(((index + 1) / 24) * source.length))
    const slice = source.slice(start, end)
    const score = slice.reduce((sum, row) => sum + ({ healthy: 82, degraded: 52, offline: 28, unknown: 12 }[statusOf(row)] || 12), 0) / slice.length
    return Math.round(score)
  })
})

async function loadNodes(options = {}) {
  const silent = options.silent === true
  if (silent) refreshing.value = true
  else loading.value = true
  error.value = ''
  try {
    const pageSize = 100
    const allRows = []
    let page = 1
    let total = 0
    do {
      const { data } = await listNodes({ source_kind: 'custom', enabled: true, page, page_size: pageSize })
      allRows.push(...data.items)
      total = data.total
      page += 1
      if (!data.items.length) break
    } while (allRows.length < total)
    rows.value = allRows
    lastUpdated.value = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    error.value = rows.value.length ? '刷新失败，正在显示上一次采样结果' : '无法读取线路状态，请确认后端服务正在运行'
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

function statusOf(row) {
  return statusMeta[row.health_status] ? row.health_status : 'unknown'
}

function statusLabel(status) {
  return statusMeta[status]?.label || '待检测'
}

function probeState(value) {
  return ({ passed: 'passed', failed: 'failed', not_applicable: 'na', unknown: 'unknown' })[value] || 'unknown'
}

function probeLabel(value) {
  return ({ passed: '通过', failed: '失败', not_applicable: '不适用', unknown: '未知' })[value] || '未知'
}

function setStatusFilter(value) {
  statusFilter.value = value
}

function openNode(row) {
  router.push({ path: '/nodes', query: { keyword: row.name } })
}

function formatChecked(value) {
  return value ? new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '未检测'
}

onMounted(() => {
  loadNodes()
  refreshTimer = window.setInterval(() => {
    if (autoRefresh.value) loadNodes({ silent: true })
  }, 30 * 1000)
})

onBeforeUnmount(() => {
  if (refreshTimer) window.clearInterval(refreshTimer)
})
</script>

<style scoped>
.health-page {
  --health-bg: #0e151b;
  --health-panel: #141f26;
  --health-panel-soft: #18262e;
  --health-line: rgba(218, 235, 228, 0.13);
  --health-text: #edf7f0;
  --health-muted: #91a49c;
  --health-green: #63e6be;
  --health-amber: #f3b562;
  --health-red: #ff6b6b;
  --health-blue: #6ea8fe;
  min-height: calc(100vh - 116px);
  padding: 24px;
  overflow: hidden;
  color: var(--health-text);
  background: var(--health-bg);
  border: 1px solid rgba(218, 235, 228, 0.08);
  border-radius: 16px;
  font-variant-numeric: tabular-nums;
}

.health-header,
.board-heading,
.panel-heading,
.monitor-topline,
.health-actions,
.signal-actions,
.board-tools,
.board-title-line {
  display: flex;
  align-items: center;
}

.health-header,
.board-heading,
.panel-heading {
  justify-content: space-between;
  gap: 18px;
}

.health-header { margin-bottom: 24px; }
.health-title-block { min-width: 0; }
.health-live-line,
.signal-mark {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--health-green);
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .08em;
  text-transform: uppercase;
}

.live-dot,
.signal-link-dot,
.status-light,
.protocol-dot,
.legend-swatch {
  display: inline-block;
  flex-shrink: 0;
  border-radius: 50%;
}

.live-dot { width: 7px; height: 7px; background: var(--health-green); box-shadow: 0 0 0 4px rgba(99, 230, 190, .13); }
.live-rule { width: 26px; height: 1px; margin-left: 2px; background: var(--health-line); }
.health-title-block h2 { margin: 9px 0 0; color: var(--health-text); font-size: 27px; line-height: 1.1; letter-spacing: -.02em; }
.health-title-block p { margin: 7px 0 0; color: var(--health-muted); font-size: 12px; }
.health-actions { gap: 10px; flex-shrink: 0; }
.auto-refresh-control { display: flex; align-items: center; gap: 8px; color: var(--health-muted); font-size: 12px; }
.icon-button,
.manage-button { color: var(--health-text); border-color: var(--health-line); background: var(--health-panel); }
.icon-button { width: 36px; height: 36px; padding: 0; }
.manage-button { height: 36px; }
.icon-button:hover,
.manage-button:hover { color: var(--health-green); border-color: rgba(99, 230, 190, .42); background: var(--health-panel-soft); }

.signal-deck {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(300px, .9fr);
  gap: 24px;
  min-height: 238px;
  padding: 28px;
  border: 1px solid rgba(99, 230, 190, .18);
  border-radius: 12px;
  background: #111b21;
  box-shadow: 0 18px 36px rgba(0, 0, 0, .16);
}
.signal-copy { align-self: center; }
.signal-mark { color: var(--health-muted); }
.signal-mark .el-icon { color: var(--health-green); font-size: 15px; }
.signal-copy h1 { margin: 18px 0 10px; color: var(--health-text); font-size: clamp(29px, 4vw, 48px); line-height: 1; letter-spacing: -.04em; }
.signal-copy h1 strong { color: var(--health-green); font-weight: 800; }
.signal-copy h1 span { color: #8ca39a; font-size: .54em; letter-spacing: -.02em; }
.signal-copy p { max-width: 46ch; margin: 0; color: var(--health-muted); font-size: 13px; line-height: 1.6; }
.signal-actions { gap: 20px; flex-wrap: wrap; margin-top: 22px; }
.signal-link { display: inline-flex; align-items: center; gap: 8px; padding: 0; border: 0; color: var(--health-text); background: none; font: inherit; font-size: 12px; cursor: pointer; }
.signal-link:hover { color: var(--health-green); }
.signal-link.quiet { color: var(--health-muted); }
.signal-link-dot { width: 7px; height: 7px; background: var(--health-red); box-shadow: 0 0 0 4px rgba(255, 107, 107, .13); }
.signal-link .el-icon { font-size: 13px; }
.signal-monitor { align-self: center; padding: 16px; border: 1px solid var(--health-line); border-radius: 8px; background: #0c1318; }
.monitor-topline { justify-content: space-between; color: var(--health-muted); font-size: 11px; }
.monitor-topline strong { color: var(--health-green); font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 18px; }
.monitor-topline small { margin-left: 4px; color: var(--health-muted); font-size: 9px; font-weight: 700; }
.monitor-grid { position: relative; display: flex; align-items: end; gap: 5px; height: 112px; margin-top: 13px; padding: 10px 6px; overflow: hidden; border-top: 1px solid var(--health-line); border-bottom: 1px solid var(--health-line); background-color: #0f1a1f; background-image: linear-gradient(rgba(99, 230, 190, .08) 1px, transparent 1px), linear-gradient(90deg, rgba(99, 230, 190, .06) 1px, transparent 1px); background-size: 100% 25%, 12.5% 100%; }
.monitor-bar { position: relative; z-index: 1; flex: 1; min-width: 3px; background: var(--health-green); opacity: .92; animation: monitor-pulse 2.4s ease-in-out infinite alternate; transform-origin: bottom; }
.monitor-bar:nth-child(3n) { background: #88f0cf; animation-delay: -420ms; }
.monitor-bar:nth-child(4n) { background: var(--health-amber); animation-delay: -780ms; }
.monitor-bar.dim { background: #697d77; opacity: .55; }
.monitor-scanline { position: absolute; z-index: 2; top: 0; bottom: 0; left: 52%; width: 1px; background: rgba(255, 255, 255, .26); box-shadow: 0 0 10px rgba(99, 230, 190, .55); }
.monitor-scale { display: flex; justify-content: space-between; margin-top: 8px; color: #62736c; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 9px; }

.metric-strip { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); margin: 18px 0 24px; border-top: 1px solid var(--health-line); border-bottom: 1px solid var(--health-line); }
.metric-cell { display: flex; align-items: baseline; gap: 6px; min-width: 0; padding: 14px 18px; border-right: 1px solid var(--health-line); }
.metric-cell:first-child { padding-left: 0; }
.metric-last { border-right: 0; }
.metric-label { color: var(--health-muted); font-size: 11px; white-space: nowrap; }
.metric-cell strong { margin-left: auto; color: var(--health-text); font-size: 21px; }
.metric-cell .metric-alert { color: var(--health-red); }
.metric-cell .mode-value { color: var(--health-green); font-size: 15px; }
.metric-tail { color: #75877f; font-size: 10px; white-space: nowrap; }

.analysis-grid { display: grid; grid-template-columns: 1.1fr 1fr .9fr; gap: 12px; }
.data-panel { border: 1px solid var(--health-line); border-radius: 10px; background: var(--health-panel); }
.analysis-grid .data-panel { min-height: 220px; padding: 20px; }
.panel-heading { align-items: flex-start; }
.panel-heading h3,
.board-heading h3 { margin: 0; color: var(--health-text); font-size: 16px; letter-spacing: -.01em; }
.panel-heading p,
.board-heading p { margin: 6px 0 0; color: var(--health-muted); font-size: 11px; }
.panel-index { color: #60726b; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 9px; letter-spacing: .08em; white-space: nowrap; }
.state-rail { display: flex; height: 10px; margin: 34px 0 24px; overflow: hidden; border-radius: 2px; background: #26353a; }
.state-rail span { min-width: 2px; }
.rail-healthy { background: var(--health-green); }.rail-degraded { background: var(--health-amber); }.rail-offline { background: var(--health-red); }.rail-unknown { background: #73817e; }
.state-legend { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px 14px; }
.legend-item { display: grid; grid-template-columns: 8px 1fr auto; align-items: center; gap: 7px; padding: 0; border: 0; color: var(--health-muted); background: none; font: inherit; font-size: 11px; text-align: left; cursor: pointer; }
.legend-item:hover { color: var(--health-text); }.legend-item strong { color: var(--health-text); font-size: 13px; }
.legend-swatch { width: 7px; height: 7px; }.swatch-healthy { background: var(--health-green); }.swatch-degraded { background: var(--health-amber); }.swatch-offline { background: var(--health-red); }.swatch-unknown { background: #73817e; }
.latency-bars { display: grid; gap: 13px; margin-top: 31px; }
.latency-value { display: flex; justify-content: space-between; margin-bottom: 5px; color: var(--health-muted); font-size: 10px; }.latency-value strong { color: var(--health-text); font-size: 11px; }
.latency-track,.protocol-track { display: block; height: 5px; overflow: hidden; background: #26353a; }.latency-track span { display: block; height: 100%; background: var(--health-blue); }
.protocol-list { display: grid; gap: 12px; margin-top: 28px; }.protocol-item { display: grid; grid-template-columns: 8px 62px 1fr 24px; align-items: center; gap: 8px; color: var(--health-muted); font-size: 10px; }.protocol-dot { width: 7px; height: 7px; }.protocol-track { height: 4px; }.protocol-track i { display: block; height: 100%; }.protocol-item strong { color: var(--health-text); font-size: 11px; text-align: right; }.panel-empty { margin-top: 32px; color: var(--health-muted); font-size: 12px; }

.line-board { margin-top: 12px; padding: 20px 20px 8px; }
.board-heading { align-items: flex-start; }.board-title-line { gap: 10px; }.board-count { color: var(--health-muted); font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 10px; }.board-tools { gap: 8px; flex-shrink: 0; }.search-input { width: 220px; }.protocol-select { width: 128px; }
.line-board :deep(.el-input__wrapper), .line-board :deep(.el-select__wrapper) { background: #0e171d; box-shadow: 0 0 0 1px var(--health-line) inset; }.line-board :deep(.el-input__inner), .line-board :deep(.el-select__selected-item) { color: var(--health-text); }.line-board :deep(.el-input__inner::placeholder) { color: #718179; }
.status-tabs { display: flex; gap: 4px; margin-top: 20px; padding-bottom: 12px; border-bottom: 1px solid var(--health-line); }.status-tabs button { padding: 6px 10px; border: 1px solid transparent; color: var(--health-muted); background: transparent; font: inherit; font-size: 11px; cursor: pointer; }.status-tabs button span { margin-left: 4px; color: #667770; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }.status-tabs button.active { border-color: rgba(99, 230, 190, .32); color: var(--health-green); background: rgba(99, 230, 190, .08); }.status-tabs button.active span { color: var(--health-green); }
.matrix-head,.matrix-row { display: grid; grid-template-columns: minmax(220px, 1.5fr) 82px 76px 76px 116px 92px 20px; align-items: center; gap: 12px; }.matrix-head { padding: 14px 8px 10px; color: #667770; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 9px; letter-spacing: .04em; text-transform: uppercase; }.matrix-row { min-height: 66px; padding: 10px 8px; border-top: 1px solid var(--health-line); color: var(--health-text); cursor: pointer; transition: background-color 160ms ease, transform 160ms ease; }.matrix-row:hover,.matrix-row:focus-visible { outline: none; background: rgba(99, 230, 190, .06); transform: translateX(2px); }.line-identity { display: flex; align-items: center; gap: 10px; min-width: 0; }.status-light { width: 8px; height: 8px; }.light-healthy { background: var(--health-green); box-shadow: 0 0 0 4px rgba(99, 230, 190, .1); }.light-degraded { background: var(--health-amber); box-shadow: 0 0 0 4px rgba(243, 181, 98, .1); }.light-offline { background: var(--health-red); box-shadow: 0 0 0 4px rgba(255, 107, 107, .1); }.light-unknown { background: #8995a7; }.line-identity div { min-width: 0; }.line-identity strong,.line-identity small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.line-identity strong { font-size: 12px; }.line-identity small { margin-top: 4px; color: var(--health-muted); font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 10px; }.protocol-code,.checked-time { color: var(--health-muted); font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 10px; }.status-word { font-size: 11px; }.word-healthy { color: var(--health-green); }.word-degraded { color: var(--health-amber); }.word-offline { color: var(--health-red); }.word-unknown { color: #a6b0bd; }.latency-number { color: var(--health-text); font-size: 12px; }.latency-number small { color: var(--health-muted); font-size: 9px; font-weight: 400; }.probe-breakdown { display: grid; gap: 3px; min-width: 0; color: var(--health-muted); font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 9px; line-height: 1.2; }.probe-breakdown span::before { content: ''; display: inline-block; width: 5px; height: 5px; margin: 0 5px 1px 0; background: currentColor; }.probe-passed { color: var(--health-green); }.probe-failed { color: var(--health-red); }.probe-na { color: #8995a7; }.probe-unknown { color: var(--health-muted); }.checked-time { color: #82928b; }.row-arrow { color: #60726b; transition: transform 160ms ease, color 160ms ease; }.matrix-row:hover .row-arrow { color: var(--health-green); transform: translateX(3px); }
.matrix-state { display: flex; align-items: center; justify-content: center; gap: 10px; min-height: 180px; color: var(--health-muted); font-size: 12px; }.matrix-state .el-icon { color: var(--health-green); }.matrix-error .el-icon { color: var(--health-red); }.matrix-error button { padding: 0; border: 0; color: var(--health-green); background: none; font: inherit; cursor: pointer; }

@keyframes monitor-pulse { from { opacity: .72; } to { opacity: 1; } }

@media (max-width: 1120px) { .analysis-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }.protocol-panel { grid-column: 1 / -1; }.protocol-list { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 820px) { .health-page { padding: 18px; }.health-header { align-items: flex-start; flex-direction: column; }.health-actions { width: 100%; }.manage-button { margin-left: auto; }.signal-deck { grid-template-columns: 1fr; padding: 22px; }.metric-strip { grid-template-columns: repeat(2, 1fr); }.metric-cell,.metric-cell:first-child { padding: 13px 12px; }.metric-cell:nth-child(2n) { border-right: 0; }.metric-last { border-top: 1px solid var(--health-line); }.analysis-grid { grid-template-columns: 1fr; }.protocol-panel { grid-column: auto; }.protocol-list { grid-template-columns: 1fr; }.board-heading { align-items: stretch; flex-direction: column; }.board-tools { width: 100%; }.search-input { flex: 1; width: auto; }.matrix-head { display: none; }.matrix-row { grid-template-columns: minmax(0, 1fr) 70px 58px 112px 18px; gap: 8px; }.matrix-row > :nth-child(6) { display: none; } }
@media (max-width: 520px) { .health-page { padding: 14px; border-radius: 10px; }.health-title-block h2 { font-size: 23px; }.health-actions { flex-wrap: wrap; }.signal-copy h1 { font-size: 34px; }.metric-strip { grid-template-columns: 1fr 1fr; }.metric-cell { padding: 12px 8px; }.metric-cell strong { font-size: 18px; }.metric-label { font-size: 10px; }.metric-tail { font-size: 9px; }.board-tools { flex-direction: column; align-items: stretch; }.search-input,.protocol-select { width: 100%; }.status-tabs { overflow-x: auto; }.status-tabs button { flex-shrink: 0; }.matrix-row { grid-template-columns: minmax(0, 1fr) 58px 48px 18px; }.matrix-row > :nth-child(4),.matrix-row > :nth-child(5) { display: none; }.line-identity strong { font-size: 11px; } }
@media (prefers-reduced-motion: reduce) { .monitor-bar { animation: none; }.matrix-row { transition: none; } }
</style>
