<script setup lang="ts">
import { ref } from 'vue'
import MarkdownRenderer from './MarkdownRenderer.vue'
import { useI18n } from '../composables/useI18n'

const { t } = useI18n()

const props = defineProps<{
  role: string
  content: string
  toolCalls?: string
  createdAt?: string
}>()

const toolExpanded = ref(false)
</script>

<template>
  <div class="bubble-row" :class="{ 'user-row': role === 'user', 'assistant-row': role === 'assistant', 'tool-row': role === 'tool' }">
    <div class="bubble" :class="{ user: role === 'user', assistant: role === 'assistant', tool: role === 'tool' }">
      <template v-if="role === 'tool'">
        <button class="tool-toggle" @click="toolExpanded = !toolExpanded">
          {{ toolExpanded ? '▼' : '▶' }} {{ t('chat.toolCall') }}
        </button>
        <pre v-if="toolExpanded" class="tool-content">{{ content }}</pre>
      </template>
      <template v-else-if="role === 'assistant'">
        <MarkdownRenderer :content="content" />
      </template>
      <template v-else>
        <div class="bubble-text">{{ content }}</div>
      </template>
      <div v-if="createdAt" class="bubble-time">{{ createdAt }}</div>
    </div>
  </div>
</template>

<style scoped>
.bubble-row {
  display: flex;
  margin-bottom: var(--space-3);
}
.user-row {
  justify-content: flex-end;
}
.assistant-row,
.tool-row {
  justify-content: flex-start;
}
.bubble {
  max-width: 75%;
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-lg);
  font-size: var(--text-base);
  line-height: 1.6;
}
.bubble.user {
  background: var(--surface);
  border: 1px solid var(--border);
  border-top-right-radius: var(--radius-sm);
  color: var(--text-primary);
}
.bubble.assistant {
  background: var(--bg-muted);
  border-top-left-radius: var(--radius-sm);
  color: var(--text-primary);
}
.bubble.tool {
  background: var(--bg-muted);
  border-left: 3px solid var(--accent-yellow);
  max-width: 90%;
  font-size: var(--text-sm);
}
.bubble-text {
  white-space: pre-wrap;
  word-break: break-word;
}
.bubble-time {
  font-size: var(--text-xs);
  color: var(--text-muted);
  margin-top: var(--space-1);
  text-align: right;
}
.tool-toggle {
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  font-family: inherit;
  font-size: var(--text-sm);
  padding: 0;
}
.tool-toggle:hover {
  color: var(--text-primary);
}
.tool-content {
  margin: var(--space-2) 0 0;
  font-family: var(--font-mono, 'JetBrains Mono', monospace);
  font-size: var(--text-xs);
  white-space: pre-wrap;
  word-break: break-all;
  color: var(--text-secondary);
}
</style>
