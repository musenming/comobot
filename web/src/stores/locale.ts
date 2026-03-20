import { defineStore } from 'pinia'
import { useStorage } from '@vueuse/core'
import type { Locale } from '../locales'

export const useLocaleStore = defineStore('locale', () => {
  const locale = useStorage<Locale>('comobot-locale', 'en')

  function setLocale(val: Locale) {
    locale.value = val
  }

  function toggle() {
    locale.value = locale.value === 'en' ? 'zh' : 'en'
  }

  return { locale, setLocale, toggle }
})
