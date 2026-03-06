<script setup lang="ts">
defineProps<{
  icon: string
  label: string
  value: number | string
  trend?: number
}>()
</script>

<template>
  <div class="stat-card">
    <div class="stat-header">
      <span class="stat-icon" aria-hidden="true">{{ icon }}</span>
      <span class="stat-label">{{ label }}</span>
    </div>
    <div class="stat-value">{{ value }}</div>
    <div v-if="trend !== undefined" class="stat-trend" :class="{ positive: trend >= 0, negative: trend < 0 }">
      <span>{{ trend >= 0 ? '↑' : '↓' }} {{ Math.abs(trend) }}%</span>
      <span class="trend-label">vs last 7 days</span>
    </div>
  </div>
</template>

<style scoped>
.stat-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: var(--space-6);
  transition: border-color 200ms var(--ease-default), box-shadow 200ms var(--ease-default);
}
.stat-card:hover {
  border-color: var(--text-muted);
  box-shadow: var(--shadow-sm);
}
.stat-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
}
.stat-icon {
  font-size: var(--text-md);
  opacity: 0.6;
}
.stat-label {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  font-weight: 500;
}
.stat-value {
  font-size: var(--text-xl);
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.3;
}
.stat-trend {
  margin-top: var(--space-2);
  font-size: var(--text-xs);
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.stat-trend.positive {
  color: var(--accent-green);
}
.stat-trend.negative {
  color: var(--accent-red);
}
.trend-label {
  color: var(--text-muted);
}
</style>
