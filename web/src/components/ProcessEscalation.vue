<script setup lang="ts">
import { useI18n } from '../composables/useI18n'

const { t } = useI18n()

const props = defineProps<{
  data: {
    from: string
    to: string
    reason: string
  }
}>()
</script>

<template>
  <div class="pesc">
    <span class="pesc-icon" aria-hidden="true">&#9889;</span>
    <span class="pesc-label">{{ t('process.escalation') }}</span>
    <span class="pesc-flow">
      <span class="pesc-from">{{ data.from }}</span>
      <span class="pesc-arrow">&rarr;</span>
      <span class="pesc-to">{{ data.to }}</span>
    </span>
    <span class="pesc-reason">&middot; {{ data.reason }}</span>
  </div>
</template>

<style scoped>
.pesc {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  font-size: var(--text-xs);
  color: var(--text-secondary);
  flex-wrap: wrap;
}
.pesc-icon {
  font-size: 12px;
  color: var(--accent-yellow);
}
.pesc-label {
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  font-size: 10px;
}
.pesc-flow {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.pesc-from,
.pesc-to {
  font-family: 'SF Mono', monospace;
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 999px;
  background: var(--bg-subtle);
}
.pesc-to {
  background: rgba(234, 179, 8, 0.1);
  color: var(--accent-yellow);
  font-weight: 500;
}
.pesc-arrow {
  color: var(--text-muted);
  font-size: 11px;
}
.pesc-reason {
  color: var(--text-muted);
  font-size: 10px;
}
</style>
