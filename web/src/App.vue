<script setup lang="ts">
import { watch } from 'vue'
import { NConfigProvider, NMessageProvider, darkTheme } from 'naive-ui'
import { useThemeStore } from './stores/theme'
import { darkThemeOverrides, lightThemeOverrides } from './theme'

const themeStore = useThemeStore()

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
