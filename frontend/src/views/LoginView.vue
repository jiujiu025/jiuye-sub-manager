<template>
  <div class="login-page">
    <el-card class="login-card">
      <h2 class="login-title">订阅管理系统</h2>
      <el-form label-position="top" @submit.prevent="submit">
        <el-form-item label="用户名">
          <el-input v-model="username" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="password"
            type="password"
            show-password
            placeholder="请输入密码"
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
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const authStore = useAuthStore()
const username = ref('admin')
const password = ref('')
const loading = ref(false)

async function submit() {
  if (!username.value || !password.value) {
    return
  }
  loading.value = true
  try {
    await authStore.login(username.value, password.value)
    router.push('/')
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
  background: #f3f4f6;
}

.login-card {
  width: 360px;
}

.login-title {
  margin-top: 0;
  text-align: center;
}

.login-button {
  width: 100%;
}
</style>
