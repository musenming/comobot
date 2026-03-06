<script setup lang="ts">
defineProps<{
  lines?: number
  height?: string
}>()
</script>

<template>
  <div class="skeleton-card" :style="height ? { height } : undefined">
    <div class="skeleton-line short" />
    <div class="skeleton-line" v-for="i in (lines || 2)" :key="i" :class="{ short: i === (lines || 2) }" />
  </div>
</template>

<style scoped>
.skeleton-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: var(--space-6);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.skeleton-line {
  height: 14px;
  border-radius: var(--radius-sm);
  background: linear-gradient(
    90deg,
    var(--bg-muted) 25%,
    rgba(255, 255, 255, 0.04) 50%,
    var(--bg-muted) 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite linear;
}
.skeleton-line.short {
  width: 60%;
}
</style>
