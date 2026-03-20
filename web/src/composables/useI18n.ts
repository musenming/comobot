import { computed } from 'vue'
import { useLocaleStore } from '../stores/locale'
import { messages } from '../locales'

/**
 * Lightweight i18n composable.
 * Usage: const { t } = useI18n()
 *        t('sidebar.chat')  => 'Chat' or '聊天'
 */
export function useI18n() {
  const store = useLocaleStore()

  const current = computed(() => messages[store.locale])

  function t(key: string, params?: Record<string, string>): string {
    const parts = key.split('.')
    let val: any = current.value
    for (const p of parts) {
      val = val?.[p]
    }
    if (typeof val !== 'string') return key
    if (params) {
      return val.replace(/\{(\w+)\}/g, (_, k) => params[k] ?? `{${k}}`)
    }
    return val
  }

  return { t, locale: computed(() => store.locale) }
}
