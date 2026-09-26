import { defineStore } from 'pinia'
import { loginUser as loginUserApi } from '../api'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('admin_token') || '',
    username: localStorage.getItem('admin_username') || '',
    role: localStorage.getItem('admin_role') || ''
  }),
  actions: {
    async login(username, password) {
      const { data } = await loginUserApi({ username, password })
      this.token = data.access_token
      this.username = username
      this.role = data.role
      localStorage.setItem('admin_token', data.access_token)
      localStorage.setItem('admin_username', username)
      localStorage.setItem('admin_role', data.role)
    },
    logout() {
      this.token = ''
      this.username = ''
      this.role = ''
      localStorage.removeItem('admin_token')
      localStorage.removeItem('admin_username')
      localStorage.removeItem('admin_role')
      window.location.href = '/login'
    }
  }
})
