<template>
  <div class="page dashboard-page">
    <section class="dashboard-hero">
      <div class="hero-copy">
        <div class="hero-status"><span class="hero-status-dot" />实时运营面板</div>
        <h2>欢迎回来，{{ authStore.username }}</h2>
        <p>把来源、节点和订阅状态收拢在一个清晰的控制中心。</p>
        <div class="hero-actions">
          <el-button type="primary" @click="router.push('/sources')">
            <el-icon><Connection /></el-icon>
            管理来源
          </el-button>
          <el-button class="hero-secondary" @click="router.push('/packages')">
            <el-icon><Tickets /></el-icon>
            查看套餐
          </el-button>
        </div>
      </div>
      <div class="signal-panel" aria-label="系统状态">
        <div class="signal-heading">
          <span>系统脉搏</span>
          <strong>{{ stats.failed_source_count ? '需要关注' : '运行稳定' }}</strong>
        </div>
        <div class="signal-bars" aria-hidden="true">
          <span class="bar bar-short" />
          <span class="bar bar-medium" />
          <span class="bar bar-tall" />
          <span class="bar bar-medium" />
          <span class="bar bar-short" />
          <span class="bar bar-tall" />
          <span class="bar bar-medium" />
        </div>
        <div class="signal-foot">
          <span>最近同步</span>
          <b>{{ stats.last_sync_at ? formatTime(stats.last_sync_at) : '尚未同步' }}</b>
        </div>
      </div>
    </section>

    <section class="stats-grid" aria-label="核心指标">
      <div v-for="(card, index) in cards" :key="card.label" class="stat-card" :class="`tone-${card.tone}`" :style="{ '--delay': `${index * 55}ms` }">
        <div class="stat-topline">
          <div class="stat-icon"><el-icon><component :is="card.icon" /></el-icon></div>
          <span class="stat-index">0{{ index + 1 }}</span>
        </div>
        <div class="stat-label">{{ card.label }}</div>
        <div class="stat-value">{{ card.value }}</div>
        <div class="stat-meta">{{ card.meta }}</div>
      </div>
    </section>

    <section class="dashboard-lower">
      <div class="surface-card pulse-card">
        <div class="section-heading">
          <div>
            <h3>同步脉搏</h3>
            <p>上游来源和节点池的最新状态</p>
          </div>
          <el-tag :type="stats.failed_source_count ? 'warning' : 'success'" effect="light">
            {{ stats.failed_source_count ? `${stats.failed_source_count} 个来源待处理` : '全部正常' }}
          </el-tag>
        </div>
        <div class="pulse-row">
          <div class="pulse-mark"><el-icon><Refresh /></el-icon></div>
          <div class="pulse-copy">
            <strong>{{ stats.last_sync_at ? '最近一次同步已完成' : '等待第一次同步' }}</strong>
            <span>{{ stats.last_sync_at ? formatTime(stats.last_sync_at) : '添加来源后开始构建节点池' }}</span>
          </div>
          <div class="pulse-number">
            <strong>{{ stats.node_count ?? 0 }}</strong>
            <span>节点在线池</span>
          </div>
        </div>
      </div>

      <div class="surface-card quick-card">
        <div class="section-heading">
          <div>
            <h3>快速入口</h3>
            <p>常用操作一步到位</p>
          </div>
          <el-icon class="section-heading-icon"><Right /></el-icon>
        </div>
        <button class="quick-link" type="button" @click="router.push('/nodes')">
          <span class="quick-icon cyan"><el-icon><Grid /></el-icon></span>
          <span><strong>节点池</strong><small>查看并导出节点</small></span>
          <el-icon><ArrowRight /></el-icon>
        </button>
        <button class="quick-link" type="button" @click="router.push('/logs')">
          <span class="quick-icon coral"><el-icon><Document /></el-icon></span>
          <span><strong>运行日志</strong><small>定位同步与订阅问题</small></span>
          <el-icon><ArrowRight /></el-icon>
        </button>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { getStats } from '../api'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const authStore = useAuthStore()
