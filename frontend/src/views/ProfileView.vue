<template>
  <div class="page">
    <div class="surface-card profile-card">
    <el-form label-width="120px">
      <el-form-item label="旧密码">
        <el-input v-model="oldPassword" type="password" show-password />
      </el-form-item>
      <el-form-item label="新密码">
        <el-input v-model="newPassword" type="password" show-password />
      </el-form-item>
      <el-form-item label="确认新密码">
        <el-input v-model="confirmPassword" type="password" show-password />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :loading="saving" @click="submit">修改密码</el-button>
      </el-form-item>
    </el-form>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { changePassword } from '../api'
import { useAuthStore } from '../stores/auth'

const authStore = useAuthStore()
const saving = ref(false)
const oldPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')

async function submit() {
  if (newPassword.value.length < 8) {
    ElMessage.warning('新密码至少 8 位')
    return
  }
  if (newPassword.value !== confirmPassword.value) {
    ElMessage.warning('两次输入的新密码不一致')
    return
  }
  saving.value = true
  try {
    await changePassword({
      old_password: oldPassword.value,
      new_password: newPassword.value
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
