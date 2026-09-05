import { defineStore } from 'pinia'
import { login as loginApi } from '../api'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('admin_token') || '',
    username: localStorage.getItem('admin_username') || ''
  }),
  actions: {
    async login(username, password) {
      const { data } = await loginApi({ username, password })
      this.token = data.access_token
      this.username = username
      localStorage.setItem('admin_token', data.access_token)
      localStorage.setItem('admin_username', username)
    },
    logout() {
      this.token = ''
      this.username = ''
      localStorage.removeItem('admin_token')
      localStorage.removeItem('admin_username')
      window.location.href = '/login'
    }
  }
})
