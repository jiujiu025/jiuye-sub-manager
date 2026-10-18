<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">系统设置</h2>
        <p class="page-subtitle">调整自动同步、节点健康检测、缓存与去重策略。</p>
      </div>
      <div class="page-header-mark"><el-icon><Setting /></el-icon><span>CONTROL</span></div>
    </div>
    <div class="surface-card settings-card">
    <el-form label-width="200px">
      <el-form-item label="自动同步间隔（分钟）">
        <el-input-number v-model="form.sync_interval_minutes" :min="1" :max="1440" />
      </el-form-item>
      <el-form-item label="定时同步开关">
        <el-switch v-model="form.sync_enabled" />
      </el-form-item>
      <el-divider content-position="left">节点健康检测</el-divider>
      <el-form-item label="健康检测开关">
        <el-switch v-model="form.health_enabled" />
      </el-form-item>
      <el-form-item label="检测模式">
        <el-select v-model="form.health_probe_mode" style="width: 220px">
          <el-option label="完整代理检测" value="full" />
          <el-option label="基础端口检测" value="basic" />
        </el-select>
        <div class="hint">完整模式会启动临时 sing-box，并实际访问测试网址。</div>
      </el-form-item>
      <el-form-item label="检测间隔（分钟）">
        <el-input-number v-model="form.health_interval_minutes" :min="1" :max="1440" />
      </el-form-item>
      <el-form-item label="单节点超时（秒）">
        <el-input-number v-model="form.health_timeout_seconds" :min="1" :max="60" :step="0.5" />
      </el-form-item>
      <el-form-item label="失败告警阈值">
        <el-input-number v-model="form.health_failure_threshold" :min="1" :max="10" />
      </el-form-item>
      <el-form-item label="恢复确认次数">
        <el-input-number v-model="form.health_recovery_threshold" :min="1" :max="10" />
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
          <el-option v-for="source in sourceOptions" :key="source" :label="source === '自有节点' ? '导入外部节点' : source" :value="source" />
        </el-select>
        <div class="hint">排在前面的来源优先保留，导入外部节点始终最高</div>
      </el-form-item>
      <el-divider content-position="left">外部通知推送</el-divider>
      <div class="notification-intro">
        <span>站内通知仍是主通道；外部渠道由后台每分钟投递一次。密钥只保存在服务端，页面不会回显。</span>
      </div>
      <section class="channel-section">
        <div class="channel-heading">
          <div><strong>Telegram 机器人</strong><span class="channel-status" :class="{ ready: form.telegram_configured }">{{ form.telegram_configured ? '已配置' : '未配置' }}</span></div>
          <el-switch v-model="form.telegram_enabled" />
        </div>
        <el-form-item label="Bot Token">
          <el-input v-model="form.telegram_bot_token" type="password" show-password placeholder="留空表示保持现有配置" autocomplete="new-password" />
        </el-form-item>
        <el-form-item label="Chat ID">
          <el-input v-model="form.telegram_chat_ids_text" type="textarea" :rows="2" placeholder="每行一个，也可以用逗号分隔" />
          <div v-if="form.telegram_chat_ids_masked.length" class="hint">当前接收人：{{ form.telegram_chat_ids_masked.join('、') }}</div>
        </el-form-item>
        <div class="channel-actions">
          <el-button plain :loading="testingChannel === 'telegram'" @click="testNotificationChannel('telegram')">发送测试</el-button>
          <el-button text type="danger" @click="clearTelegram">清除配置</el-button>
        </div>
      </section>
      <section class="channel-section">
        <div class="channel-heading">
          <div><strong>微信公众号模板消息</strong><span class="channel-status" :class="{ ready: form.wechat_configured }">{{ form.wechat_configured ? '已配置' : '未配置' }}</span></div>
          <el-switch v-model="form.wechat_enabled" />
        </div>
        <el-form-item label="AppID">
          <el-input v-model="form.wechat_app_id" placeholder="留空表示保持现有配置" autocomplete="off" />
        </el-form-item>
        <el-form-item label="AppSecret">
          <el-input v-model="form.wechat_app_secret" type="password" show-password placeholder="留空表示保持现有配置" autocomplete="new-password" />
        </el-form-item>
        <el-form-item label="模板 ID">
          <el-input v-model="form.wechat_template_id" placeholder="公众号模板消息的 template_id" />
        </el-form-item>
        <el-form-item label="接收 OpenID">
          <el-input v-model="form.wechat_openids_text" type="textarea" :rows="2" placeholder="每行一个 OpenID" />
          <div v-if="form.wechat_openids_masked.length" class="hint">当前接收人：{{ form.wechat_openids_masked.join('、') }}</div>
        </el-form-item>
        <div class="channel-actions">
          <el-button plain :loading="testingChannel === 'wechat'" @click="testNotificationChannel('wechat')">发送测试</el-button>
          <el-button text type="danger" @click="clearWechat">清除配置</el-button>
        </div>
      </section>
      <el-form-item>
        <el-button type="primary" :loading="saving" @click="save">保存设置</el-button>
      </el-form-item>
    </el-form>
    <el-alert
      type="info"
      :closable="false"
      title="生效说明"
      description="同步、健康检测和外部通知设置保存后立即生效。微信公众号需要已审核模板及接收用户 OpenID；企业微信机器人仍可通过 .env 用于节点健康告警。"
    />
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getSystemSettings, listSources, testNotification, updateSystemSettings } from '../api'

