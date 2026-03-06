<script setup lang="ts">
defineProps<{
  status: 'online' | 'offline' | 'error' | 'paused'
}>()

const colorMap: Record<string, string> = {
  online: 'var(--accent-green)',
  offline: 'var(--text-muted)',
  error: 'var(--accent-red)',
  paused: 'var(--accent-yellow)',
}

const labelMap: Record<string, string> = {
  online: 'Online',
  offline: 'Offline',
  error: 'Error',
  paused: 'Paused',
}
</script>

<template>
  <span class="status-badge">
    <span
      class="status-dot"
      :class="{ breathing: status === 'online' }"
      :style="{ background: colorMap[status] }"
      aria-hidden="true"
    />
    <span class="status-text">{{ labelMap[status] }}</span>
  </span>
</template>

<style scoped>
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.status-dot.breathing {
  animation: breathe 2s ease-in-out infinite;
}
.status-text {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}
</style>
