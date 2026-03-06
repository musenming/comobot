<script setup lang="ts">
import { NButton } from 'naive-ui'

const props = defineProps<{
  provider: {
    provider: string
    key_count?: number
    [key: string]: any
  }
}>()

const emit = defineEmits<{
  (e: 'edit'): void
  (e: 'test'): void
  (e: 'remove'): void
}>()

const nameMap: Record<string, string> = {
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  deepseek: 'DeepSeek',
  dashscope: 'DashScope',
  gemini: 'Gemini',
  moonshot: 'Moonshot',
  zhipu: 'Zhipu AI',
  minimax: 'MiniMax',
  ollama: 'Ollama',
}
</script>

<template>
  <div class="provider-card">
    <div class="card-header">
      <div class="provider-icon" aria-hidden="true">◆</div>
      <div class="provider-info">
        <span class="provider-name">{{ nameMap[provider.provider] || provider.provider }}</span>
        <span class="provider-meta">{{ provider.key_count || 0 }} key(s)</span>
      </div>
      <StatusBadge :status="(provider.key_count || 0) > 0 ? 'online' : 'offline'" />
    </div>

    <div class="card-actions">
      <NButton size="small" quaternary @click="emit('edit')">Edit</NButton>
      <NButton size="small" quaternary @click="emit('test')">Test</NButton>
      <NButton size="small" quaternary type="error" @click="emit('remove')">Remove</NButton>
    </div>
  </div>
</template>

<style scoped>
.provider-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: var(--space-6);
  transition: border-color 200ms var(--ease-default), box-shadow 200ms var(--ease-default);
}
.provider-card:hover {
  border-color: var(--text-muted);
  box-shadow: var(--shadow-sm);
}
.card-header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}
.provider-icon {
  font-size: 24px;
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-muted);
  border-radius: var(--radius-md);
}
.provider-info {
  flex: 1;
  display: flex;
  flex-direction: column;
}
.provider-name {
  font-size: var(--text-md);
  font-weight: 500;
  color: var(--text-primary);
}
.provider-meta {
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