const saving = ref(false)
const testingChannel = ref('')
const sourceOptions = ref(['自有节点'])
const form = reactive({
  sync_interval_minutes: 5,
  sync_enabled: true,
  health_enabled: true,
  health_probe_mode: 'full',
  health_interval_minutes: 5,
  health_timeout_seconds: 5,
  health_failure_threshold: 3,
  health_recovery_threshold: 2,
  health_probe_concurrency: 20,
  cache_ttl_seconds: 300,
  dedup_source_priority: [],
  telegram_enabled: false,
  telegram_configured: false,
  telegram_chat_ids_masked: [],
  telegram_bot_token: '',
  telegram_chat_ids_text: '',
  clear_telegram_config: false,
  wechat_enabled: false,
  wechat_configured: false,
  wechat_openids_masked: [],
  wechat_app_id: '',
  wechat_app_secret: '',
  wechat_template_id: '',
  wechat_openids_text: '',
  clear_wechat_config: false
})

async function load() {
  const { data } = await getSystemSettings()
  Object.assign(form, data)
  form.telegram_bot_token = ''
  form.telegram_chat_ids_text = ''
  form.clear_telegram_config = false
  form.wechat_app_id = ''
  form.wechat_app_secret = ''
  form.wechat_template_id = ''
  form.wechat_openids_text = ''
  form.clear_wechat_config = false
}

async function loadSources() {
  const { data } = await listSources()
  const names = data.items.map((item) => item.name)
  sourceOptions.value = ['自有节点', ...names]
}

async function save() {
  saving.value = true
  try {
    const payload = {
      ...form,
    }
    if (form.telegram_chat_ids_text.trim()) {
      payload.telegram_chat_ids = splitValues(form.telegram_chat_ids_text)
    } else {
      delete payload.telegram_chat_ids
    }
    if (form.wechat_openids_text.trim()) {
      payload.wechat_openids = splitValues(form.wechat_openids_text)
    } else {
      delete payload.wechat_openids
    }
    if (!form.telegram_bot_token) delete payload.telegram_bot_token
    if (!form.wechat_app_id) delete payload.wechat_app_id
    if (!form.wechat_app_secret) delete payload.wechat_app_secret
    if (!form.wechat_template_id) delete payload.wechat_template_id
    await updateSystemSettings(payload)
    ElMessage.success('设置已保存并生效')
    await load()
  } finally {
    saving.value = false
  }
}

function splitValues(value) {
  return [...new Set(value.split(/[\n,]/).map((item) => item.trim()).filter(Boolean))]
}

function clearTelegram() {
  form.clear_telegram_config = true
  form.telegram_enabled = false
  form.telegram_bot_token = ''
  form.telegram_chat_ids_text = ''
  form.telegram_chat_ids_masked = []
  ElMessage.info('Telegram 配置将在保存后清除')
}

function clearWechat() {
  form.clear_wechat_config = true
  form.wechat_enabled = false
  form.wechat_app_id = ''
  form.wechat_app_secret = ''
  form.wechat_template_id = ''
  form.wechat_openids_text = ''
  form.wechat_openids_masked = []
  ElMessage.info('微信公众号配置将在保存后清除')
}

async function testNotificationChannel(channel) {
  testingChannel.value = channel
  try {
    const { data } = await testNotification({ channel, content: '这是一条 Sub-Manager 测试通知。' })
    ElMessage.success(`测试消息已发送（${data.sent_count} 个接收目标）`)
  } finally {
    testingChannel.value = ''
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

.notification-intro {
  margin: -4px 0 18px;
  color: var(--app-text-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.channel-section {
  margin: 18px 0 24px;
  padding-top: 18px;
  border-top: 1px solid var(--app-border);
}

.channel-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.channel-heading strong {
  margin-right: 10px;
  color: var(--app-text);
  font-size: 14px;
}

.channel-status {
  color: var(--app-text-muted);
  font-size: 12px;
}

.channel-status.ready {
  color: var(--app-success, #19a974);
}

.channel-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