const stats = ref({})

const cards = computed(() => [
  {
    label: '订阅源',
    value: stats.value.source_count ?? 0,
    meta: `启用 ${stats.value.enabled_source_count ?? 0} 个来源`,
    tone: 'cyan',
    icon: 'Connection'
  },
  {
    label: '套餐',
    value: stats.value.package_count ?? 0,
    meta: `启用 ${stats.value.enabled_package_count ?? 0} 个套餐`,
    tone: 'violet',
    icon: 'Tickets'
  },
  {
    label: '节点池',
    value: stats.value.node_count ?? 0,
    meta: `自有节点 ${stats.value.self_node_count ?? 0} 个`,
    tone: 'amber',
    icon: 'Grid'
  },
  {
    label: '同步告警',
    value: stats.value.failed_source_count ?? 0,
    meta: stats.value.failed_source_count ? '需要及时检查' : '当前没有异常',
    tone: 'coral',
    icon: 'WarningFilled'
  }
])

onMounted(async () => {
  try {
    const { data } = await getStats()
    stats.value = data
  } catch {
    stats.value = {}
  }
})

function formatTime(value) {
  return value ? new Date(value).toLocaleString() : '-'
}
</script>

<style scoped>
.dashboard-page {
  display: flex;
  flex-direction: column;
  gap: 22px;
}

.dashboard-hero {
  position: relative;
  display: flex;
  justify-content: space-between;
  gap: 28px;
  overflow: hidden;
  min-height: 252px;
  padding: 32px 36px;
  border-radius: 22px;
  color: #fff;
  background: var(--app-ink);
  box-shadow: 0 20px 45px rgba(16, 23, 42, 0.2);
}

.hero-copy {
  position: relative;
  z-index: 1;
  max-width: 640px;
}

.hero-status {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 18px;
  color: #78ded7;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0;
}

.hero-status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--app-cyan);
  box-shadow: 0 0 0 5px rgba(24, 184, 178, 0.14);
}

.hero-copy h2 {
  margin: 0;
  font-size: 32px;
  line-height: 1.2;
  letter-spacing: -0.02em;
}

.hero-copy p {
  max-width: 48ch;
  margin: 12px 0 24px;
  color: #aab5ce;
  font-size: 14px;
  line-height: 1.6;
}

.hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.hero-actions .hero-secondary {
  color: #dce4f5;
  border-color: rgba(255, 255, 255, 0.16);
  background: rgba(255, 255, 255, 0.08);
}

.signal-panel {
  position: relative;
  z-index: 1;
  align-self: stretch;
  width: 280px;
  padding: 20px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.06);
}

.signal-heading,
.signal-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.signal-heading {
  color: #aab5ce;
  font-size: 12px;
}

.signal-heading strong {
  color: #fff;
  font-size: 13px;
}

.signal-bars {
  display: flex;
  align-items: end;
  gap: 8px;
  height: 92px;
  padding: 16px 4px 14px;
}

.bar {
  flex: 1;
  min-width: 7px;
  border-radius: 8px 8px 3px 3px;
  background: var(--app-cyan);
  animation: signal-breathe 2.8s ease-in-out infinite;
}

