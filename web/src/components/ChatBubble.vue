<script setup lang="ts">
import { ref } from 'vue'
import MarkdownRenderer from './MarkdownRenderer.vue'
import ProcessMessage from './ProcessMessage.vue'
import { useI18n } from '../composables/useI18n'

const { t } = useI18n()

const props = defineProps<{
  role: string
  content: string
  toolCalls?: string
  createdAt?: string
  processType?: string
  processData?: any
}>()

const toolExpanded = ref(false)
const copyDone = ref(false)

function copyContent() {
  const text = props.content || ''
  const onSuccess = () => {
    copyDone.value = true
    setTimeout(() => { copyDone.value = false }, 1500)
  }
  // Clipboard API requires Secure Context (HTTPS or localhost).
  // Fall back to execCommand for HTTP deployments.
  if (navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(text).then(onSuccess).catch(() => fallbackCopy(text, onSuccess))
  } else {
    fallbackCopy(text, onSuccess)
  }
}

function fallbackCopy(text: string, onSuccess: () => void) {
  const ta = document.createElement('textarea')
  ta.value = text
  ta.style.position = 'fixed'
  ta.style.opacity = '0'
  document.body.appendChild(ta)
  ta.select()
  try { document.execCommand('copy'); onSuccess() } catch { /* silent */ }
  document.body.removeChild(ta)
}
</script>

<template>
  <!-- Process message: inline info bar (not a bubble) -->
  <ProcessMessage
    v-if="role === 'process'"
    :process-type="processType || ''"
    :data="processData || {}"
    :timestamp="createdAt"
  />

  <!-- Existing: user / assistant / tool bubbles -->
  <div v-else class="bubble-row" :class="{ 'user-row': role === 'user', 'assistant-row': role === 'assistant', 'tool-row': role === 'tool' }">
    <div class="bubble-wrap" :class="{ 'bubble-wrap--user': role === 'user', 'bubble-wrap--assistant': role === 'assistant' }">
      <div class="bubble" :class="{ user: role === 'user', assistant: role === 'assistant', tool: role === 'tool' }">
        <template v-if="role === 'tool'">
          <button class="tool-toggle" @click="toolExpanded = !toolExpanded">
            {{ toolExpanded ? '\u25BC' : '\u25B6' }} {{ t('chat.toolCall') }}
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
      <!-- Copy button outside bubble -->
      <button
        v-if="(role === 'user' || role === 'assistant') && content"
        class="bubble-copy"
        :class="{ 'bubble-copy--done': copyDone }"
        :title="copyDone ? t('chat.copied') : t('chat.copy')"
        @click="copyContent"
      >
        <svg v-if="!copyDone" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
        </svg>
        <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="20 6 9 17 4 12" />
        </svg>
      </button>
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
  max-width: 100%;
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

/* Copy button */
.bubble-wrap {
  position: relative;
  display: inline-flex;
  flex-direction: column;
  max-width: 75%;
}
.bubble-wrap--user .bubble-copy {
  align-self: flex-start;
}
.bubble-wrap--assistant .bubble-copy {
  align-self: flex-end;
}
.bubble-copy {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  margin-top: 2px;
  padding: 0;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  opacity: 0;
  transition: opacity 150ms, background 150ms, color 150ms;
}
.bubble-wrap:hover .bubble-copy {
  opacity: 1;
}
.bubble-copy:hover {
  background: var(--border);
  color: var(--text-primary);
}
.bubble-copy--done {
  opacity: 1;
  color: var(--accent-green);
}
.bubble-copy--done:hover {
  color: var(--accent-green);
}
</style>
