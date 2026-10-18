<template>
  <div class="page">
    <div class="page-header page-toolbar">
      <div>
        <h2 class="page-title">{{ managerOnly ? '客户经理' : '用户管理' }}</h2>
        <p class="page-subtitle">{{ managerOnly ? '创建、停用与管理销售经理账号。' : '创建用户并分配只读订阅权限。' }}</p>
      </div>
      <div class="page-actions">
        <div class="page-header-mark"><el-icon><User /></el-icon><span>MEMBERS</span></div>
        <el-button type="primary" @click="openCreate"><el-icon><Plus /></el-icon>{{ managerOnly ? '新建客户经理' : '创建用户' }}</el-button>
      </div>
    </div>

    <div v-loading="loading" class="surface-card">
      <el-table :data="users" row-key="id">
        <el-table-column prop="username" label="用户名" min-width="180" />
        <el-table-column prop="role" label="角色" width="100">
          <template #default="{ row }">{{ roleLabel(row.role) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? '启用' : '停用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180">
          <template #default="{ row }">
            <el-button v-if="row.role !== 'admin'" link type="primary" @click="openEdit(row)">编辑</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑用户' : '创建用户'" width="420px" append-to-body>
      <el-form label-width="90px">
        <el-form-item label="用户名">
          <el-input v-model="form.username" autocomplete="off" />
        </el-form-item>
        <el-form-item v-if="!editing && !managerOnly" label="角色">
          <el-select v-model="form.role" style="width: 100%">
            <el-option label="普通用户" value="user" />
          </el-select>
        </el-form-item>
        <el-form-item v-else-if="!editing && managerOnly" label="角色"><el-tag type="success">客户经理</el-tag></el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" show-password :placeholder="editing ? '留空表示不修改' : '至少 8 位'" />
        </el-form-item>
        <el-form-item v-if="editing" label="状态">
          <el-switch v-model="form.is_active" active-text="启用" inactive-text="停用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

  <script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { createUser, listUsers, updateUser } from '../api'

const users = ref([])
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const editing = ref(null)
const form = reactive({ username: '', password: '', is_active: true, role: 'user' })
const route = useRoute()
const managerOnly = computed(() => route.path === '/managers')

function resetForm() {
  Object.assign(form, { username: '', password: '', is_active: true, role: managerOnly.value ? 'manager' : 'user' })
}

function openCreate() {
  editing.value = null
  resetForm()
  dialogVisible.value = true
}

function openEdit(row) {
  editing.value = row
  Object.assign(form, { username: row.username, password: '', is_active: row.is_active, role: row.role })
  dialogVisible.value = true
}

async function load() {
  loading.value = true
  try {
    const { data } = await listUsers(managerOnly.value ? { role: 'manager' } : undefined)
    users.value = data
  } finally {
    loading.value = false
  }
}

async function save() {
  if (!form.username.trim()) {
    ElMessage.warning('请输入用户名')
    return
  }
  if (!editing.value && form.password.length < 8) {
    ElMessage.warning('密码至少 8 位')
    return
  }
  saving.value = true
  try {
    const payload = { username: form.username.trim(), role: form.role }
    if (form.password) payload.password = form.password
    if (editing.value) {
      payload.is_active = form.is_active
      await updateUser(editing.value.id, payload)
    } else {
      payload.password = form.password
      await createUser(payload)
    }
    dialogVisible.value = false
    ElMessage.success(editing.value ? '用户已更新' : '用户已创建')
    await load()
  } finally {
    saving.value = false
  }
}

onMounted(load)
watch(() => route.path, () => { resetForm(); load() })

function roleLabel(role) {
  return role === 'admin' ? '管理员' : role === 'manager' ? '经理' : '普通用户'
}
</script>

<style scoped>
.page-toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.section-title {
  margin: 0;
  font-size: 20px;
}

.section-hint {
  margin: 6px 0 0;
  color: var(--app-text-secondary);
  font-size: 13px;
}
</style>
