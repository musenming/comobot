<script setup lang="ts">
import { useI18n } from '../composables/useI18n'

const { t } = useI18n()

defineProps<{
  icon?: string
  title?: string
  description?: string
}>()
</script>

<template>
  <div class="empty-state">
    <div class="empty-icon" aria-hidden="true">{{ icon || '📭' }}</div>
    <div class="empty-title">{{ title || t('common.noData') }}</div>
    <div v-if="description" class="empty-desc">{{ description }}</div>
    <div v-if="$slots.default" class="empty-action">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--space-16) var(--space-6);
  text-align: center;
}
.empty-icon {
  font-size: 48px;
  margin-bottom: var(--space-4);
  opacity: 0.5;
}
.empty-title {
  font-size: var(--text-md);
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: var(--space-2);
}
.empty-desc {
  font-size: var(--text-sm);
  color: var(--text-muted);
  max-width: 320px;
}
.empty-action {
  margin-top: var(--space-6);
}
</style>
