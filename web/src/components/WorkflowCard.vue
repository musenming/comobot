<script setup lang="ts">
import { NButton, NSwitch, NTag } from 'naive-ui'

const props = defineProps<{
  workflow: {
    id: number
    name: string
    description?: string
    template?: string
    enabled: boolean
    total_runs?: number
    last_run_at?: string
  }
}>()

const emit = defineEmits<{
  (e: 'edit'): void
  (e: 'toggle'): void
  (e: 'duplicate'): void
  (e: 'run'): void
  (e: 'delete'): void
}>()
</script>

<template>
  <div class="workflow-card">
    <div class="card-header">
      <span class="wf-icon" aria-hidden="true">⚡</span>
      <div class="wf-info">
        <span class="wf-name">{{ workflow.name }}</span>
        <p v-if="workflow.description" class="wf-desc">{{ workflow.description }}</p>
      </div>
      <NSwitch
        :value="workflow.enabled"
        size="small"
        @update:value="emit('toggle')"
        :aria-label="workflow.enabled ? 'Disable workflow' : 'Enable workflow'"
      />
    </div>

    <div class="card-meta">
      <NTag v-if="workflow.template" size="small" :bordered="false">{{ workflow.template }}</NTag>
      <NTag v-else size="small" :bordered="false">Custom</NTag>
      <span class="meta-text">{{ workflow.total_runs || 0 }} runs</span>
      <span v-if="workflow.last_run_at" class="meta-text">Last: {{ workflow.last_run_at }}</span>
    </div>

    <div class="card-actions">
      <NButton size="small" quaternary @click="emit('edit')">Edit</NButton>
      <NButton size="small" quaternary @click="emit('duplicate')">Duplicate</NButton>
      <NButton size="small" quaternary @click="emit('run')">Run Now</NButton>
      <NButton size="small" quaternary type="error" @click="emit('delete')">Delete</NButton>
    </div>
  </div>
</template>

<style scoped>
.workflow-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: var(--space-6);
  transition: border-color 200ms var(--ease-default), box-shadow 200ms var(--ease-default);
}
.workflow-card:hover {
  border-color: var(--text-muted);
  box-shadow: var(--shadow-sm);
}
.card-header {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}
.wf-icon {
  font-size: 20px;
  flex-shrink: 0;
  margin-top: 2px;
}
.wf-info {
  flex: 1;
  min-width: 0;
}
.wf-name {
  font-size: var(--text-md);
  font-weight: 500;
  color: var(--text-primary);
}
.wf-desc {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 4px 0 0;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.card-meta {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
  flex-wrap: wrap;
}
.meta-text {
  font-size: var(--text-xs);
  color: var(--text-muted);
}
.card-actions {
  display: flex;
  gap: var(--space-2);
  border-top: 1px solid var(--border);
  padding-top: var(--space-3);
}
</style>
