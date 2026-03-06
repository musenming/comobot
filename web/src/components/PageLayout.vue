<script setup lang="ts">
import { computed, watch, ref } from 'vue'
import { useBreakpoints } from '@vueuse/core'
import AppSidebar from './AppSidebar.vue'
import { useWebSocket } from '../composables/useWebSocket'

defineProps<{
  title: string
  description?: string
}>()

const { data: wsStatus, connected: wsConnected } = useWebSocket('/ws/status')

const agentStatus = ref<'online' | 'offline' | 'error' | 'paused'>('offline')

watch(wsConnected, (c) => {
  if (!c) agentStatus.value = 'offline'
})

watch(wsStatus, (s) => {
  if (s?.type === 'status' && s.agent) {
    agentStatus.value = s.agent
  }
})

const breakpoints = useBreakpoints({ md: 768, lg: 1024 })
const isMobile = breakpoints.smaller('md')
const isTablet = breakpoints.between('md', 'lg')

const contentStyle = computed(() => {
  if (isMobile.value) return { marginLeft: '0', padding: '56px 16px 16px' }
  if (isTablet.value) return { marginLeft: 'var(--sidebar-collapsed)', padding: '24px' }
  return { marginLeft: 'var(--sidebar-width)', padding: '40px' }
})
</script>

<template>
  <div class="layout">
    <AppSidebar :agent-status="agentStatus" />
    <main class="content" :style="contentStyle">
      <div class="page-header" v-if="title">
        <div class="page-header-left">
          <h1 class="page-title">{{ title }}</h1>
          <p v-if="description" class="page-desc">{{ description }}</p>
        </div>
        <div v-if="$slots.actions" class="page-header-right">
          <slot name="actions" />
        </div>
      </div>
      <slot />
    </main>
  </div>
</template>

<style scoped>
.layout {
  min-height: 100vh;
}
.content {
  min-height: 100vh;
  transition: margin-left 200ms var(--ease-default), padding 200ms var(--ease-default);
}
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: var(--space-8);
}
.page-title {
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}
.page-desc {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 4px 0 0;
}
.page-header-right {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}
</style>
