<script setup lang="ts">
import { useI18n } from '../composables/useI18n'

const { t } = useI18n()

const props = defineProps<{
  data: {
    satisfied: boolean
    summary: string
    revisions?: string[]
  }
}>()
</script>

<template>
  <div class="prf" :class="{ 'prf--satisfied': data.satisfied, 'prf--revision': !data.satisfied }">
    <span class="prf-icon" aria-hidden="true">
      {{ data.satisfied ? '\u2713' : '\u26A0' }}
    </span>
    <div class="prf-body">
      <span class="prf-label">{{ t('process.reflection') }}</span>
      <span class="prf-summary">{{ data.summary }}</span>
      <div v-if="data.revisions && data.revisions.length > 0" class="prf-revisions">
        <span class="prf-rev-label">Revisions:</span>
        <span v-for="rev in data.revisions" :key="rev" class="prf-rev-id">{{ rev }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.prf {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 12px;
}
.prf-icon {
  font-size: 14px;
  flex-shrink: 0;
  width: 18px;
  text-align: center;
  margin-top: 1px;
}
.prf--satisfied .prf-icon { color: var(--accent-green); }
.prf--revision .prf-icon { color: var(--accent-yellow); }
.prf-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.prf-label {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-muted);
}
.prf-summary {
  font-size: var(--text-xs);
  color: var(--text-primary);
  line-height: 1.5;
}
.prf-revisions {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 2px;
  flex-wrap: wrap;
}
.prf-rev-label {
  font-size: 10px;
  color: var(--text-muted);
}
.prf-rev-id {
  font-family: 'SF Mono', monospace;
  font-size: 10px;
  color: var(--accent-yellow);
  background: rgba(234, 179, 8, 0.08);
  padding: 1px 6px;
  border-radius: 999px;
}
</style>
