<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">账号设置</h2>
        <p class="page-subtitle">更新管理员用户名和登录密码。</p>
      </div>
      <div class="page-header-mark"><el-icon><Lock /></el-icon><span>IDENTITY</span></div>
    </div>
    <div class="surface-card profile-card">
    <el-form label-width="120px">
      <el-form-item label="新用户名">
        <el-input v-model="newUsername" placeholder="留空表示不修改用户名" />
      </el-form-item>
      <el-form-item label="当前密码">
        <el-input v-model="oldPassword" type="password" show-password />
      </el-form-item>
      <el-form-item label="新密码">
        <el-input v-model="newPassword" type="password" show-password />
      </el-form-item>
      <el-form-item label="确认新密码">
        <el-input v-model="confirmPassword" type="password" show-password />
      </el-form-item>
      <el-form-item>
      <el-button type="primary" :loading="saving" @click="submit">保存账号设置</el-button>
      </el-form-item>
    </el-form>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { updateAdminProfile } from '../api'
import { useAuthStore } from '../stores/auth'

const authStore = useAuthStore()
const saving = ref(false)
const oldPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const newUsername = ref(authStore.username)

async function submit() {
  if (!newUsername.value.trim() && !newPassword.value) {
    ElMessage.warning('请填写新的用户名或密码')
    return
  }
  if (newPassword.value && newPassword.value.length < 8) {
    ElMessage.warning('新密码至少 8 位')
    return
  }
  if (newPassword.value !== confirmPassword.value) {
    ElMessage.warning('两次输入的新密码不一致')
    return
  }
  saving.value = true
  try {
    await updateAdminProfile({
      current_password: oldPassword.value,
      username: newUsername.value.trim() || null,
      new_password: newPassword.value || null
    })
    await ElMessageBox.alert('密码已修改，请重新登录', '成功', {
      confirmButtonText: '重新登录'
    })
    authStore.logout()
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.profile-card {
  max-width: 420px;
}
</style>
