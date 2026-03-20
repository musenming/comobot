<script setup lang="ts">
import { watch, computed } from 'vue'
import { NConfigProvider, NMessageProvider, darkTheme, zhCN, dateZhCN, enUS, dateEnUS } from 'naive-ui'
import { useThemeStore } from './stores/theme'
import { useLocaleStore } from './stores/locale'
import { darkThemeOverrides, lightThemeOverrides } from './theme'

const themeStore = useThemeStore()
const localeStore = useLocaleStore()

const naiveLocale = computed(() => (localeStore.locale === 'zh' ? zhCN : enUS))
const naiveDateLocale = computed(() => (localeStore.locale === 'zh' ? dateZhCN : dateEnUS))

watch(
  () => themeStore.isDark,
  (dark) => {
    document.documentElement.classList.toggle('dark', dark)
  },
  { immediate: true }
)
</script>

<template>
  <NConfigProvider
    :theme="themeStore.isDark ? darkTheme : null"
    :theme-overrides="themeStore.isDark ? darkThemeOverrides : lightThemeOverrides"
    :locale="naiveLocale"
    :date-locale="naiveDateLocale"
  >
    <NMessageProvider>
      <router-view v-slot="{ Component }">
        <Transition name="fade" mode="out-in">
          <component :is="Component" />
        </Transition>
      </router-view>
    </NMessageProvider>
  </NConfigProvider>
</template>
