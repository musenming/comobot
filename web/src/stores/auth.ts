import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '../api/client'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || '')
  const username = ref('')

  const isAuthenticated = computed(() => !!token.value)

  async function login(user: string, password: string) {
    const { data } = await api.post('/auth/login', { username: user, password })
    token.value = data.access_token
    username.value = user
    localStorage.setItem('token', data.access_token)
  }

  function logout() {
    token.value = ''
    username.value = ''
    localStorage.removeItem('token')
  }

  return { token, username, isAuthenticated, login, logout }
})
