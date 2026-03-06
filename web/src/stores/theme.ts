import { defineStore } from 'pinia'
import { computed } from 'vue'
import { usePreferredDark, useStorage } from '@vueuse/core'

export const useThemeStore = defineStore('theme', () => {
  const prefersDark = usePreferredDark()
  const userPref = useStorage<'dark' | 'light' | 'system'>('comobot-theme', 'system')

  const isDark = computed(() => {
    if (userPref.value === 'system') return prefersDark.value
    return userPref.value === 'dark'
  })

  function toggle() {
    userPref.value = isDark.value ? 'light' : 'dark'
  }

  function setTheme(value: 'dark' | 'light' | 'system') {
    userPref.value = value
  }

  return { isDark, userPref, toggle, setTheme }
})
