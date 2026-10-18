<template>
  <div class="manager-login-page">
    <div class="manager-login-shell">
      <div class="manager-login-brand">
        <div class="manager-mark"><el-icon :size="24"><Briefcase /></el-icon></div>
        <span>JIUYE CLOUD / PARTNER DESK</span>
        <h1>经理工作台</h1>
        <p>管理你的客户、销售订阅和到期提醒。</p>
        <div class="manager-points">
          <span><el-icon><UserFilled /></el-icon>客户归属清晰</span>
          <span><el-icon><Tickets /></el-icon>订阅状态集中</span>
          <span><el-icon><Bell /></el-icon>到期及时提醒</span>
        </div>
      </div>
      <el-card class="manager-login-card">
        <div class="login-card-head">
          <span>经理登录</span>
          <small>使用管理员创建的经理账号</small>
        </div>
        <el-form label-position="top" @submit.prevent="submit">
          <el-form-item label="账号">
            <el-input v-model="username" autocomplete="username" placeholder="请输入经理账号" />
          </el-form-item>
          <el-form-item label="密码">
            <el-input v-model="password" type="password" show-password autocomplete="current-password" placeholder="请输入密码" @keyup.enter="submit" />
          </el-form-item>
          <el-button type="primary" class="login-button" :loading="loading" @click="submit">进入工作台</el-button>
        </el-form>
        <button class="back-link" type="button" @click="router.push('/login')">返回系统登录</button>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const authStore = useAuthStore()
const username = ref('')
const password = ref('')
const loading = ref(false)

async function submit() {
  if (!username.value.trim() || !password.value) {
    ElMessage.warning('请输入账号和密码')
    return
  }
  loading.value = true
  try {
    await authStore.login(username.value.trim(), password.value, 'manager')
    router.push('/manager')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.manager-login-page { min-height: 100vh; display: grid; place-items: center; padding: 24px; background: linear-gradient(135deg, #10172a 0%, #17243d 58%, #0f766e 130%); }
.manager-login-shell { width: min(900px, 100%); display: grid; grid-template-columns: 1fr 360px; gap: 54px; align-items: center; padding: 52px; border: 1px solid rgba(255,255,255,.14); border-radius: 24px; background: rgba(255,255,255,.08); box-shadow: 0 28px 80px rgba(0,0,0,.28); }
.manager-login-brand { color: #fff; }
.manager-mark { display: grid; place-items: center; width: 50px; height: 50px; margin-bottom: 24px; border-radius: 15px; color: #102036; background: #79e4d6; }
.manager-login-brand > span { color: #8ce8dd; font-size: 11px; font-weight: 800; letter-spacing: .08em; }
.manager-login-brand h1 { margin: 12px 0 10px; font-size: 34px; }
.manager-login-brand p { margin: 0; color: #b9c8dc; line-height: 1.7; }
.manager-points { display: grid; gap: 12px; margin-top: 30px; color: #dce7f4; font-size: 13px; }
.manager-points span { display: flex; align-items: center; gap: 8px; }
.manager-points .el-icon { color: #79e4d6; }
.manager-login-card { border: 0; }
.login-card-head { display: flex; flex-direction: column; gap: 6px; margin-bottom: 24px; }
.login-card-head span { font-size: 22px; font-weight: 700; }
.login-card-head small { color: var(--app-text-secondary); }
.login-button { width: 100%; height: 42px; }
.back-link { display: block; margin: 18px auto 0; border: 0; background: transparent; color: var(--app-primary); cursor: pointer; font-size: 13px; }
@media (max-width: 700px) { .manager-login-shell { grid-template-columns: 1fr; gap: 28px; padding: 28px 24px; } .manager-login-brand h1 { font-size: 28px; } }
</style>
