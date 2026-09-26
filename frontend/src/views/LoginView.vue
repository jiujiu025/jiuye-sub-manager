<template>
  <div class="login-page">
    <div class="login-shell">
      <div class="login-intro">
        <div class="login-brand-mark"><el-icon :size="24"><Cloudy /></el-icon></div>
        <div class="login-kicker">JIUYE CLOUD / CONTROL CENTER</div>
        <h1>订阅管理系统</h1>
        <p>让来源、节点和订阅分发保持清晰可控。</p>
        <div class="login-signals">
          <span><i class="signal-dot cyan" />来源同步</span>
          <span><i class="signal-dot violet" />节点编排</span>
          <span><i class="signal-dot coral" />订阅交付</span>
        </div>
      </div>
      <el-card class="login-card">
      <div class="login-card-head">
        <span>欢迎回来</span>
        <small>使用账号登录控制台</small>
      </div>
      <el-form label-position="top" @submit.prevent="submit">
        <el-form-item label="用户名">
          <el-input
            v-model="username"
            placeholder="请输入用户名"
            autocomplete="username"
          />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="password"
            type="password"
            show-password
            placeholder="请输入密码"
            autocomplete="current-password"
            @keyup.enter="submit"
          />
        </el-form-item>
        <el-button
          type="primary"
          class="login-button"
          :loading="loading"
          @click="submit"
        >
          登录
        </el-button>
      </el-form>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const authStore = useAuthStore()
const username = ref('')
const password = ref('')
const loading = ref(false)

async function submit() {
  if (!username.value || !password.value) {
    return
  }
  loading.value = true
  try {
    await authStore.login(username.value, password.value)
    router.push(authStore.role === 'user' ? '/my-subscriptions' : '/')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: var(--app-bg);
}

.login-shell {
  display: grid;
  grid-template-columns: minmax(280px, 1fr) 360px;
  gap: 56px;
  align-items: center;
  width: min(880px, 100%);
  padding: 56px;
  border: 1px solid var(--app-border);
  border-radius: 24px;
  background: #fff;
  box-shadow: 0 24px 70px rgba(16, 23, 42, 0.12);
  animation: login-enter 420ms ease-out both;
}

.login-intro {
  color: var(--app-text);
}

.login-brand-mark {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  margin-bottom: 26px;
  border-radius: 14px;
  color: var(--app-ink);
  background: var(--app-cyan);
  box-shadow: 0 12px 24px rgba(24, 184, 178, 0.22);
}

.login-kicker {
  color: var(--app-primary);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.08em;
}

.login-intro h1 {
  margin: 12px 0 10px;
  font-size: 32px;
  line-height: 1.2;
}

.login-intro p {
  max-width: 28ch;
  margin: 0;
  color: var(--app-text-secondary);
  line-height: 1.7;
}

.login-signals {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 30px;
  color: var(--app-text-secondary);
  font-size: 12px;
}

.login-signals span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.signal-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}

.signal-dot.cyan { background: var(--app-cyan); }
.signal-dot.violet { background: var(--app-primary); }
.signal-dot.coral { background: var(--app-coral); }

.login-card {
  width: 360px;
  border: 0;
  box-shadow: none;
}

.login-card-head {
  display: flex;
  flex-direction: column;
  gap: 5px;
  margin-bottom: 24px;
}

.login-card-head span {
  font-size: 22px;
  font-weight: 700;
}

.login-card-head small {
  color: var(--app-text-secondary);
  font-size: 13px;
}

.login-button {
  width: 100%;
  height: 42px;
}

@keyframes login-enter {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

@media (max-width: 700px) {
  .login-page {
    min-height: 100vh;
    height: auto;
    padding: 16px;
  }

  .login-shell {
    grid-template-columns: 1fr;
    gap: 24px;
    padding: 28px 24px;
  }

  .login-card {
    width: 100%;
  }

  .login-intro h1 {
    font-size: 26px;
  }
}
</style>
