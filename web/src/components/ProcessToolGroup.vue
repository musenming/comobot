<script setup lang="ts">
import { ref } from 'vue'
import ProcessToolCall from './ProcessToolCall.vue'
import { useI18n } from '../composables/useI18n'

const { t } = useI18n()

const props = defineProps<{
  items: Array<{
    tool: string
    args?: Record<string, any>
    status: string
    result_summary?: string
    duration_ms?: number
  }>
}>()

const expanded = ref(false)

function summaryText(): string {
  const count = props.items.length
  const doneCount = props.items.filter(i => i.status === 'done').length
  const failedCount = props.items.filter(i => i.status === 'failed').length
  let text = t('process.tool_group').replace('{count}', String(count))
  if (failedCount > 0) text += ` (${failedCount} ${t('process.status.failed').toLowerCase()})`
  else if (doneCount === count) text += ` - ${t('process.status.done')}`
  return text
}
</script>

<template>
  <div class="ptg">
    <button class="ptg-header" @click="expanded = !expanded">
      <span class="ptg-chevron">{{ expanded ? '\u25BE' : '\u25B8' }}</span>
      <span class="ptg-icon" aria-hidden="true">&#9881;</span>
      <span class="ptg-label">{{ summaryText() }}</span>
      <span class="ptg-spacer" />
      <span class="ptg-hint">{{ expanded ? t('process.collapse') : t('process.expand') }}</span>
    </button>
    <Transition name="ptg-slide">
      <div v-if="expanded" class="ptg-body">
        <ProcessToolCall
          v-for="(item, idx) in items"
          :key="idx"
          :data="item"
        />
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.ptg {
  border-radius: var(--radius-sm);
  overflow: hidden;
}
.ptg-header {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 6px 10px;
  background: none;
  border: none;
  font-size: var(--text-xs);
  color: var(--text-secondary);
  cursor: pointer;
  text-align: left;
  font-family: inherit;
}
.ptg-header:hover {
  background: rgba(0, 0, 0, 0.02);
  transform: none;
}
.ptg-chevron {
  font-size: 10px;
  color: var(--text-muted);
  transition: transform 200ms var(--ease-default);
  width: 10px;
  text-align: center;
}
.ptg-icon {
  font-size: 12px;
  color: var(--text-muted);
}
.ptg-label {
  font-weight: 500;
}
.ptg-spacer { flex: 1; }
.ptg-hint {
  font-size: 10px;
  color: var(--text-muted);
  opacity: 0;
  transition: opacity 150ms;
}
.ptg-header:hover .ptg-hint { opacity: 1; }
.ptg-body {
  border-top: 1px solid var(--border);
}
.ptg-slide-enter-active,
.ptg-slide-leave-active {
  transition: all 200ms var(--ease-default);
  overflow: hidden;
}
.ptg-slide-enter-from,
.ptg-slide-leave-to {
  opacity: 0;
  max-height: 0;
}
.ptg-slide-enter-to,
.ptg-slide-leave-from {
  opacity: 1;
  max-height: 600px;
}
</style>
