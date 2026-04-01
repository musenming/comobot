<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from '../composables/useI18n'

const { t } = useI18n()

const props = defineProps<{
  data: {
    memories: Array<{
      id: string
      content: string
      score?: number
    }>
    count: number
  }
}>()

const expanded = ref(false)
</script>

<template>
  <div class="pmr">
    <button class="pmr-header" @click="expanded = !expanded">
      <span class="pmr-icon" aria-hidden="true">&#9679;</span>
      <span class="pmr-label">
        {{ t('process.memory_recall').replace('{count}', String(data.count || data.memories.length)) }}
      </span>
      <span class="pmr-spacer" />
      <span class="pmr-toggle">{{ expanded ? '\u25BE' : '\u25B8' }}</span>
    </button>
    <Transition name="pmr-slide">
      <div v-if="expanded" class="pmr-body">
        <div
          v-for="mem in data.memories"
          :key="mem.id"
          class="pmr-item"
        >
          <span class="pmr-item-id">{{ mem.id }}</span>
          <span class="pmr-item-content">{{ mem.content }}</span>
          <span v-if="mem.score != null" class="pmr-item-score">{{ (mem.score * 100).toFixed(0) }}%</span>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.pmr {
  border-radius: var(--radius-sm);
  overflow: hidden;
}
.pmr-header {
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
.pmr-header:hover {
  background: rgba(0, 0, 0, 0.02);
  transform: none;
}
.pmr-icon {
  color: #eab308;
  font-size: 8px;
}
.pmr-label {
  font-weight: 500;
}
.pmr-spacer { flex: 1; }
.pmr-toggle {
  font-size: 10px;
  color: var(--text-muted);
}
.pmr-body {
  padding: 0 10px 8px;
}
.pmr-item {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 4px 0;
  font-size: var(--text-xs);
  border-bottom: 1px solid var(--border);
}
.pmr-item:last-child { border-bottom: none; }
.pmr-item-id {
  font-family: 'SF Mono', monospace;
  font-size: 9px;
  color: var(--text-muted);
  flex-shrink: 0;
}
.pmr-item-content {
  flex: 1;
  color: var(--text-primary);
  line-height: 1.5;
}
.pmr-item-score {
  font-family: 'SF Mono', monospace;
  font-size: 9px;
  color: var(--accent-green);
  background: rgba(34, 197, 94, 0.08);
  padding: 1px 5px;
  border-radius: 999px;
  flex-shrink: 0;
}
.pmr-slide-enter-active,
.pmr-slide-leave-active {
  transition: all 200ms var(--ease-default);
  overflow: hidden;
}
.pmr-slide-enter-from,
.pmr-slide-leave-to {
  opacity: 0;
  max-height: 0;
}
.pmr-slide-enter-to,
.pmr-slide-leave-from {
  opacity: 1;
  max-height: 400px;
}
</style>
