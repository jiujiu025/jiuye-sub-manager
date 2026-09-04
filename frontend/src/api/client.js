import axios from 'axios'
import { ElMessage } from 'element-plus'

const client = axios.create({
  baseURL: '/api',
  timeout: 30000
})

client.interceptors.request.use((config) => {
  const token = localStorage.getItem('admin_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

client.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status
    if (status === 401 && localStorage.getItem('admin_token')) {
      localStorage.removeItem('admin_token')
      localStorage.removeItem('admin_username')
      window.location.href = '/login'
    }
    const data = error.response?.data
    if (status === 422 && data?.errors?.length) {
      const first = data.errors[0]
      const field = (first.loc || []).slice(1).join('.') || '参数'
      ElMessage.error(`字段 ${field} 校验失败：${first.msg}`)
      return Promise.reject(error)
    }
    const detail = data?.detail || '请求失败'
    ElMessage.error(typeof detail === 'string' ? detail : '请求失败')
    return Promise.reject(error)
  }
)

export default client