.bar:nth-child(2n) { background: var(--app-lilac); animation-delay: 180ms; }
.bar:nth-child(3n) { background: #f6bd62; animation-delay: 340ms; }
.bar-short { height: 28%; }
.bar-medium { height: 58%; }
.bar-tall { height: 86%; }

.signal-foot {
  padding-top: 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
  color: #8794b0;
  font-size: 11px;
}

.signal-foot b {
  color: #dce4f5;
  font-size: 11px;
  font-weight: 600;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

.stat-card {
  position: relative;
  overflow: hidden;
  padding: 20px;
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-md);
  background: #fff;
  box-shadow: var(--app-shadow);
  animation: card-enter 360ms ease-out var(--delay) both;
}

.stat-topline {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.stat-icon {
  display: grid;
  width: 38px;
  height: 38px;
  place-items: center;
  border-radius: 12px;
  color: var(--tone);
  background: var(--tone-soft);
  font-size: 19px;
}

.stat-index {
  color: var(--app-text-muted);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0;
}

.stat-label {
  position: relative;
  z-index: 1;
  margin-top: 22px;
  color: var(--app-text-secondary);
  font-size: 13px;
  font-weight: 600;
}

.stat-value {
  position: relative;
  z-index: 1;
  margin: 4px 0 3px;
  color: var(--app-text);
  font-size: 32px;
  font-weight: 750;
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
}

.stat-meta {
  position: relative;
  z-index: 1;
  color: var(--app-text-muted);
  font-size: 12px;
}

.tone-cyan { --tone: var(--app-cyan); --tone-soft: #e2f7f5; }
.tone-violet { --tone: var(--app-primary); --tone-soft: #eeedff; }
.tone-amber { --tone: var(--app-amber); --tone-soft: #fff4dc; }
.tone-coral { --tone: var(--app-coral); --tone-soft: #ffebe8; }

.dashboard-lower {
  display: grid;
  grid-template-columns: minmax(0, 1.45fr) minmax(300px, 0.75fr);
  gap: 16px;
}

.pulse-card,
.quick-card {
  min-height: 190px;
}

.section-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.section-heading h3 {
  margin: 0;
  color: var(--app-text);
  font-size: 17px;
}

.section-heading p {
  margin: 5px 0 0;
  color: var(--app-text-secondary);
  font-size: 12px;
}

.section-heading-icon {
  color: var(--app-text-muted);
}

.pulse-row {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-top: 30px;
}

.pulse-mark {
  display: grid;
  width: 44px;
  height: 44px;
  place-items: center;
  border-radius: 13px;
  color: var(--app-cyan);
  background: #e2f7f5;
  font-size: 19px;
}

.pulse-copy {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 5px;
}

.pulse-copy strong {
  color: var(--app-text);
  font-size: 14px;
}

.pulse-copy span,
.pulse-number span {
  color: var(--app-text-secondary);
  font-size: 12px;
}

.pulse-number {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
}

.pulse-number strong {
  color: var(--app-primary);
  font-size: 25px;
  line-height: 1;
}

.quick-card {
  padding-bottom: 14px;
}

.quick-link {
  display: flex;
  align-items: center;
  width: 100%;
  gap: 11px;
  padding: 12px 0;
  border: 0;
  border-bottom: 1px solid var(--app-border);
  color: var(--app-text);
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.quick-link:last-child { border-bottom: 0; }

.quick-link > span:nth-child(2) {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 3px;
}

.quick-link strong { font-size: 13px; }
.quick-link small { color: var(--app-text-secondary); font-size: 11px; }
.quick-link > .el-icon { color: var(--app-text-muted); }

.quick-icon {
  display: grid;
  width: 32px;
  height: 32px;
  place-items: center;
  border-radius: 10px;
  font-size: 16px;
}

.quick-icon.cyan { color: var(--app-cyan); background: #e2f7f5; }
.quick-icon.coral { color: var(--app-coral); background: #ffebe8; }

.quick-link:hover strong,
.quick-link:hover > .el-icon { color: var(--app-primary); }

@keyframes card-enter {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes signal-breathe {
  0%, 100% { opacity: 0.72; transform: scaleY(0.9); transform-origin: bottom; }
  50% { opacity: 1; transform: scaleY(1); transform-origin: bottom; }
}

@media (max-width: 1100px) {
  .stats-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .dashboard-lower { grid-template-columns: 1fr; }
}

@media (max-width: 720px) {
  .dashboard-hero { flex-direction: column; padding: 26px 22px; }
  .hero-copy h2 { font-size: 27px; }
  .signal-panel { width: 100%; }
  .stats-grid { grid-template-columns: 1fr; }
  .pulse-row { align-items: flex-start; }
  .pulse-number { margin-left: auto; }
}
</style>
