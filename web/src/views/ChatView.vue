<script setup lang="ts">
import { ref, nextTick, watch } from 'vue'
import { NInput, NButton } from 'naive-ui'
import PageLayout from '../components/PageLayout.vue'
import ChatBubble from '../components/ChatBubble.vue'
import { useWebSocket } from '../composables/useWebSocket'

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

const { connected, data, send } = useWebSocket('/ws/chat')
const chatMessages = ref<ChatMessage[]>([])
const input = ref('')
const sending = ref(false)
const thinking = ref(false)
const messagesEl = ref<HTMLElement | null>(null)

function scrollToBottom() {
  nextTick(() => {
    if (messagesEl.value) {
      messagesEl.value.scrollTop = messagesEl.value.scrollHeight
    }
  })
}

watch(data, (msg) => {
  if (!msg) return
  if (msg.type === 'ack') {
    thinking.value = true
  } else if (msg.type === 'thinking') {
    thinking.value = true
  } else if (msg.type === 'response') {
    thinking.value = false
    sending.value = false
    chatMessages.value.push({ role: 'assistant', content: msg.content })
    scrollToBottom()
  } else if (msg.type === 'error') {
    thinking.value = false
    sending.value = false
    chatMessages.value.push({ role: 'assistant', content: `Error: ${msg.error}` })
    scrollToBottom()
  }
})

function sendMessage() {
  const text = input.value.trim()
  if (!text || sending.value) return
  chatMessages.value.push({ role: 'user', content: text })
  send(JSON.stringify({ type: 'message', content: text }))
  input.value = ''
  sending.value = true
  scrollToBottom()
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage()
  }
}
</script>

<template>
  <PageLayout title="Chat">
    <div class="chat-container">
      <div ref="messagesEl" class="chat-messages">
        <div v-if="chatMessages.length === 0" class="chat-empty">
          <span class="empty-icon">◬</span>
          <p>Start a conversation with ComoBot</p>
        </div>
        <ChatBubble
          v-for="(msg, i) in chatMessages"
          :key="i"
          :role="msg.role"
          :content="msg.content"
        />
        <div v-if="thinking" class="thinking-indicator">
          <span class="dot" /><span class="dot" /><span class="dot" />
        </div>
      </div>
      <div class="chat-input-area">
        <div class="connection-status" :class="{ online: connected }">
          {{ connected ? 'Connected' : 'Disconnected' }}
        </div>
        <div class="input-row">
          <NInput
            v-model:value="input"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 4 }"
            placeholder="Type a message..."
            :disabled="!connected"
            @keydown="handleKeydown"
          />
          <NButton
            type="primary"
            :loading="sending"
            :disabled="!input.trim() || !connected"
            @click="sendMessage"
          >
            Send
          </NButton>
        </div>
      </div>
    </div>
  </PageLayout>
</template>

<style scoped>
.chat-container {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 160px);
}
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-4) 0;
}
.chat-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-muted);
  gap: var(--space-3);
}
.empty-icon {
  font-size: 48px;
  opacity: 0.3;
}
.chat-input-area {
  flex-shrink: 0;
  border-top: 1px solid var(--border);
  padding-top: var(--space-3);
}
.connection-status {
  font-size: var(--text-xs);
  color: var(--accent-red);
  margin-bottom: var(--space-2);
}
.connection-status.online {
  color: var(--accent-green, #22c55e);
}
.input-row {
  display: flex;
  gap: var(--space-3);
  align-items: flex-end;
}
.input-row :deep(.n-input) {
  flex: 1;
}
.thinking-indicator {
  display: flex;
  gap: 4px;
  padding: var(--space-3) var(--space-4);
}
.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-muted);
  animation: blink 1.4s infinite both;
}
.dot:nth-child(2) { animation-delay: 0.2s; }
.dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes blink {
  0%, 80%, 100% { opacity: 0.3; }
  40% { opacity: 1; }
}
</style>
